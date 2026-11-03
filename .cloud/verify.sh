#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
verification_root=$(mktemp -d "${TMPDIR:-/tmp}/mediadesk-cloud-check.XXXXXX")
trap 'rm -rf -- "$verification_root"' EXIT
export XDG_DATA_HOME="$verification_root/data"
export XDG_CONFIG_HOME="$verification_root/config"
export XDG_CACHE_HOME="$verification_root/cache"
export MEDIADESK_GOOGLE_CONFIG="$verification_root/google"
export GDK_BACKEND=x11
export PYTHONPATH="$project_root"
printf 'Source commit: '
git rev-parse HEAD
/usr/bin/python3 --version
cat /etc/os-release
xvfb-run -a /usr/bin/python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
printf '%s\n' 'Source checks completed. Package install/uninstall checks remain on Ubuntu 24.04 CI; local manual acceptance is deferred.'
