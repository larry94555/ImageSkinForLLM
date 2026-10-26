#!/usr/bin/env bash
# Installs ffmpeg and ffprobe for CI. Ubuntu's apt mirrors have stalled or crawled at about
# 100 kB/s, so this first downloads a pinned static build from GitHub's release storage, which
# takes seconds, and checks it against the digests below. If the download, the check or a test
# run (including drawing text) fails, it falls back to apt. To update the build, change the
# release and both digests.
set -euo pipefail

base_url="${FFMPEG_BASE_URL:-https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1}"
ffmpeg_sha256=e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99
ffprobe_sha256=4f231a1960d83e403d08f7971e271707bec278a9ae18e21b8b5b03186668450d
bin_dir="${RUNNER_TEMP:-/tmp}/ffmpeg-bin"

install_static() {
  mkdir -p "$bin_dir" &&
    curl -fsSL --retry 3 --connect-timeout 20 --max-time 180 -o "$bin_dir/ffmpeg" "$base_url/ffmpeg-linux-x64" &&
    curl -fsSL --retry 3 --connect-timeout 20 --max-time 180 -o "$bin_dir/ffprobe" "$base_url/ffprobe-linux-x64" &&
    printf '%s  %s\n%s  %s\n' "$ffmpeg_sha256" "$bin_dir/ffmpeg" "$ffprobe_sha256" "$bin_dir/ffprobe" |
    sha256sum --check --strict --quiet &&
    chmod +x "$bin_dir/ffmpeg" "$bin_dir/ffprobe" &&
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
