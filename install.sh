#/bin/bash
set -euo pipefail

# Simple cross-agent installer for safe-mac-storage-cleanup-skill
# Usage: ./install.sh [--target ~/.agents/skills/mac-storage-cleanup]

SKILL_NAME="mac-storage-cleanup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SOURCE="$SCRIPT_DIR/skill"

DEFAULT_TARGETS=(
    "$HOME/.agents/skills/$SKILL_NAME"
    "$HOME/.codex/skills/$SKILL_NAME"
    "$HOME/.claude/skills/$SKILL_NAME"
)

TARGET="${1:-}"

echo "=== safe-mac-storage-cleanup-skill installer ==="

if [[ -z "$TARGET" ]]; then
    echo "No target specified. Installing to common locations..."
    for t in "${DEFAULT_TARGETS[@]}"; do
        echo "→ Installing to $t"
        mkdir -p "$t"
        cp -r "$SKILL_SOURCE"/* "$t"/ 
        echo "   Done."
    done
else
    echo "→ Installing to custom target: $TARGET"
    mkdir -p "$TARGET"
    cp -r "$SKILL_SOURCE"/* "$TARGET"/ 
fi

echo ""
echo "✅ Installation complete."
echo ""
echo "Next steps:"
echo "1. Tell your AI agent (Codex, Claude, Cursor...):"
echo "   'Load the mac-storage-cleanup skill' or 'My disk is full, use the safe storage cleanup skill'"
echo ""
echo "2. The agent will run a read-only audit first. Nothing is deleted without your explicit approval."
echo ""
echo "Safety: Strict whitelists + validation in safe_cleanup.py + Trash by default."
echo "See README.md and skill/SKILL.md for full details."
echo ""
echo "To uninstall: just delete the skill folder(s) from your agent's skills directory."