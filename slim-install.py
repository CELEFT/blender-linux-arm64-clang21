#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Remove build-only, test and development payload from a portable Blender install."""
import argparse
import json
import os
import shutil
from pathlib import Path

FILE_SUFFIXES = ('.a', '.la', '.prl', '.pyc', '.pyo', '.debug')
CACHE_DIRS = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
TOP_LEVEL_BUILD_DIRS = ('include', 'lib/cmake', 'lib/pkgconfig', 'share/man', 'share/doc')


def dir_size(path):
    return sum(entry.stat().st_size for entry in path.rglob('*')
               if entry.is_file() and not entry.is_symlink())


def remove(path, removed):
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    removed.append(str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('install_dir', type=Path)
    parser.add_argument('--no-i18n', action='store_true',
                        help='Remove runtime locale data (the build disables internationalization).')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()

    install_dir = args.install_dir.resolve()
    blender = install_dir / 'blender'
    if not blender.is_file():
        raise SystemExit(f'Not a Blender installation: {blender}')
    before = dir_size(install_dir)
    removed = []

    for relative in TOP_LEVEL_BUILD_DIRS:
        remove(install_dir / relative, removed)

    if args.no_i18n:
        remove(install_dir / 'datafiles/locale', removed)

    python_lib = install_dir / 'python/lib'
    if python_lib.is_dir():
        for python_dir in sorted(python_lib.glob('python*')):
            for name in ('test', 'tests', 'idlelib', 'tkinter', 'turtledemo',
                         'pydoc_data'):
                remove(python_dir / name, removed)
            for config_dir in python_dir.glob('config-*'):
                remove(config_dir, removed)
            for test_binary in (python_dir / 'lib-dynload').glob('_test*.so'):
                remove(test_binary, removed)

    # Remove test packages and bytecode caches wherever they live.
    for directory in sorted(install_dir.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if not directory.is_dir() or directory.is_symlink():
            continue
        if directory.name in CACHE_DIRS:
            remove(directory, removed)
            continue
        relative_parts = directory.relative_to(install_dir).parts
        if ('site-packages' in relative_parts and directory.name in {'test', 'tests'}):
            remove(directory, removed)

    for file in sorted(install_dir.rglob('*')):
        if file.is_file() and not file.is_symlink() and file.suffix in FILE_SUFFIXES:
            remove(file, removed)

    # Remove now-empty directories without traversing symlinks.
    for directory in sorted(install_dir.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()
            except OSError:
                pass

    after = dir_size(install_dir)
    report = {
        'install_dir': str(install_dir),
        'bytes_before': before,
        'bytes_after': after,
        'bytes_saved': before - after,
        'removed_entries': len(removed),
        'removed_sample': removed[:100],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f'SLIM_INSTALL bytes {before} -> {after}, saved {before - after}, entries {len(removed)}',
          flush=True)


if __name__ == '__main__':
    main()
