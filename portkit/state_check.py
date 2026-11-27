#!/usr/bin/env python3
"""Does an old save state still load, and run the same? For every port in ports.json, loads each registered state in the
port's headless runner (hidden, muted, memory cards in a scratch folder), runs `delta` frames, and checks:

  LOAD   the runner exits 0 and says it loaded the state (a state an engine change broke fails with "section ... ends
         before its fields" and starts from the boot instead);
  RAM    the SHA-256 of the RAM dump after those frames equals the baseline's. A different hash is CHANGED, not FAIL:
         an engine change may be meant to change it; after reading why, `--accept` records the new hash.

  python state_check.py [--port NAME ...] [--state NAME ...] [--accept] [--vault] [--list] [--json]

--vault   copies every registered state into <vault>/<port>/, so cleaning a port's build/
          folder (or a session rewriting a state) cannot lose the states this test needs; states missing from the port are taken from the vault.
Exit code: 0 all OK, 1 any FAIL/CHANGED/MISSING. Baselines: baselines/<port>.json (small: hashes, frames, the exe's build time).
Runs one state at a time and only reads the ports (memory cards go to a scratch folder): safe next to running sessions."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, 'ports.json'), encoding='utf-8'))
BASELINES = os.path.join(HERE, 'baselines')
LOADED = re.compile(r'\[state\] loaded (.+?) \(frame (\d+)\)')
BAD = re.compile(r'ends before|cannot load|failed to load|state: .*(error|mismatch)|bad state|unsupported state', re.I)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def resolve(port, rel):
    p = rel if os.path.isabs(rel) else os.path.join(port['dir'], rel)
    return p


def vault_path(name, state):
    return os.path.join(CFG['vault'], name, os.path.basename(state))


def run_state(name, port, state, frames_after):
    exe = resolve(port, port['exe'])
    scratch = os.path.join(CFG['scratch'], name)
    os.makedirs(os.path.join(scratch, 'cards'), exist_ok=True)
    # A runner needs its DLLs: its own folder's, then the MSYS2 UCRT64 ones (what scripts/common.sh puts on the PATH).
    env = dict(os.environ, TMP=scratch, TEMP=scratch,
               PATH=os.pathsep.join([os.path.dirname(exe), 'C:/msys64/ucrt64/bin', os.environ.get('PATH', '')]))
    base = [exe] + port['args'] + ['--card-dir', os.path.join(scratch, 'cards'), '--load-state', state]
    # Pass 1: the state's own frame (the runners count frames in total, so the limit is that frame plus the delta).
    r = subprocess.run(base + ['--frames', '1'], cwd=port['dir'], env=env, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    m = LOADED.search(out)
    if not m:
        return {'status': 'FAIL', 'why': 'no "[state] loaded" line, exit %d' % r.returncode + (' (%s)' % BAD.search(out).group(0) if BAD.search(out) else ''),
                'tail': out.strip().splitlines()[-3:]}
    frame = int(m.group(2))
    dump = os.path.join(scratch, 'ram.bin')
    if os.path.exists(dump):
        os.remove(dump)
    r = subprocess.run(base + ['--frames', str(frame + frames_after), '--dump-ram', dump], cwd=port['dir'], env=env,
                       capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    if r.returncode != 0 or BAD.search(out):
        return {'status': 'FAIL', 'why': 'exit %d %s' % (r.returncode, BAD.search(out).group(0) if BAD.search(out) else ''),
                'tail': out.strip().splitlines()[-3:]}
    if not os.path.exists(dump):
        return {'status': 'FAIL', 'why': 'no RAM dump written', 'tail': out.strip().splitlines()[-3:]}
    return {'status': 'RUN', 'frame': frame, 'ram_sha256': sha256(dump)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', action='append', help='only these ports (default: all with a runner and states)')
    ap.add_argument('--state', action='append', help='only states whose file name contains this')
    ap.add_argument('--accept', action='store_true', help='record the current hashes as the baselines')
    ap.add_argument('--vault', action='store_true', help='copy the registered states into the vault, then stop')
    ap.add_argument('--list', action='store_true', help='show what is registered and where each state is, then stop')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    names = args.port or list(CFG['ports'])
    results, worst = [], 0
    os.makedirs(BASELINES, exist_ok=True)
    for name in names:
        port = CFG['ports'][name]
        states = [s for s in port['states'] if not args.state or any(a in os.path.basename(s) for a in args.state)]
        if not states:
            continue
        for rel in states:
            src = resolve(port, rel)
            vp = vault_path(name, rel)
            where = 'port' if os.path.exists(src) else ('vault' if os.path.exists(vp) else 'MISSING')
            if args.list:
                print('%-10s %-40s %s' % (name, os.path.basename(rel), where))
                continue
            if args.vault:
                if where == 'port' and not os.path.exists(vp):
                    os.makedirs(os.path.dirname(vp), exist_ok=True)
                    shutil.copy2(src, vp)  # a copy, not a link: a session rewriting its state in place must not change the vault's
                    how = 'copied'
                    print('%-10s %-40s %s' % (name, os.path.basename(rel), how))
                else:
                    print('%-10s %-40s %s' % (name, os.path.basename(rel), 'in vault' if os.path.exists(vp) else where))
                continue
            row = {'port': name, 'state': os.path.basename(rel)}
            if where == 'MISSING':
                row.update(status='MISSING', why='not in the port or the vault')
            elif not port['exe'] or not os.path.exists(resolve(port, port['exe'])):
                row.update(status='SKIP', why='no runner built')
            else:
                t0 = time.time()
                row.update(run_state(name, port, src if where == 'port' else vp, port['delta']))
                row['seconds'] = round(time.time() - t0, 1)
                bl_path = os.path.join(BASELINES, name + '.json')
                bl = json.load(open(bl_path)) if os.path.exists(bl_path) else {}
                key = os.path.basename(rel)
                if row['status'] == 'RUN':
                    old = bl.get(key)
                    if args.accept or not old:
                        bl[key] = {'frame': row['frame'], 'delta': port['delta'], 'ram_sha256': row['ram_sha256'],
                                   'exe_time': time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(resolve(port, port['exe']))))}
                        json.dump(bl, open(bl_path, 'w'), indent=1)
                        row['status'] = 'OK' if not old else 'ACCEPTED'
                        row['why'] = 'baseline recorded' if not old else 'new baseline recorded'
                    elif old['ram_sha256'] == row['ram_sha256']:
                        row['status'] = 'OK'
                    else:
                        row['status'] = 'CHANGED'
                        row['why'] = 'RAM after %d frames differs from the baseline (%s)' % (port['delta'], old['exe_time'])
            results.append(row)
            if row['status'] in ('FAIL', 'CHANGED', 'MISSING'):
                worst = 1
            if not args.json:
                print('%-10s %-34s %-9s %s' % (row['port'], row['state'], row['status'], row.get('why', '')))
                for line in row.get('tail', []):
                    print('             ' + line)
    if args.json:
        print(json.dumps(results, indent=1))
    return worst


if __name__ == '__main__':
    sys.exit(main())
