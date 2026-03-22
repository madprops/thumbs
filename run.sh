#!/usr/bin/env bash
root="$(dirname "$(readlink -f "$0")")"
"$root/venv/bin/python" "$root/src/main.py" "$@"