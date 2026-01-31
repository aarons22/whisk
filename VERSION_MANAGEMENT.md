# Version Management

This project uses automated version management with GitHub releases and human-readable changelogs.

## Quick Release Process

```bash
# 1. Bump version
./scripts/bump_version.sh patch

# 2. Update changelog (script will help you)
# Edit CHANGELOG.md to move items from [Unreleased] to the new version section

# 3. Commit changelog changes
git add CHANGELOG.md
git commit --amend --no-edit

# 4. Push the tag
git push origin v0.0.2
```

## Changelog Format

We follow [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [Unreleased]
### Added
- New features

### Changed
- Changes to existing functionality

### Fixed
- Bug fixes

### Removed
- Removed features

## [0.0.2] - 2025-01-31
### Added
- Human-readable changelog system
- Automated release note extraction
```

## What Happens

1. Script updates `pyproject.toml` version and creates git tag
2. You update `CHANGELOG.md` with human-readable notes
3. You push the tag: `git push origin v0.0.2`
4. GitHub Actions extracts the relevant changelog section
5. Creates release with your human-readable notes + built packages

## Helper Scripts

- `./scripts/update_changelog.sh 0.0.2` - Prepares changelog structure
- `./scripts/extract_changelog.sh v0.0.2` - Tests changelog extraction

## Manual Process

If you prefer doing it manually:

```bash
# Edit version in pyproject.toml and CHANGELOG.md
# Then:
git add pyproject.toml CHANGELOG.md
git commit -m "Bump version to 0.0.2"
git tag v0.0.2
git push origin main
git push origin v0.0.2
```

The GitHub release will include your human-readable changelog section plus installable packages.