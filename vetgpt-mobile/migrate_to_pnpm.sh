#!/usr/bin/env bash
# VetGPT — migrate from npm to pnpm
# Run from vetgpt-mobile/ directory:
#   bash migrate_to_pnpm.sh

set -e

echo "═══════════════════════════════════════"
echo "  VetGPT — migrating npm → pnpm"
echo "═══════════════════════════════════════"

# ── 1. Check pnpm is installed ────────────────────────────────────────────────
if ! command -v pnpm &> /dev/null; then
    echo ""
    echo "pnpm not found. Installing via corepack..."
    corepack enable
    corepack prepare pnpm@latest --activate
    echo "✅ pnpm installed: $(pnpm --version)"
else
    echo "✅ pnpm found: $(pnpm --version)"
fi

# ── 2. Remove npm artifacts ───────────────────────────────────────────────────
echo ""
echo "Cleaning npm artifacts..."
rm -rf node_modules
rm -f  package-lock.json
rm -f  yarn.lock
echo "✅ Cleaned"

# ── 3. Install with pnpm ──────────────────────────────────────────────────────
echo ""
echo "Installing dependencies with pnpm..."
pnpm install
echo "✅ Dependencies installed"

# ── 4. Verify key packages ────────────────────────────────────────────────────
echo ""
echo "Verifying installation..."
pnpm list expo expo-router react-native zustand 2>/dev/null | head -20

# ── 5. Clear Expo cache ───────────────────────────────────────────────────────
echo ""
echo "Clearing Expo cache..."
rm -rf .expo
echo "✅ Expo cache cleared"

echo ""
echo "═══════════════════════════════════════"
echo "  Migration complete!"
echo "═══════════════════════════════════════"
echo ""
echo "Commands going forward:"
echo "  pnpm start          → expo start"
echo "  pnpm android        → expo start --android"
echo "  pnpm ios            → expo start --ios"
echo "  pnpm clean          → full reinstall"
echo "  pnpm add <package>  → install new package"
echo "  pnpm remove <pkg>   → uninstall package"
echo ""
echo "Start the app:"
echo "  pnpm start -- --clear"
