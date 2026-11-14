#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a portable bin/lib/share Blender tree and create a .tar.xz archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
LAUNCHER = '''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LAUNCHER="$ROOT/lib/blender/blender-launcher.py"
for PYTHON in "$ROOT"/lib/blender/[0-9]*/python/bin/python3*; do
  if [ -x "$PYTHON" ]; then
    exec "$PYTHON" "$LAUNCHER" "$@"
  fi
done
exec python3 "$LAUNCHER" "$@"
'''


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def elf_files(root):
    files = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as file:
            if file.read(4) == b'\x7fELF':
                files.append(path)
    return files


def strip_elfs(elfs):
    if os.environ.get('BLENDER_STRIP_BINARIES', '1') in {'0', 'false', 'off'}:
        print('ELF stripping disabled', flush=True)
        return False
    strip = shutil.which(os.environ.get('STRIP', 'strip'))
    if not strip:
        raise SystemExit('BLENDER_STRIP_BINARIES is enabled but strip is missing.')
    before = sum(path.stat().st_size for path in elfs)
    for path in elfs:
        subprocess.run([strip, '--strip-unneeded', str(path)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    after = sum(path.stat().st_size for path in elfs)
    print(f'Stripped {len(elfs)} ELF files: {before} -> {after} bytes', flush=True)
    return True


def normalize_modes(root):
    for path in [root, *root.rglob('*')]:
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o755)
        else:
            executable = bool(stat.S_IMODE(path.lstat().st_mode) & 0o111)
            path.chmod(0o755 if executable else 0o644)


def copy_file(source, target, mode=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if mode is not None:
        target.chmod(mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--dependency-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--os-label', required=True)
    parser.add_argument('--recipe-dir', type=Path, default=ROOT)
    args = parser.parse_args()

    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('Invalid Blender version.')
    if not re.fullmatch(r'[A-Za-z0-9.]+', args.os_label):
        parser.error('Invalid OS label.')

    payload = args.payload.resolve()
    recipe_dir = args.recipe_dir.resolve()
    output = args.output.resolve()
    if not (payload / 'blender').is_file():
        raise SystemExit(f'Not a Blender installation: {payload}')
    if not (recipe_dir / 'blender-launcher.py').is_file():
        raise SystemExit('Missing blender-launcher.py from recipe directory.')
    if not args.dependency_manifest.is_file():
        raise SystemExit(f'Missing dependency manifest: {args.dependency_manifest}')

    header = subprocess.check_output(['readelf', '-h', str(payload / 'blender')],
                                     text=True, env=dict(os.environ, LC_ALL='C'))
    if not re.search(r'Machine:\s+AArch64', header):
        raise SystemExit('The Blender executable is not AArch64.')

    folder = f'blender-{args.version}-linux-arm64-{args.os_label}-snapdragon8s'
    archive_name = folder + '.tar.xz'
    output.mkdir(parents=True, exist_ok=True)
    archive = output / archive_name
    archive.unlink(missing_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.staging.', dir=output))

    try:
        root = staging / folder
        bin_dir = root / 'bin'
        lib_dir = root / 'lib/blender'
        applications = root / 'share/applications'
        icons = root / 'share/icons/hicolor/scalable/apps'
        docs = root / 'share/doc/blender-linux-arm64'
        bin_dir.mkdir(parents=True)
        applications.mkdir(parents=True)
        icons.mkdir(parents=True)
        docs.mkdir(parents=True)

        shutil.copytree(payload, lib_dir, symlinks=True)
        copy_file(recipe_dir / 'blender-launcher.py', lib_dir / 'blender-launcher.py', 0o755)
        copy_file(args.metadata, lib_dir / 'BUILD-INFO.json')
        copy_file(args.dependency_manifest, lib_dir / 'dependency-sources.tsv')
        copy_file(args.dependency_manifest, root / 'dependency-sources.tsv')

        (bin_dir / 'blender').write_text(LAUNCHER)
        (bin_dir / 'blender').chmod(0o755)

        copy_file(recipe_dir / 'packaging/blender.desktop',
                  applications / 'blender-linux-arm64.desktop', 0o644)
        icon_source = payload / 'blender.svg'
        if not icon_source.is_file():
            raise SystemExit('Missing blender.svg in the Blender installation.')
        copy_file(icon_source, icons / 'blender-linux-arm64.svg', 0o644)
        copy_file(recipe_dir / 'packaging/install-desktop.sh',
                  root / 'install-desktop.sh', 0o755)

        for name in ('README.md', 'RELEASING.md', 'LICENSE'):
            copy_file(recipe_dir / name, root / name, 0o644)
        for name in ('README.md', 'RELEASING.md', 'LICENSE'):
            copy_file(recipe_dir / name, docs / name, 0o644)
        chinese_guide = recipe_dir / 'docs/SNAPDRAGON-8S-GEN3.zh-CN.md'
        if chinese_guide.is_file():
            copy_file(chinese_guide, docs / chinese_guide.name, 0o644)

        stripped = strip_elfs(elf_files(lib_dir))
        normalize_modes(root)

        install_size = sum(path.stat().st_size for path in lib_dir.rglob('*')
                           if path.is_file() and not path.is_symlink())
        info = json.loads(args.metadata.read_text())
        info.update(
            package_name=folder,
            package_version=f'{args.version}+{args.os_label}',
            package_format='tar.xz',
            package_build_os=args.os_label,
            archive_layout='bin-lib-share',
            launcher='bin/blender',
            raw_executable='lib/blender/blender',
            desktop_file='share/applications/blender-linux-arm64.desktop',
            desktop_installer='install-desktop.sh',
            archive_name=archive_name,
            stripped_elf=stripped,
            install_size_bytes=install_size,
        )
        serialized = json.dumps(info, indent=2) + '\n'
        (lib_dir / 'BUILD-INFO.json').write_text(serialized)
        (root / 'BUILD-INFO.json').write_text(serialized)
        (output / 'BUILD-INFO.json').write_text(serialized)

        env = dict(os.environ, LC_ALL='C', XZ_OPT='-9')
        command = ['tar', '--sort=name', '--owner=0', '--group=0', '--numeric-owner',
                   '-C', str(staging), '-cJf', str(archive), folder]
        source_date_epoch = os.environ.get('SOURCE_DATE_EPOCH')
        if source_date_epoch:
            command.insert(1, f'--mtime=@{source_date_epoch}')
        subprocess.run(command, check=True, env=env)

        info.update(archive_size_bytes=archive.stat().st_size,
                    archive_sha256=sha256(archive))
        (output / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2) + '\n')
        print(f'Portable archive: {archive} ({archive.stat().st_size} bytes)', flush=True)
        print(f'SHA256: {info["archive_sha256"]}', flush=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == '__main__':
    main()
