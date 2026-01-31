#!/bin/bash

# Extract changelog section for a specific version
# Usage: ./extract_changelog.sh v1.0.0

VERSION="$1"

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 v1.0.0"
    exit 1
fi

# Remove 'v' prefix if present for changelog matching
VERSION_NUM="${VERSION#v}"

# Check if CHANGELOG.md exists
if [ ! -f "CHANGELOG.md" ]; then
    echo "Error: CHANGELOG.md not found"
    exit 1
fi

# Extract the section for this version
awk -v version="$VERSION_NUM" '
BEGIN { found=0; printing=0 }

# Look for the version header like ## [1.0.0] - 2023-01-01
/^## \[/ {
    if (found && printing) {
        # We hit the next version section, stop printing
        exit
    }
    if (index($0, "[" version "]") > 0) {
        found=1
        printing=1
        next  # Skip the version header itself
    }
}

# If we found the version and are printing, output the line
found && printing {
    # Skip empty lines at the start
    if (NF > 0 || started) {
        started=1
        print $0
    }
}
' CHANGELOG.md

# Check if we found the version
if ! grep -q "\[$VERSION_NUM\]" CHANGELOG.md; then
    echo "Warning: Version $VERSION_NUM not found in CHANGELOG.md"
    echo "Available versions:"
    grep "^## \[" CHANGELOG.md
    exit 1
fi