#!/bin/sh
# Launcher for scripts/spanharness.py (POSIX sh; dash and bash 3.2 work).
#   spanharness.sh record | report [OUT.md] [--months N] | lint [--root DIR]   (docs/lessons-format.md, section 2)
# Windows (Git Bash): PowerShell records, so `record` does nothing here and every other command goes to spanharness.ps1.
# Elsewhere: the first python3 or python that is 3.8 or newer runs spanharness.py. `record` never fails the hook.

cmd=${1-}

case $(uname -s 2>/dev/null) in
MINGW* | MSYS* | CYGWIN*)
    [ "$cmd" = record ] && exit 0
    self=$(printf '%s\n' "$0" | tr '\\' '/')
    case $self in
    */*) dir=${self%/*} ;;
    *) dir=. ;;
    esac
    exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$dir/spanharness.ps1" "$@"
    ;;
esac

case $0 in
*/*) dir=${0%/*} ;;
*) dir=. ;;
esac
[ -n "$dir" ] || dir=/

# macOS: /usr/bin/python3 is a stub that opens an install dialog until the Command Line Tools are there.
if [ "$(uname -s 2>/dev/null)" = Darwin ] && [ "$(command -v python3 2>/dev/null)" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then
    if [ "$cmd" = record ]; then
        exit 0
    fi
    echo "spanharness: Python 3.8 or newer is required; install it (for example 'xcode-select --install' or Homebrew python3)." >&2
    exit 1
fi

for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
        exec "$py" -I "$dir/spanharness.py" "$@"
    fi
done

if [ "$cmd" = record ]; then
    cat >/dev/null
    exit 0
fi
echo "spanharness: Python 3.8 or newer is required (python3 or python on PATH)." >&2
exit 1
