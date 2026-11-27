#!/usr/bin/env python3
"""Starts a new BozoEngine port with the team's layout, so a new game begins where the last one ended up:

  python new_port.py --title "Amplitude" --iso "D:/Amplitude (USA).iso" [--prefix amp] [--exe-name amplitude] [--dest D:/Amplitude_Recomp]
  python new_port.py --title "Game" --serial SLUS-12345 --elf SLUS_123.45 --sha1 <hash> --region NTSC-U      (no disc to hand)

From the disc (bsdtar reads SYSTEM.CNF and the executable: nothing is extracted to disk) it takes the serial, the executable's
name and SHA-1, and the region. It writes, in <dest>:
  - scripts/ (common, extract_iso with the SHA-1 check, build_runtime, run, bench_run/bench_lock on the shared bench, symbols),
    .gitignore (the game's files, build trees and player folders are never committed), LICENSE (MIT, The Bozos),
    cmake/ and a CMakeLists.txt skeleton that imports BozoEngine and checks the ELF (the rest is copied from a finished port),
    README.md in the team's format (banner first, IMPORTANT note with the disc's SHA-1, status table, build steps),
    docs/RECOMP_NOTES.md, recomp/ tools/ runtime/ folders, runtime/app/<exe>.rc + .manifest (the window's icon and version info);
  - docs/branding/make_logo.py with a starting variant for the game and, run at once, the icon (docs/branding/<prefix>_icon_1024/256.png,
    runtime/app/<exe>.ico) and the banner (docs/branding/<prefix>_banner.png): the team's clown with the game's name, to be themed
    later by a variant in make_logo.py (the same tool as the other ports');
  - git init, and the BozoEngine submodule (the engine's master) unless --no-engine.
It creates nothing on GitHub and pushes nothing: that is the user's call. Refuses a non-empty destination."""
import argparse, hashlib, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'template')
BASE_LOGO = 'D:/Onimusha_Recomp/docs/branding/make_logo.py'  # the logo tool, as the ports keep it
LOGO_MARKER = "if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'oni':"
FONT = 'D:/tmb_kit/downloads/exo2-1796e344/Exo2[wght].ttf'
BSDTAR = 'C:/msys64/usr/bin/bsdtar.exe' if os.path.exists('C:/msys64/usr/bin/bsdtar.exe') else 'bsdtar'
REGIONS = {'SLUS': 'NTSC-U', 'SCUS': 'NTSC-U', 'SLES': 'PAL', 'SCES': 'PAL', 'SLPS': 'NTSC-J', 'SCPS': 'NTSC-J', 'SLPM': 'NTSC-J', 'SCAJ': 'NTSC-J'}
REGION_LONG = {'NTSC-U': 'North American', 'PAL': 'European (PAL)', 'NTSC-J': 'Japanese'}


def tar_out(iso, member):
    r = subprocess.run([BSDTAR, '-xOf', iso, member], capture_output=True)
    if r.returncode != 0:
        raise SystemExit('cannot read %s from %s: %s' % (member, iso, r.stderr.decode(errors='replace').strip()))
    return r.stdout


def disc_info(iso):
    cnf = tar_out(iso, 'SYSTEM.CNF').decode('latin-1')
    m = re.search(r'BOOT2\s*=\s*cdrom0:\\?([A-Z0-9_.]+);1', cnf, re.I)
    if not m:
        raise SystemExit('no BOOT2 line in SYSTEM.CNF:\n' + cnf)
    elf = m.group(1)
    sha1 = hashlib.sha1(tar_out(iso, elf)).hexdigest()
    return elf, sha1


def serial_of(elf):
    m = re.match(r'([A-Z]{4})_(\d{3})\.(\d{2})$', elf.upper())
    if not m:
        raise SystemExit('cannot read a serial from %s: pass --serial' % elf)
    return '%s-%s%s' % (m.group(1), m.group(2), m.group(3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--title', required=True, help='the game, e.g. "Amplitude"')
    ap.add_argument('--iso')
    ap.add_argument('--serial'), ap.add_argument('--elf'), ap.add_argument('--sha1'), ap.add_argument('--region')
    ap.add_argument('--prefix', help='short lower-case name of the port\'s files, e.g. amp (default: the first letters of the title)')
    ap.add_argument('--exe-name', help='the window executable, e.g. amplitude (default: the title in lower case, letters only)')
    ap.add_argument('--dest', help='default D:/<Title>_Recomp')
    ap.add_argument('--no-engine', action='store_true', help='do not add the BozoEngine submodule (no network)')
    a = ap.parse_args()

    elf, sha1 = a.elf, a.sha1
    if a.iso:
        elf, sha1 = disc_info(a.iso)
    if not (elf and sha1):
        raise SystemExit('give --iso, or --elf and --sha1')
    serial = a.serial or serial_of(elf)
    region = a.region or REGIONS.get(serial[:4], 'NTSC-U')
    title = a.title
    words = re.findall(r'[A-Za-z0-9]+', title)
    project = ''.join(w[:1].upper() + w[1:] for w in words) + '_Recomp'
    exe_name = a.exe_name or ''.join(words).lower()
    prefix = a.prefix or exe_name[:4]
    dest = a.dest or 'D:/' + project
    if os.path.exists(dest) and os.listdir(dest):
        raise SystemExit('%s is not empty: not touching it' % dest)

    subs = {
        '@PROJECT_DASH@': project.replace('_', '-'), '@PROJECT@': project, '@TITLE_DASH@': '-'.join(words),
        '@REGION_SHORT@': {'NTSC-U': 'USA', 'PAL': 'Europe', 'NTSC-J': 'Japan'}[region], '@REGION_LONG@': REGION_LONG[region],
        '@REGION@': region, '@SERIAL@': serial, '@ELFNAME@': elf, '@SHA1@': sha1, '@PREFIXU@': prefix.upper(), '@PREFIX@': prefix,
        '@EXE_NAME@': exe_name, '@TITLE@': title,
    }

    def conv(text):
        for k, v in subs.items():
            text = text.replace(k, v)
        return text

    made = []
    for root, _dirs, files in os.walk(TEMPLATE):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, TEMPLATE).replace('\\', '/')
            out = os.path.join(dest, conv(rel))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            raw = open(src, 'rb').read()
            try:
                open(out, 'w', encoding='utf-8', newline='\n').write(conv(raw.decode('utf-8')))
            except UnicodeDecodeError:
                open(out, 'wb').write(raw)
            made.append(conv(rel))
    for sh in os.listdir(os.path.join(dest, 'scripts')):
        os.chmod(os.path.join(dest, 'scripts', sh), 0o755)

    # The logo tool, with a starting variant for the game.
    branding = os.path.join(dest, 'docs', 'branding')
    os.makedirs(branding, exist_ok=True)
    logo = open(BASE_LOGO, encoding='utf-8').read()
    assert LOGO_MARKER in logo, 'the base make_logo.py changed: update LOGO_MARKER'
    block = '''if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '%(prefix)s':
    # %(title)s's starting logo: the team clown with the game's name. Make it the game's own (a variant like the ones above:
    # the clown plus a few generic shapes from the game, no game art) and rerun: python make_logo.py %(prefix)s
    big = icon(1024)
    big.save(os.path.join(OUT, '%(prefix)s_icon_1024.png'))
    icon(256).save(os.path.join(OUT, '%(prefix)s_icon_256.png'))
    app = os.path.join(os.path.dirname(os.path.dirname(OUT)), 'runtime', 'app')
    os.makedirs(app, exist_ok=True)
    big.save(os.path.join(app, '%(exe)s.ico'), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    wordmark(2000, 600, False, title=%(upper)r, subtitle='NATIVE PC PORT  \\u00b7  THE BOZOS',
             title_size=0.26).save(os.path.join(OUT, '%(prefix)s_banner.png'))
    print('%(prefix)s done')
    sys.exit(0)


''' % {'prefix': prefix, 'title': title, 'exe': exe_name, 'upper': title.upper()}
    open(os.path.join(branding, 'make_logo.py'), 'w', encoding='utf-8', newline='\n').write(logo.replace(LOGO_MARKER, block + LOGO_MARKER, 1))
    made.append('docs/branding/make_logo.py')
    env = dict(os.environ, BOZOS_FONT=os.environ.get('BOZOS_FONT', FONT))
    r = subprocess.run([sys.executable, 'make_logo.py', prefix], cwd=branding, env=env, capture_output=True, text=True)
    if r.returncode == 0:
        made += ['docs/branding/%s_icon_1024.png' % prefix, 'docs/branding/%s_icon_256.png' % prefix, 'docs/branding/%s_banner.png' % prefix,
                 'runtime/app/%s.ico' % exe_name]
    else:
        print('WARNING: the icon and banner were not made (needs Pillow and the Exo 2 font, BOZOS_FONT): run `python make_logo.py %s` in docs/branding' % prefix)
        print(r.stderr.strip()[-300:])

    subprocess.run(['git', 'init', '-q', '-b', 'main', dest], check=True)
    if not a.no_engine:
        r = subprocess.run(['git', '-C', dest, 'submodule', 'add', '-q', '-b', 'master', 'https://github.com/TheBozos/BozoEngine.git', 'BozoEngine'],
                           capture_output=True, text=True)
        print('BozoEngine submodule: ' + ('added' if r.returncode == 0 else 'FAILED ' + r.stderr.strip()[-200:]))
    print('\n%s: %s (%s, %s, ELF %s, SHA-1 %s)' % (project, title, serial, region, elf, sha1))
    print('wrote %d files in %s, prefix %r, window executable %r' % (len(made), dest, prefix, exe_name))
    print('Next: scripts/extract_iso.sh "<iso>", then the symbol map and the recompile (copy the CMake from a finished port);')
    print('theme docs/branding/make_logo.py (a %s variant) and rerun it; ask the user before creating the GitHub repo or pushing.' % prefix)


if __name__ == '__main__':
    main()
