#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export GDK_BACKEND=x11
export PYTHONPATH="$project_root${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m mediadesk "$@"
