#!/usr/bin/env bash
# Fetch the corresponding source of the Android libmpv (android/sources.lock) and, with "archive", make the source
# and licence files of a libmpv-android-* release.
#
#   android/fetch_sources.sh checkout <dir>         one git checkout per line of the lock, in <dir>/<name>
#   android/fetch_sources.sh archive <dir> <tag>    the same in <dir>/work, then in <dir>:
#       <tag>-sources.tar.xz       every tree of the lock (recipe/, deps/<name>/), the files of android/ and SOURCES.txt
#       mpv-<commit>-source.tar.xz, ffmpeg-<ref>-source.tar.xz   mpv and FFmpeg alone, the same trees
#       <tag>-licenses.tar.gz      the licence files of every tree, as the sources hold them
#
# Each tree is fetched at the commit of the lock (by its tag when the ref is a tag, then checked), with no history and
# no submodule, as the recipe's include/download-deps.sh clones them. A ref that no longer resolves to the locked
# commit stops the script. The archives are made with a fixed order, owner and time, so the same lock gives the same
# tar content. Needs bash, git, tar (GNU), xz and gzip. Builds nothing.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lock="$here/sources.lock"

usage() {
  sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

lock_lines() {
  grep -v '^#' "$lock" | grep -v '^[[:space:]]*$'
}

checkout() {
  local dir="$1" name url ref commit got
  mkdir -p "$dir"
  while read -r name url ref commit; do
    [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "sources.lock: $name: not a full commit: $commit" >&2; exit 1; }
    if [ -d "$dir/$name/.git" ] && [ "$(git -C "$dir/$name" rev-parse HEAD 2>/dev/null)" = "$commit" ]; then
      echo "$name: $commit (already there)"
      continue
    fi
    rm -rf "${dir:?}/$name"
    git init -q "$dir/$name"
    if [[ "$ref" =~ ^[0-9a-f]{40}$ ]] || [ "$ref" = main ] || [ "$ref" = master ]; then
      # a commit, or a branch the recipe resets to a commit: fetch the commit itself
      git -C "$dir/$name" fetch -q --depth 1 "$url" "$commit"
    else
      git -C "$dir/$name" fetch -q --depth 1 "$url" "refs/tags/$ref"
    fi
    got="$(git -C "$dir/$name" rev-parse 'FETCH_HEAD^{commit}')"
    if [ "$got" != "$commit" ]; then
      echo "$name: $ref is now $got, the lock says $commit; nothing is archived" >&2
      exit 1
    fi
    git -C "$dir/$name" -c advice.detachedHead=false checkout -q "$commit"
    echo "$name: $commit ($ref)"
  done < <(lock_lines)
}

# A tar of <dir> with a fixed order, owner and time (the commit time of the recipe), compressed by <compressor>
fixed_tar() {
  local base="$1" path="$2" mtime="$3"
  tar -C "$base" --sort=name --mtime="@$mtime" --owner=0 --group=0 --numeric-owner --format=gnu \
    --exclude=.git -cf - "$path"
}

archive() {
  local out="$1" tag="$2"
  if ! [[ "$tag" =~ ^libmpv-android-[0-9]{8}-[0-9]+$ ]]; then
    echo "tag: libmpv-android-<date>-<number>, not $tag" >&2
    exit 2
  fi
  local work="$out/work" stage="$out/stage"
  checkout "$work"
  local mtime
  mtime="$(git -C "$work/recipe" log -1 --format=%ct)"
  rm -rf "$stage"
  local top="$stage/$tag-sources"
  mkdir -p "$top/deps" "$top/android"
  local name url ref commit
  while read -r name url ref commit; do
    local dest="$top/deps/$name"
    [ "$name" = recipe ] && dest="$top/recipe"
    mkdir -p "$dest"
    git -C "$work/$name" archive --format=tar HEAD | tar -C "$dest" -xf -
  done < <(lock_lines)
  cp "$here/sources.lock" "$here/fetch_sources.sh" "$here/build.sh" "$here/README.md" "$top/android/"
  {
    echo "Corresponding source of the libmpv of media-kit/libmpv-android-video-build v1.1.7 (flavour default),"
    echo "release $tag of https://github.com/immuch360/libmpv-builds"
    echo
    echo "recipe/             media-kit/libmpv-android-video-build at the tag v1.1.7: build scripts and patches"
    echo "deps/<name>/        each library at its commit, unpatched (the recipe's patch.sh applies"
    echo "                    recipe/buildscripts/patches/ffmpeg and patches/mpv)"
    echo "android/            the files of android/ of immuch360/libmpv-builds: the lock, this archive's script,"
    echo "                    and build.sh, which rebuilds the four jars from this archive"
    echo
    echo "name repository ref commit"
    lock_lines
  } > "$top/SOURCES.txt"

  echo "writing $tag-sources.tar.xz"
  fixed_tar "$stage" "$tag-sources" "$mtime" | xz -9 -T1 > "$out/$tag-sources.tar.xz"

  local mpv_commit ffmpeg_ref
  mpv_commit="$(lock_lines | awk '$1 == "mpv" {print $4}')"
  ffmpeg_ref="$(lock_lines | awk '$1 == "ffmpeg" {print $3}')"
  mkdir -p "$stage/single"
  rm -rf "$stage/single/"*
  cp -a "$top/deps/mpv" "$stage/single/mpv-${mpv_commit:0:10}"
  cp -a "$top/deps/ffmpeg" "$stage/single/ffmpeg-$ffmpeg_ref"
  echo "writing mpv-${mpv_commit:0:10}-source.tar.xz and ffmpeg-$ffmpeg_ref-source.tar.xz"
  fixed_tar "$stage/single" "mpv-${mpv_commit:0:10}" "$mtime" | xz -9 -T1 > "$out/mpv-${mpv_commit:0:10}-source.tar.xz"
  fixed_tar "$stage/single" "ffmpeg-$ffmpeg_ref" "$mtime" | xz -9 -T1 > "$out/ffmpeg-$ffmpeg_ref-source.tar.xz"

  local lic="$stage/$tag-licenses"
  mkdir -p "$lic"
  local tree file
  for tree in "$top/recipe" "$top"/deps/*; do
    name="$(basename "$tree")"
    mkdir -p "$lic/$name"
    for file in "$tree"/COPYING* "$tree"/LICENSE* "$tree"/LICENCE* "$tree"/Copyright* "$tree"/COPYRIGHT* \
                "$tree"/docs/FTL.TXT "$tree"/docs/GPLv2.TXT; do
      [ -f "$file" ] && cp "$file" "$lic/$name/"
    done
    if [ -z "$(ls -A "$lic/$name")" ]; then
      echo "$name: no licence file at the top of its tree" >&2
      exit 1
    fi
  done
  echo "writing $tag-licenses.tar.gz"
  fixed_tar "$stage" "$tag-licenses" "$mtime" | gzip -9n > "$out/$tag-licenses.tar.gz"
  rm -rf "$stage"
}

case "${1:-}" in
  checkout) [ $# -eq 2 ] || usage; checkout "$2" ;;
  archive) [ $# -eq 3 ] || usage; mkdir -p "$2"; archive "$(cd "$2" && pwd)" "$3" ;;
  *) usage ;;
esac
