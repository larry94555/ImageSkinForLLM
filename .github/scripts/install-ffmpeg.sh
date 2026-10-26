#!/usr/bin/env bash
# Installs ffmpeg and ffprobe for CI. Ubuntu's apt mirrors have stalled or crawled at about
# 40-100 kB/s, so this first downloads a pinned static build from GitHub's release storage, which
# takes seconds, and checks it against the digest below. If the download, the check or a test
# run (including drawing text) fails, it falls back to apt. BtbN keeps the last build of each
# month for two years; to update, pick a newer month-end build and change the release, archive
# and digest together.
set -euo pipefail

base_url="${FFMPEG_BASE_URL:-https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08}"
archive=ffmpeg-n8.1.3-9-g29e619e767-linux64-gpl-8.1.tar.xz
archive_sha256=97ce978979194b5cf7e06a5e68020dbdaa7a4f3294c5452b6a1bc347100dbb79
work_dir="${RUNNER_TEMP:-/tmp}/ffmpeg-static"
bin_dir="$work_dir/bin"

install_static() {
  mkdir -p "$work_dir" &&
    curl -fsSL --retry 3 --connect-timeout 20 --max-time 180 -o "$work_dir/$archive" \
      "$base_url/$archive" &&
    printf '%s  %s\n' "$archive_sha256" "$work_dir/$archive" | sha256sum --check --strict --quiet &&
    tar -xJf "$work_dir/$archive" -C "$work_dir" --strip-components=1 \
      --wildcards '*/bin/ffmpeg' '*/bin/ffprobe' &&
    "$bin_dir/ffmpeg" -version >/dev/null &&
    "$bin_dir/ffprobe" -version >/dev/null &&
    can_draw_text
}

# Some tests label videos with drawtext, which needs fontconfig to find a font.
can_draw_text() {
  local err
  if ! err=$("$bin_dir/ffmpeg" -v error -f lavfi -i color=c=black:s=64x64:d=0.1 \
    -vf drawtext=text=ok -f null - 2>&1); then
    echo "Static ffmpeg can't draw text: $err"
    return 1
  fi
}

start=$(date +%s)
if install_static; then
  echo "$bin_dir" >>"$GITHUB_PATH"
  export PATH="$bin_dir:$PATH"
  echo "Installed static ffmpeg from $base_url"
else
  echo "::warning::Static ffmpeg install from $base_url failed; falling back to apt"
  apt_opts=(-o Acquire::Retries=3 -o Acquire::http::Timeout=30)
  sudo apt-get "${apt_opts[@]}" update -q
  sudo apt-get "${apt_opts[@]}" install -y -q --no-install-recommends ffmpeg
  echo "Installed ffmpeg from apt"
fi
ffmpeg -version | head -n 1
ffprobe -version | head -n 1
echo "ffmpeg install took $(($(date +%s) - start)) s"
