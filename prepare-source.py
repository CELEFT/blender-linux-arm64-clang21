#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve stable upstream tags and matching ARM64 libraries; record exact commits.

Git endpoints can be overridden with BLENDER_SOURCE_URL and
BLENDER_LIBRARY_URL. When the primary Blender host is unavailable, the GitHub
mirrors are tried as a fallback. This keeps CI usable without changing tags or
commits. Domestic/private mirrors can be supplied through the same env vars.
"""
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_URLS = (
    'https://projects.blender.org/blender/blender.git',
    'https://github.com/blender/blender.git',
)
DEFAULT_LIBRARY_URLS = (
    'https://projects.blender.org/blender/lib-linux_arm64.git',
    'https://github.com/blender/lib-linux_arm64.git',
)


def urls_from_env(name, defaults):
    values = []
    override = os.environ.get(name, '').strip()
    if override:
        values.append(override)
    for value in defaults:
        if value not in values:
            values.append(value)
    return tuple(values)


SOURCE_URLS = urls_from_env('BLENDER_SOURCE_URL', DEFAULT_SOURCE_URLS)
LIBRARY_URLS = urls_from_env('BLENDER_LIBRARY_URL', DEFAULT_LIBRARY_URLS)


def git(*args, cwd=None, capture=False, env=None):
    merged = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                  GIT_HTTP_LOW_SPEED_LIMIT='1000', GIT_HTTP_LOW_SPEED_TIME='60')
    if env:
        merged.update(env)
    return subprocess.run(['git', *args], cwd=cwd, check=True, env=merged,
                          text=True, stdout=subprocess.PIPE if capture else None).stdout


def retry_git(args, cwd=None, attempts=3, env=None):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return git(*args, cwd=cwd, env=env)
        except subprocess.CalledProcessError as error:
            last_error = error
            print(f'git attempt {attempt}/{attempts} failed: git {" ".join(args)}', file=sys.stderr,
                  flush=True)
            if attempt != attempts:
                time.sleep(2 * attempt)
    raise last_error


def stable_versions(refs):
    versions = set()
    for line in refs.splitlines():
        match = re.search(r'\trefs/tags/v(\d+)\.(\d+)\.(\d+)$', line)
        if match:
            versions.add(tuple(map(int, match.groups())))
    return sorted(versions)


def ls_remote_tags():
    last_error = None
    for url in SOURCE_URLS:
        try:
            refs = git('ls-remote', '--tags', url, capture=True)
            versions = stable_versions(refs)
            if versions:
                return versions, url
        except subprocess.CalledProcessError as error:
            last_error = error
            print(f'Tag lookup failed via {url}', file=sys.stderr, flush=True)
    if last_error:
        raise last_error
    raise SystemExit('No stable Blender tags found.')


def checkout(directory, urls, ref):
    if directory.exists() and not (directory/'.git').is_dir():
        # A failed/cancelled first download may have created an empty directory
        # before `git init`. Treat only an empty directory as recoverable.
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
        else:
            raise SystemExit(f'{directory} is not a Git checkout; use a fresh checkout to prepare another version.')
    if not directory.exists():
        directory.mkdir(parents=True)
        git('init', str(directory))
        git('remote', 'add', 'origin', urls[0], cwd=directory)
        git('lfs', 'install', '--local', cwd=directory)
    else:
        # Never discard user changes to upstream source.
        git('diff', '--exit-code', cwd=directory)
        git('diff', '--cached', '--exit-code', cwd=directory)
        remotes = git('remote', cwd=directory, capture=True).split()
        if 'origin' not in remotes:
            git('remote', 'add', 'origin', urls[0], cwd=directory)

    last_error = None
    selected_url = None
    for url in urls:
        git('remote', 'set-url', 'origin', url, cwd=directory)
        try:
            retry_git(['fetch', '--depth', '1', 'origin', ref], cwd=directory)
            selected_url = url
            break
        except subprocess.CalledProcessError as error:
            last_error = error
            print(f'Fetch failed via {url}', file=sys.stderr, flush=True)
    if selected_url is None:
        raise last_error or SystemExit(f'Could not fetch {ref}')
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1')
    subprocess.run(['git', 'checkout', '--detach', 'FETCH_HEAD'], cwd=directory,
                   env=env, check=True)
    return git('rev-parse', 'HEAD', cwd=directory, capture=True).strip(), selected_url


def lfs_pull(directory, include):
    retry_git(['lfs', 'pull', include, '--exclude='], cwd=directory)


def check_dependencies():
    rows = list(csv.DictReader((ROOT/'logs/dependency-sources.tsv').open(), delimiter='\t'))
    versions = {row['name']: row['version'] for row in rows if row['version']}
    deps = (ROOT/'source/lib/linux_arm64/deps.md').read_text()
    mismatches = []
    for name, version in re.findall(r'^\| `([^`]+)` \| `([^`]+)`', deps, re.M):
        if name in versions and versions[name] != version:
            mismatches.append(f'{name}: source needs {versions[name]}, libraries list {version}')
    if mismatches:
        print('Dependency version differences (CMake and verification will check compatibility):\n'+'\n'.join(mismatches), flush=True)
        (ROOT/'logs/dependency-version-differences.txt').write_text('\n'.join(mismatches)+'\n')
    if not re.search(r'^\| `', deps, re.M):
        raise SystemExit('Cannot validate the ARM64 dependency manifest.')
    if not mismatches:
        print('ARM64 dependency versions match the source manifest.', flush=True)


def main():
    if '--check-dependencies' in sys.argv:
        check_dependencies()
        return
    requested = os.environ.get('BLENDER_VERSION', '').strip().removeprefix('v')
    archive_info = None
    if (ROOT/'source').is_dir() and not (ROOT/'source/.git').exists() and (ROOT/'BUILD-INFO.json').exists():
        archive_info = json.loads((ROOT/'BUILD-INFO.json').read_text())
        if requested and requested != archive_info['version']:
            raise SystemExit('Source archive contains a different version; use a fresh recipe checkout.')
        requested = archive_info['version']
    if requested and not re.fullmatch(r'\d+\.\d+\.\d+', requested):
        raise SystemExit('BLENDER_VERSION must be a stable version such as 5.2.3.')
    if not requested:
        versions, _source_url = ls_remote_tags()
        requested = '.'.join(map(str, versions[-1]))
    source = ROOT/'source'
    if archive_info:
        source_commit = archive_info['source_commit']
        source_url = archive_info.get('source_url', SOURCE_URLS[0])
    else:
        source_commit, source_url = checkout(source, SOURCE_URLS, 'refs/tags/v'+requested)
        lfs_pull(source, '--include=release/**,assets/**,scripts/**')
    header = (source/'source/blender/blenkernel/BKE_blender_version.h').read_text()
    combined = int(re.search(r'^#define BLENDER_VERSION\s+(\d+)', header, re.M)[1])
    patch = int(re.search(r'^#define BLENDER_VERSION_PATCH\s+(\d+)', header, re.M)[1])
    cycle = re.search(r'^#define BLENDER_VERSION_CYCLE\s+(\w+)', header, re.M)[1]
    actual = f'{combined//100}.{combined%100}.{patch}'
    if actual != requested or cycle != 'release':
        raise SystemExit(f'Tag is not the requested stable release: {actual}, {cycle}')
    if combined < 502:
        raise SystemExit(f'This recipe requires Blender 5.2 or newer, got {actual}.')
    library_ref = os.environ.get('BLENDER_DEPENDENCY_REF', '').strip()
    if not library_ref and archive_info:
        library_ref = archive_info['dependency_commit']
    if library_ref.startswith('-') or any(c.isspace() for c in library_ref):
        raise SystemExit('Invalid dependency ref.')
    if not library_ref:
        # Newer Blender tags may pin ARM64 as a proper submodule.
        tree = git('ls-tree', 'HEAD', 'lib/linux_arm64', cwd=source, capture=True).strip()
        if tree.startswith('160000 commit '):
            library_ref = tree.split()[2]
        else:
            branch = f'blender-v{combined//100}.{combined%100}-release'
            refs = ''
            for url in LIBRARY_URLS:
                try:
                    refs = git('ls-remote', '--heads', url, f'refs/heads/{branch}', capture=True).strip()
                except subprocess.CalledProcessError:
                    continue
                if refs:
                    break
            library_ref = refs.split()[0] if refs else 'refs/heads/main'
    libraries = source/'lib/linux_arm64'
    dependency_commit, dependency_url = checkout(libraries, LIBRARY_URLS, library_ref)
    if library_ref == 'refs/heads/main' and not os.environ.get('BLENDER_DEPENDENCY_REF', '').strip():
        subject = git('log', '-1', '--format=%s', cwd=libraries, capture=True)
        declared = re.search(r'Blender (\d+\.\d+)', subject)
        series = f'{combined//100}.{combined%100}'
        if not declared or declared[1] != series:
            raise SystemExit('No matching release branch or identifiable main library bundle. '
                             'Set BLENDER_DEPENDENCY_REF to a compatible ARM64 library commit.')
    lfs_pull(libraries, '--include=*')
    info = dict(version=requested, source_commit=source_commit, source_url=source_url,
                dependency_commit=dependency_commit, dependency_ref=library_ref,
                dependency_url=dependency_url)
    (ROOT/'logs').mkdir(exist_ok=True)
    (ROOT/'logs/build-info.json').write_text(json.dumps(info, indent=2)+'\n')
    print(json.dumps(info, indent=2), flush=True)


if __name__ == '__main__':
    main()
