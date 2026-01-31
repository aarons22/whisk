#!/bin/bash
set -e

# Version bump script for whisk
# Usage: ./scripts/bump_version.sh [patch|minor|major]

BUMP_TYPE=${1:-patch}

echo "🔄 Bumping $BUMP_TYPE version..."

# Install bump2version if not available
if ! command -v bump2version &> /dev/null; then
    echo "Installing bump2version..."
    pip install bump2version
fi

# Bump version
bump2version $BUMP_TYPE

# Get the new version
NEW_VERSION=$(grep "current_version" .bumpversion.cfg | cut -d' ' -f3)

echo "✅ Version bumped to $NEW_VERSION"
echo ""
echo "📝 Don't forget to update CHANGELOG.md!"
echo "   1. Move items from [Unreleased] to [$NEW_VERSION] - $(date +%Y-%m-%d)"
echo "   2. Add new [Unreleased] section"
echo "   3. Update version links at bottom"
echo ""
echo "📋 Next steps:"
echo "   1. Review the changes: git log -1 --oneline"
echo "   2. Update CHANGELOG.md with release notes"
echo "   3. Commit changelog: git add CHANGELOG.md && git commit --amend --no-edit"
echo "   4. Push the tag: git push origin v$NEW_VERSION"
echo "   5. GitHub Actions will automatically create a release"

# Optionally open CHANGELOG.md for editing
if command -v code &> /dev/null; then
    echo ""
    read -p "Open CHANGELOG.md in VS Code? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        code CHANGELOG.md
    fi
fi