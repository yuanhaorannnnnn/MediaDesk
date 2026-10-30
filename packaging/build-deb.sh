#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IFS= read -r app_version < "$project_root/VERSION"
dpkg --validate-version "$app_version"
build_root=$(mktemp -d "${TMPDIR:-/tmp}/mediadesk-deb.XXXXXX")
trap 'rm -rf -- "$build_root"' EXIT HUP INT TERM
install -d "$build_root/DEBIAN" "$build_root/usr/share/mediadesk" "$build_root/usr/bin" "$build_root/usr/share/applications" "$build_root/usr/share/icons/hicolor/scalable/apps"
cp -a "$project_root/mediadesk" "$build_root/usr/share/mediadesk/"
install -m 644 "$project_root/mediadesk/assets/mediadesk.svg" "$build_root/usr/share/icons/hicolor/scalable/apps/mediadesk.svg"
find "$build_root/usr/share/mediadesk" -type d -name __pycache__ -prune -exec rm -rf {} +
cat > "$build_root/DEBIAN/control" <<'CONTROL'
Package: mediadesk
Version: @VERSION@
Section: video
Priority: optional
Architecture: all
Maintainer: MediaDesk personal project
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, librsvg2-common, libvlc5, vlc-plugin-base, vlc-plugin-video-output, ffmpeg, yt-dlp, python3-requests, python3-google-auth, python3-google-auth-oauthlib, python3-secretstorage, xdg-user-dirs
Recommends: nodejs
Description: Personal media library and download workspace
 Local Ubuntu media library with YouTube integration and libVLC playback.
CONTROL
sed -i "s/@VERSION@/$app_version/" "$build_root/DEBIAN/control"
cat > "$build_root/usr/bin/mediadesk" <<'LAUNCHER'
#!/bin/sh
set -eu
export GDK_BACKEND=x11
export PYTHONPATH=/usr/share/mediadesk${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m mediadesk "$@"
LAUNCHER
chmod 755 "$build_root/usr/bin/mediadesk"
cat > "$build_root/usr/share/applications/mediadesk.desktop" <<'DESKTOP'
[Desktop Entry]
Name=MediaDesk
Comment=Personal media library
Exec=mediadesk
Icon=mediadesk
StartupWMClass=MediaDesk
Terminal=false
Type=Application
Categories=AudioVideo;Video;Player;
DESKTOP
mkdir -p "$project_root/dist"
dpkg-deb --build --root-owner-group "$build_root" "$project_root/dist/mediadesk_${app_version}_all.deb"
