#!/bin/bash
# The Mac's double-click for AudioDefence.py: runs the game from source with uv (see "On the Mac" in the README).
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed. Install it with:  brew install uv"
    read -r -p "Press Enter to close." _
    exit 1
fi
exec uv run AudioDefence.py "$@"
