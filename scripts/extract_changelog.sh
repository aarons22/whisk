#!/bin/bash
set -e

# Extract changelog section for a specific version
VERSION="$1"

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 v0.0.2"
    exit 1
fi

# Remove 'v' prefix for matching in changelog
CLEAN_VERSION=${VERSION#v}

# Extract the section for this version from CHANGELOG.md
awk -v version="$CLEAN_VERSION" '
    /^## \[/ {
        if ($0 ~ "\\[" version "\\]") {
            found = 1
            next
        } else if (found) {
            exit
        }
    }
    found && /^## \[/ { exit }
    found { print }
' CHANGELOG.md