#!/bin/sh
# Install a published MediaDesk DEB; the invoking user must already be logged in to gh.
set -eu

repo='yuanhaorannnnnn/MediaDesk'
version=${MEDIADESK_VERSION:-0.1.0}
package="mediadesk_${version}_all.deb"

fail() { printf 'MediaDesk 安装失败：%s\n' "$*" >&2; exit 1; }

printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail '版本号须为数字形式，如 0.1.0。'
for tool in gh sudo apt-get dpkg-deb sha256sum awk mktemp; do
    command -v "$tool" >/dev/null 2>&1 || fail "缺少 $tool，请先安装并确认可用。"
done
[ -r /etc/os-release ] || fail '无法读取系统版本。'
. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 24.04 ] || fail '当前仅验证 Ubuntu 24.04，请检查系统版本。'
gh auth status --hostname github.com >/dev/null 2>&1 || fail '请先使用 gh auth login 登录有仓库访问权限的 GitHub 账号。'

tmp=$(mktemp -d "${TMPDIR:-/tmp}/mediadesk-install.XXXXXXXX")
trap 'rm -rf -- "$tmp"' EXIT HUP INT TERM
printf '正在读取私有 Release v%s…\n' "$version"
gh release download "v$version" --repo "$repo" --dir "$tmp" --pattern "$package" --pattern SHA256SUMS || fail '无法下载 Release，请检查账号权限和网络。'
[ -f "$tmp/$package" ] && [ -f "$tmp/SHA256SUMS" ] || fail 'Release 缺少安装包或校验文件。'

# Accept exactly one checksum for the intended filename, without trusting manifest paths.
expected=$(awk -v name="$package" '$2 == name && length($1) == 64 && $1 ~ /^[[:xdigit:]]+$/ { print tolower($1) }' "$tmp/SHA256SUMS")
[ "$(printf '%s\n' "$expected" | wc -l)" -eq 1 ] && [ -n "$expected" ] || fail '校验文件不包含唯一的安装包 SHA-256。'
actual=$(sha256sum "$tmp/$package")
actual=${actual%% *}
[ "$actual" = "$expected" ] || fail '安装包 SHA-256 不匹配，已停止安装。'
[ "$(dpkg-deb -f "$tmp/$package" Package)" = mediadesk ] || fail '安装包名称不匹配。'
[ "$(dpkg-deb -f "$tmp/$package" Version)" = "$version" ] || fail '安装包版本不匹配。'
[ "$(dpkg-deb -f "$tmp/$package" Architecture)" = all ] || fail '安装包架构不匹配。'

printf '校验通过。apt 将从已配置的软件源处理依赖，可能需要管理员密码。\n'
# The script may arrive on stdin from a pipe; sudo must prompt through the terminal.
if ! sudo -n -v >/dev/null 2>&1; then
    if ! (sudo -v </dev/tty); then
        fail '需要可交互的终端以输入管理员密码，请在终端运行。'
    fi
fi
sudo apt-get update
sudo apt-get install -y "$tmp/$package"
printf 'MediaDesk %s 安装完成，可从应用菜单启动。\n' "$version"
