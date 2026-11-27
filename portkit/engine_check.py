#!/usr/bin/env python3
"""Which BozoEngine is each port on, and does a port still work on another one?

  python engine_check.py                       the table: each port's committed engine pin, how far it is behind the
                                               engine's master on GitHub, and what its working checkout is on
  python engine_check.py --run REF [--port N]  builds each port (or N) against engine commit/branch REF in a scratch
                                               git worktree under <scratch>/enginecheck/<port> (the port's own folder is
                                               never touched: the game/ folder is a junction), then runs state_check's
                                               states on that build and compares them with the baselines
  python engine_check.py --run REF --dry-run   prints the steps only
  python engine_check.py --clean               removes the scratch worktrees

The build is the port's own scripts/build_runtime.sh (CMake + Ninja under MSYS2), so a run is a full build: minutes per
port and all the CPU; run it when the bench is yours, one port at a time (--port), not with a session timing something.
Exit code: 0 every state OK on the new engine (or the table printed), 1 a build failed or a state FAIL/CHANGED."""
import argparse, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import state_check as sc

CFG = sc.CFG
REPO = 'TheBozos/BozoEngine'
# The ports' scripts are for MSYS2's bash (a bare `bash` can be WSL's, which cannot see D:/ paths).
BASH = 'C:/msys64/usr/bin/bash.exe' if os.path.exists('C:/msys64/usr/bin/bash.exe') else 'bash'


def run(cmd, cwd=None, check=True, **kw):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)
    if check and r.returncode != 0:
        raise RuntimeError('%s: %s' % (' '.join(map(str, cmd)), (r.stdout + r.stderr).strip()[-400:]))
    return r


def gh(path):
    return json.loads(run(['gh', 'api', path]).stdout)


def pin_of(port):
    """The engine commit the port's HEAD records (the submodule's gitlink), and the one its checkout is on."""
    r = run(['git', '-C', port['dir'], 'ls-tree', 'HEAD', 'BozoEngine'], check=False).stdout.split()
    pin = r[2] if len(r) >= 3 and r[1] == 'commit' else None
    co = run(['git', '-C', os.path.join(port['dir'], 'BozoEngine'), 'rev-parse', 'HEAD'], check=False).stdout.strip() or None
    return pin, co


def table():
    master = gh('repos/%s/commits/master' % REPO)
    msha = master['sha']
    print('BozoEngine master: %s  %s  %s' % (msha[:7], master['commit']['committer']['date'][:10], master['commit']['message'].splitlines()[0][:70]))
    print('%-10s %-8s %-32s %s' % ('port', 'pin', 'vs master', 'checkout'))
    for name, port in CFG['ports'].items():
        pin, co = pin_of(port)
        if not pin:
            print('%-10s %-8s %s' % (name, '-', 'no BozoEngine submodule recorded'))
            continue
        try:
            cmp = gh('repos/%s/compare/%s...master' % (REPO, pin))
            rel = '%d commits behind' % cmp['ahead_by'] if cmp['ahead_by'] else 'at master'
            if cmp['behind_by']:
                rel += ' (+%d only on its branch)' % cmp['behind_by']
        except RuntimeError:
            rel = 'not on GitHub (a local commit?)'
        note = ''
        if co and co != pin:
            note = 'checkout is %s, not the pin' % co[:7]
        print('%-10s %-8s %-32s %s' % (name, pin[:7], rel, note))


def run_engine(ref, names, dry):
    worst = 0
    for name in names:
        port = CFG['ports'][name]
        if not port.get('build'):
            print('%-10s SKIP  no build script registered' % name)
            continue
        wt = os.path.join(CFG['scratch'], 'enginecheck', name)
        steps = [
            ['git', '-C', port['dir'], 'worktree', 'add', '--detach', wt, 'HEAD'],
            ['git', '-C', wt, 'submodule', 'update', '--init', '--reference', CFG['engine_repo'], 'BozoEngine'],
            ['git', '-C', os.path.join(wt, 'BozoEngine'), 'fetch', 'origin', ref],
            ['git', '-C', os.path.join(wt, 'BozoEngine'), 'checkout', '--detach', 'FETCH_HEAD'],
        ]
        for link in port.get('link', ['game']):
            steps.append(['cmd', '/c', 'mklink', '/J', os.path.join(wt, link).replace('/', '\\'), os.path.join(port['dir'], link).replace('/', '\\')])
        build = [BASH, os.path.join(wt, port['build']).replace('\\', '/')]
        # A build takes the whole shared bench (the port's own lock: other sessions' timed runs wait for it).
        if os.path.exists(os.path.join(port['dir'], 'scripts', 'bench_run.sh')):
            build = [BASH, os.path.join(wt, 'scripts', 'bench_run.sh').replace('\\', '/'), '--alone', '60', 'engine check %s' % ref] + build
        steps.append(build)
        if dry:
            print('== %s' % name)
            for s in steps:
                print('   ' + ' '.join(s))
            continue
        try:
            if os.path.exists(wt):
                print('%-10s reusing %s' % (name, wt))
            else:
                for s in steps[:-1]:
                    run(s)
            env = dict(os.environ, TMP=os.path.join(CFG['scratch'], 'tmp'), TEMP=os.path.join(CFG['scratch'], 'tmp'))
            os.makedirs(env['TMP'], exist_ok=True)
            print('%-10s building on engine %s ...' % (name, ref), flush=True)
            b = run(steps[-1], cwd=wt, check=False, env=env)
            if b.returncode != 0:
                print('%-10s BUILD FAILED\n%s' % (name, (b.stdout + b.stderr).strip()[-1500:]))
                worst = 1
                continue
        except RuntimeError as e:
            print('%-10s SETUP FAILED %s' % (name, e))
            worst = 1
            continue
        # The same states and baselines, on the new build: the exe is the worktree's, the states the port's own.
        p2 = dict(port, dir=wt)
        p2['states'] = [sc.resolve(port, s) for s in port['states']]
        for rel in p2['states']:
            vp = sc.vault_path(name, rel)
            src = rel if os.path.exists(rel) else vp
            if not os.path.exists(src):
                print('%-10s %-34s MISSING' % (name, os.path.basename(rel)))
                worst = 1
                continue
            res = sc.run_state(name, p2, src, port['delta'])
            bl_path = os.path.join(sc.BASELINES, name + '.json')
            bl = json.load(open(bl_path)) if os.path.exists(bl_path) else {}
            old = bl.get(os.path.basename(rel))
            if res['status'] == 'RUN':
                res['status'] = 'OK' if (old and old['ram_sha256'] == res['ram_sha256']) else ('NO BASELINE' if not old else 'CHANGED')
            if res['status'] not in ('OK',):
                worst = 1
            print('%-10s %-34s %-12s %s' % (name, os.path.basename(rel), res['status'], res.get('why', '')))
    return worst


def clean():
    base = os.path.join(CFG['scratch'], 'enginecheck')
    for name, port in CFG['ports'].items():
        wt = os.path.join(base, name)
        if os.path.exists(wt):
            for link in port.get('link', ['game']):
                lp = os.path.join(wt, link)
                if os.path.isdir(lp) and os.path.islink(lp) or os.path.isjunction(lp) if hasattr(os.path, 'isjunction') else False:
                    os.rmdir(lp)  # a junction: removes the link, never the target
            run(['git', '-C', port['dir'], 'worktree', 'remove', '--force', wt], check=False)
            shutil.rmtree(wt, ignore_errors=True)
            print('removed', wt)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', metavar='REF')
    ap.add_argument('--port', action='append')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--clean', action='store_true')
    a = ap.parse_args()
    if a.clean:
        clean()
        return 0
    if a.run:
        return run_engine(a.run, a.port or [n for n, p in CFG['ports'].items() if p.get('build') and p['states']], a.dry_run)
    table()
    return 0


if __name__ == '__main__':
    sys.exit(main())
