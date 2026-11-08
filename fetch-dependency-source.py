#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Download pinned Blender dependency sources and verify their hashes.

The Blender mirror is tried first, then the upstream URI recorded by Blender,
then optional download prefixes from BLENDER_DEPENDENCY_MIRROR_PREFIXES
(comma-separated). Downloads use urllib's normal User-Agent, not a spoofed
browser UA, because several mirrors reject forged browser identities.
"""
import argparse
import csv
import hashlib
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('names', nargs='*')
parser.add_argument('--all', action='store_true')
parser.add_argument('--manifest', type=Path, default=None)
parser.add_argument('--output', type=Path, default=Path('dependency-sources'))
parser.add_argument('--retries', type=int, default=3)
args = parser.parse_args()

manifest = args.manifest or Path(__file__).parent / 'dependency-sources.tsv'
if not manifest.exists():
    manifest = Path(__file__).parent / 'logs/dependency-sources.tsv'
rows = list(csv.DictReader(manifest.open(), delimiter='\t'))
known = {row['name'] for row in rows}
requested = {name.upper() for name in args.names}
unknown = requested - known
if unknown:
    parser.error('Unknown dependencies: ' + ', '.join(sorted(unknown)))
if not args.all and not requested:
    parser.error('Specify dependency names or --all')
if args.retries < 1:
    parser.error('--retries must be positive')

args.output.mkdir(parents=True, exist_ok=True)
prefixes = [
    value.strip().rstrip('/') + '/'
    for value in os.environ.get('BLENDER_DEPENDENCY_MIRROR_PREFIXES', '').split(',')
    if value.strip()
]


def candidate_urls(row):
    candidates = [row.get('blender_mirror', '')]
    upstream = row.get('upstream', '')
    if upstream and upstream not in candidates:
        candidates.append(upstream)
    # A prefix mirror keeps the original URL path, which works for mirrors that
    # expose the same directory layout (for example an internal artifact proxy).
    for prefix in prefixes:
        mirrored = prefix + row.get('file', '')
        if mirrored not in candidates:
            candidates.append(mirrored)
    return [url for url in candidates if url]


def download(url, target):
    temporary = target.with_name(target.name + '.part')
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def verify(row, target):
    digest = hashlib.new(row['hash_type'].lower())
    with target.open('rb') as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().lower() == row['hash'].lower()


for row in rows:
    if not args.all and row['name'] not in requested:
        continue
    target = args.output / row['file']
    if target.exists() and verify(row, target):
        print('Verified', target, flush=True)
        continue
    target.unlink(missing_ok=True)
    last_error = None
    downloaded = False
    for url in candidate_urls(row):
        for attempt in range(1, args.retries + 1):
            try:
                print('Downloading', row['name'], url, f'(attempt {attempt}/{args.retries})', flush=True)
                download(url, target)
                if not verify(row, target):
                    target.unlink(missing_ok=True)
                    raise ValueError('checksum mismatch')
                print('Verified', target, flush=True)
                downloaded = True
                break
            except (OSError, ValueError, urllib.error.URLError) as error:
                last_error = error
                target.unlink(missing_ok=True)
                if attempt != args.retries:
                    time.sleep(2 * attempt)
        if downloaded:
            break
    if not downloaded:
        raise SystemExit(f'Failed to download {row["name"]}: {last_error}')
