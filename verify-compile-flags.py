#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail the build if any C/C++/ASM translation unit loses the target CPU policy."""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

SOURCE_SUFFIXES = {'.c', '.C', '.cc', '.cpp', '.cxx', '.m', '.mm', '.s', '.S'}
LTO_SUFFIXES = SOURCE_SUFFIXES - {'.s', '.S'}
FORBIDDEN = (
    '-march=native', '-mcpu=native', '-mtune=native',
    '-msve', '-msve2',
)
SVE_ENABLE_RE = re.compile(r'(?:^|[+-])sve2?(?:$|[+\s])')


def command_line(entry):
    if 'arguments' in entry:
        return list(entry['arguments'])
    return shlex.split(entry.get('command', ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compile_commands', type=Path)
    parser.add_argument('--cpu-flag', required=True)
    parser.add_argument('--lto-flag', default=None)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    entries = json.loads(args.compile_commands.read_text())
    checked = []
    missing = []
    forbidden = []
    for entry in entries:
        source = Path(entry.get('file', ''))
        if source.suffix not in SOURCE_SUFFIXES:
            continue
        argv = command_line(entry)
        checked.append(str(source))
        if args.cpu_flag not in argv:
            missing.append(f'{source}: missing {args.cpu_flag}')
        if args.lto_flag and source.suffix in LTO_SUFFIXES and args.lto_flag not in argv:
            missing.append(f'{source}: missing {args.lto_flag}')
        for token in argv:
            if token.startswith(('-', '+')) and (token in FORBIDDEN or SVE_ENABLE_RE.search(token)):
                forbidden.append(f'{source}: {token}')
    if not checked:
        raise SystemExit('compile_commands.json contains no C/C++/ASM translation units')
    if missing:
        preview = '\n'.join(missing[:20])
        raise SystemExit(f'{len(missing)} translation-unit option checks failed:\n{preview}')
    if forbidden:
        preview = '\n'.join(forbidden[:20])
        raise SystemExit(f'Forbidden native/SVE compile options found:\n{preview}')

    binary_info = None
    if args.binary:
        if not args.binary.is_file():
            raise SystemExit(f'Binary does not exist: {args.binary}')
        header = subprocess.check_output(['readelf', '-h', str(args.binary)], text=True,
                                         env=dict(os.environ, LC_ALL='C'))
        if not re.search(r'Machine:\s+AArch64', header):
            raise SystemExit('Blender executable is not AArch64')
        binary_info = {'path': str(args.binary), 'machine': 'AArch64'}

    result = {
        'cpu_flag': args.cpu_flag,
        'lto_flag': args.lto_flag,
        'translation_units_checked': len(checked),
        'forbidden_options': list(FORBIDDEN),
        'binary': binary_info,
        'status': 'PASS',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'CPU_FLAGS_VERIFIED {len(checked)} translation units use {args.cpu_flag}', flush=True)
    print(f'Wrote {args.output}', flush=True)


if __name__ == '__main__':
    main()
