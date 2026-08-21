#!/bin/bash
# Install the scheduled run as a macOS LaunchAgent.
#
# The committed plist is a template: launchd needs an absolute path, and this
# fills in wherever you have the project checked out. Run from anywhere:
#
#   bash schedule/install.sh
#
# Remove with:  bash schedule/install.sh --uninstall
set -euo pipefail

LABEL="local.8ktrends"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ "${1:-}" == "--uninstall" ]]; then
    launchctl unload "$TARGET" 2>/dev/null || true
    rm -f "$TARGET"
    echo "removed $LABEL"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__PROJECT_DIR__|$HERE|g" "$HERE/schedule/$LABEL.plist" > "$TARGET"
launchctl unload "$TARGET" 2>/dev/null || true
launchctl load -w "$TARGET"
echo "installed $LABEL for $HERE"
echo "check with:  launchctl list | grep 8ktrends"
