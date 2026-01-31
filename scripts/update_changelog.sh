#!/bin/bash
set -e

# Update changelog for a new version
# Usage: ./scripts/update_changelog.sh <version>

VERSION="$1"
if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.0.2"
    exit 1
fi

DATE=$(date +%Y-%m-%d)
TEMP_FILE=$(mktemp)

echo "📝 Updating CHANGELOG.md for version $VERSION..."

# Create updated changelog
awk -v version="$VERSION" -v date="$DATE" '
    /^## \[Unreleased\]/ {
        print $0
        print ""
        print "### Added"
        print "- New features go here"
        print ""
        print "### Changed"
        print "- Changes to existing functionality go here"
        print ""
        print "### Fixed"
        print "- Bug fixes go here"
        print ""
        print "### Removed"
        print "- Removed features go here"
        print ""
        print "## [" version "] - " date
        next
    }
    /^\[Unreleased\]:/ {
        print "[Unreleased]: https://github.com/yourusername/paprika-skylight/compare/v" version "...HEAD"
        print "[" version "]: https://github.com/yourusername/paprika-skylight/releases/tag/v" version
        next
    }
    { print }
' CHANGELOG.md > "$TEMP_FILE"

# Replace original file
mv "$TEMP_FILE" CHANGELOG.md

echo "✅ CHANGELOG.md updated for version $VERSION"
echo "📝 Please edit the [Unreleased] section and move items to [$VERSION]"

# Open for editing if possible
if command -v code &> /dev/null; then
    echo ""
    read -p "Open CHANGELOG.md in VS Code? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        code CHANGELOG.md
    fi
fi