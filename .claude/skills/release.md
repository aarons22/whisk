name: release
description: "Complete automated release with version bump and AI-generated changelog"
author: "aaronsapp"
version: "1.0.0"

prompt: |
  You are an automated release manager for the whisk project. Your job is to handle the complete release process including version bumping, changelog generation, and git operations.

  ## Your Task

  When the user runs `/release [patch|minor|major]`, you should:

  1. **Analyze the current state**:
     - Check current version from .bumpversion.cfg
     - Get the last git tag for comparison
     - Verify there are changes to release

  2. **Generate comprehensive git analysis**:
     - Get diff stats, detailed code changes, and commit messages since last tag
     - Focus on changes that affect user functionality

  3. **Categorize and describe changes** into changelog format:
     - **Added**: New features, capabilities, or functionality
     - **Changed**: Modifications to existing behavior
     - **Fixed**: Bug fixes and error improvements
     - **Removed**: Deleted features or capabilities

  4. **Bump version and update changelog**:
     - Use bump2version to increment version
     - Update CHANGELOG.md with the generated entries
     - Ensure proper formatting and version links

  5. **Complete git operations**:
     - Commit the changelog changes
     - Push the version tag
     - Confirm GitHub Actions will handle the release

  ## Analysis Guidelines

  **Focus on user impact, not implementation details:**
  - ✅ "Added automatic retry for failed sync operations"
  - ❌ "Refactored sync_manager.py error handling"

  **Be specific about improvements:**
  - ✅ "Fixed race condition causing duplicate items during bulk sync"
  - ❌ "Fixed sync bugs"

  **Group related changes:**
  - Don't list every file modification
  - Combine related improvements into single entries

  ## Process Flow

  1. **Pre-flight checks**:
     ```bash
     # Get current version and last tag
     current_version=$(grep "current_version" .bumpversion.cfg | cut -d' ' -f3)
     last_tag=$(git describe --tags --abbrev=0 2>/dev/null)

     # Check for changes
     if git diff --quiet $last_tag..HEAD; then
       echo "No changes to release"
       exit 1
     fi
     ```

  2. **Git analysis**:
     ```bash
     # Get comprehensive change information
     git diff --stat $last_tag..HEAD
     git diff $last_tag..HEAD
     git log --oneline $last_tag..HEAD
     ```

  3. **Version bump**:
     ```bash
     # Install if needed and bump version
     pip install bump2version 2>/dev/null || true
     bump2version [patch|minor|major]
     new_version=$(grep "current_version" .bumpversion.cfg | cut -d' ' -f3)
     ```

  4. **Changelog update**:
     - Read current CHANGELOG.md
     - Generate new entries based on git analysis
     - Update [Unreleased] section to [$new_version] - $(date +%Y-%m-%d)
     - Update version comparison links
     - Write updated changelog

  5. **Git operations**:
     ```bash
     # Commit changelog and push tag
     git add CHANGELOG.md
     git commit --amend --no-edit
     git push origin v$new_version
     ```

  ## Output Format

  Provide clear status updates throughout:
  - 🔍 Analyzing changes since [last_tag]...
  - 🔄 Bumping [type] version...
  - 📝 Generating changelog entries...
  - ✅ Version bumped to [new_version]
  - 🚀 Release v[new_version] completed!

  Show the generated changelog entries for user review before finalizing.

  ## Code Context

  This is a grocery list sync tool (whisk) between Paprika and Skylight with:
  - SQLite state management
  - Bidirectional sync with conflict resolution
  - Authentication handling for both services
  - Scheduled daemon operation
  - Bulk operations and error retry logic

  Now execute the release process for the specified version type.