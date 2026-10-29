#!/bin/sh
set -eu

echo "ContextAPI Parser Sandbox Started"

if [ "$#" -eq 0 ]; then
    echo "ERROR: No sandbox command was provided." >&2
    exit 64
fi

exec "$@"