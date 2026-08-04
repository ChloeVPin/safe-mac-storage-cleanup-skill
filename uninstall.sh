#!/bin/bash
set -euo pipefail

# Uninstaller for cleanme
# Usage: ./uninstall.sh [--target ~/.agents/skills/cleanme]

SKILL_NAME="cleanme"

DEFAULT_TARGETS=(
    "$HOME/.agents/skills/$SKILL_NAME"
    "$HOME/.codex/skills/$SKILL_NAME"
    "$HOME/.claude/skills/$SKILL_NAME"
    "$HOME/.config/opencode/skills/$SKILL_NAME"
    "$HOME/.cursor/skills/$SKILL_NAME"
)

TARGET="${1:-}"

echo "=== cleanme uninstaller ==="

if [[ -z "$TARGET" ]]; then
    echo "No target specified. Removing from common locations..."
    for t in "${DEFAULT_TARGETS[@]}"; do
        if [[ -d "$t" ]]; then
            echo "→ Removing $t"
            rm -rf "$t"
            echo "   Done."
        else
            echo "→ Skipping $t (not found)"
        fi
    done
else
    echo "→ Removing custom target: $TARGET"
    if [[ -d "$TARGET" ]]; then
        rm -rf "$TARGET"
        echo "   Done."
    else
        echo "   Target not found."
    fi
fi

echo ""
echo "Uninstall complete."
echo "To reinstall, run ./install.sh or npx cleanme."
