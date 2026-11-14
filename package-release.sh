#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

recipe_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${1:-$recipe_dir}" && pwd)"
source "$recipe_dir/build-settings.sh"

release_dir="$recipe_dir/release"
os_id="$(. /etc/os-release; printf '%s%s' "$ID" "${VERSION_ID:-${VERSION_CODENAME:-unknown}}")"
[[ "$os_id" =~ ^[a-zA-Z0-9.]+$ ]] || { echo 'Invalid OS label.' >&2; exit 1; }
binary_name="blender-${blender_version}-linux-arm64-${os_id}-snapdragon8s.tar.xz"
source_name="blender-${blender_version}-source.tar.xz"
metadata="$project_dir/logs/build-info.json"
dependency_manifest="$project_dir/logs/dependency-sources.tsv"

[[ -x "$install_dir/blender" && -f "$project_dir/source/CMakeLists.txt" ]] || {
  echo 'Prepare sources and build first. Set BLENDER_INSTALL_DIR for a custom installation.' >&2
  exit 1
}
[[ -f "$metadata" && -f "$dependency_manifest" ]] || {
  echo 'Missing build metadata or dependency manifest.' >&2
  exit 1
}

mkdir -p "$release_dir"
rm -f "$release_dir/$binary_name" "$release_dir/$source_name" \
      "$release_dir/BUILD-INFO.json" "$release_dir/SHA256SUMS"

echo 'Creating portable bin/lib/share archive...'
python3 "$recipe_dir/package-portable.py" \
  --payload "$install_dir" \
  --metadata "$metadata" \
  --dependency-manifest "$dependency_manifest" \
  --output "$release_dir" \
  --version "$blender_version" \
  --os-label "$os_id" \
  --recipe-dir "$recipe_dir"

# Keep a corresponding-source archive for GPL compliance and auditing.
source_staging="$(mktemp -d "$release_dir/.source-staging.XXXXXX")"
trap 'rm -rf -- "$source_staging"' EXIT
cp "$release_dir/BUILD-INFO.json" "$source_staging/BUILD-INFO.json"
cp "$dependency_manifest" "$source_staging/dependency-sources.tsv"

recipe_files=(
  README.md RELEASING.md LICENSE
  build-blender.sh build-settings.sh prepare-source.sh prepare-source.py
  fetch-dependency-source.py generate-dependency-manifest.cmake
  package-release.sh package-portable.py blender-launcher.py prune-install.py
  verify-build.py verify-compile-flags.py verify-proot.py verify-ui.py verify-vulkan.py
  packaging docs config .github/workflows/manual-build.yml
)
XZ_OPT=-9 tar -cJf "$release_dir/$source_name" \
  --exclude=.git --exclude=source/lib --exclude=source/tests/data \
  -C "$project_dir" source \
  -C "$recipe_dir" "${recipe_files[@]}" \
  -C "$source_staging" BUILD-INFO.json dependency-sources.tsv

cd "$release_dir"
sha256sum "$binary_name" "$source_name" BUILD-INFO.json > SHA256SUMS
for asset in "$binary_name" "$source_name"; do
  [[ "$(stat -c %s "$asset")" -lt 2147483648 ]] || {
    echo "Asset exceeds GitHub's 2 GiB limit: $asset" >&2
    exit 1
  }
done

printf 'Release assets: %s\n' "$release_dir"
du -h "$release_dir/$binary_name" "$release_dir/$source_name"
printf '\nPortable archive layout:\n'
tar -tJf "$release_dir/$binary_name" | sed -n '1,20p' || true
