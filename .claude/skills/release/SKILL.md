---
name: release
description: "Complete automated release with version bump and AI-generated changelog"
---

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

## Critical Git Synchronization

**⚠️ IMPORTANT**: To prevent tag/commit sync issues, follow this exact sequence:

1. **Never use `git commit --amend`** after `bump2version` has created a tag
2. **Use `--no-commit --no-tag`** flags with bump2version for atomic operations
3. **Always verify** tag points to the correct commit before pushing
4. **Push branch first**, then tag, to ensure proper synchronization

**The Problem We're Solving:**
- `bump2version` creates commit A and tag pointing to A
- Amending creates new commit B, but tag still points to A
- Result: Orphaned commit A with tag, unpushed commit B without tag

**The Solution:**
- Use `bump2version --no-commit --no-tag` to avoid automatic git operations
- Manually create single atomic commit with all changes
- Manually create tag pointing to that commit
- Push both together

## Verification Steps

After completing the release, always verify:
```bash
# Check tag points to correct commit
current_commit=$(git rev-parse HEAD)
tag_commit=$(git rev-parse v$new_version)
if [ "$current_commit" != "$tag_commit" ]; then
    echo "❌ ERROR: Tag/commit mismatch detected!"
    echo "Current commit: $current_commit"
    echo "Tag points to: $tag_commit"
    exit 1
else
    echo "✅ Tag and commit are synchronized"
fi
```

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
   current_version=$(grep "current_version =" .bumpversion.cfg | cut -d' ' -f3)
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

3. **Version bump and changelog (atomic operation)**:
   ```bash
   # Install if needed
   pip install bump2version 2>/dev/null || true

   # Get new version first (before bumping)
   current_version=$(grep "current_version =" .bumpversion.cfg | cut -d' ' -f3)

   # Use bump2version without commit/tag to avoid conflicts
   bump2version [patch|minor|major] --no-commit --no-tag
   new_version=$(grep "current_version =" .bumpversion.cfg | cut -d' ' -f3)

   # Update changelog with generated entries
   # (Update CHANGELOG.md with new entries here)

   # Create single atomic commit with both version bump and changelog
   git add .bumpversion.cfg pyproject.toml CHANGELOG.md
   git commit -m "Bump version: $current_version → $new_version"

   # Create tag on the correct commit
   git tag "v$new_version"
   ```

4. **Git operations**:
   ```bash
   # Push both commit and tag together
   git push origin main
   git push origin "v$new_version"

   # Verify tag points to correct commit
   git show-ref --tags | grep "v$new_version"
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

## Complete Implementation Example

**Correct sequence for atomic version bump:**

```bash
# 1. Analysis phase
current_version=$(grep "current_version =" .bumpversion.cfg | cut -d' ' -f3)
last_tag=$(git describe --tags --abbrev=0 2>/dev/null)

# 2. Version bump (no git operations)
pip install bump2version 2>/dev/null || true
bump2version patch --no-commit --no-tag
new_version=$(grep "current_version =" .bumpversion.cfg | cut -d' ' -f3)

# 3. Update changelog
# [Update CHANGELOG.md with generated entries]

# 4. Atomic commit with all changes
git add .bumpversion.cfg pyproject.toml CHANGELOG.md
git commit -m "Bump version: $current_version → $new_version"

# 5. Create tag on correct commit
git tag "v$new_version"

# 6. Verification
current_commit=$(git rev-parse HEAD)
tag_commit=$(git rev-parse "v$new_version")
if [ "$current_commit" != "$tag_commit" ]; then
    echo "❌ ERROR: Tag/commit mismatch!"
    exit 1
fi

# 7. Push both
git push origin main
git push origin "v$new_version"

echo "✅ Release v$new_version completed successfully!"
```

**Key Changes from Previous Version:**
- ✅ Use `--no-commit --no-tag` flags with bump2version
- ✅ Single atomic commit for all changes
- ✅ Verification step to catch sync issues
- ✅ Push branch before tag
- ❌ **NEVER** use `git commit --amend` after bump2version

Now execute the release process for the specified version type.