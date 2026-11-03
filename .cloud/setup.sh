#!/usr/bin/env bash
set -euo pipefail

# Run in the Cloud setup conversation, not against a personal desktop account.
if ! command -v apt-get >/dev/null; then
  echo 'MediaDesk Cloud setup requires an apt-based environment; use Ubuntu 24.04 CI for package validation.' >&2
  exit 1
fi
installer=()
if [[ $(id -u) -ne 0 ]]; then
  if ! command -v sudo >/dev/null || ! sudo -n true 2>/dev/null; then
    echo 'Noninteractive package installation is unavailable. Keep full system checks on the existing Ubuntu CI.' >&2
    exit 1
  fi
  installer=(sudo -n)
fi
"${installer[@]}" apt-get update -qq
"${installer[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  python3 python3-qrcode python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 \
  librsvg2-common libvlc5 vlc-plugin-base vlc-plugin-video-output ffmpeg yt-dlp \
  python3-requests python3-google-auth python3-google-auth-oauthlib \
  python3-secretstorage xdg-user-dirs xvfb xauth desktop-file-utils nodejs
/usr/bin/python3 --version
df -h .
