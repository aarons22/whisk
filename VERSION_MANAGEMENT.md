# Version Management

This project uses AI-powered automated release management through a single Claude Code skill.

## One Command Releases

```bash
/release patch    # Bug fixes (0.0.2 → 0.0.3)
/release minor    # New features (0.0.2 → 0.1.0)
/release major    # Breaking changes (0.0.2 → 1.0.0)
```

## What Happens Automatically

The `/release` skill handles everything:

1. **🔍 Analysis**: Examines git diffs and commits since last tag
2. **📝 Changelog**: Generates human-readable changelog entries
3. **🔄 Version Bump**: Updates pyproject.toml and creates git tag
4. **📋 Update**: Updates CHANGELOG.md with new version section
5. **🚀 Release**: Commits changes, pushes tag, triggers GitHub release

## AI-Generated Changelog

The skill analyzes your actual code changes and generates user-focused entries:

**Input**: Git diffs + commit messages
**Output**: Professional changelog entries like:
```markdown
### Added
- Automatic retry mechanism for failed sync operations
- Better error messages when Skylight authentication fails

### Fixed
- Race condition causing duplicate items during bulk sync
- Network timeout handling in Paprika API calls
```

## Manual Fallback

If needed, you can still use the basic version bump script:
```bash
./scripts/bump_version.sh patch
# Then manually edit CHANGELOG.md
git add CHANGELOG.md && git commit --amend --no-edit
git push origin v0.0.3
```

## Benefits

- **Simple**: Single `/release patch` command
- **Smart**: AI understands code impact vs implementation details
- **Consistent**: Professional changelog format every time
- **Complete**: Handles all git operations automatically

Your release process is now fully automated with intelligent changelog generation!