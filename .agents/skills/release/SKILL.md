---
name: release
description: Automate semantic releases for this repository with version bumping, changelog drafting from git history, atomic commit/tag creation, and push verification. Use when asked to run `/release`, cut a patch/minor/major release, generate release notes, or prevent tag/commit mismatch.
---

Run a complete release using a single atomic commit and a matching tag.

## Inputs

- Accept one version type: `patch`, `minor`, or `major`.
- Default to `patch` if the user does not specify a type.

## Release Workflow

1. Validate repository state.
   - Ensure working tree is clean unless the user explicitly approves including staged changes.
   - Ensure current branch is the intended release branch.
   - Read current version from `.bumpversion.cfg`.

2. Discover release range.
   - Resolve the latest tag: `git describe --tags --abbrev=0`.
   - Compare changes from `<last_tag>..HEAD`.
   - Stop and report if there are no releasable changes.

3. Analyze user-facing changes.
   - Use `git log`, `git diff --stat`, and targeted diffs.
   - Draft changelog entries grouped under:
     - `Added`
     - `Changed`
     - `Fixed`
     - `Removed`
   - Describe behavior and user impact, not internal refactors.

4. Perform version bump without automatic git side effects.
   - Run `bump2version <patch|minor|major> --no-commit --no-tag`.
   - Never run `git commit --amend` in the release flow.

5. Update release files.
   - Update `CHANGELOG.md` for the new version.
   - Stage release files (typically `.bumpversion.cfg`, `pyproject.toml`, and `CHANGELOG.md`).

6. Create atomic release commit and tag.
   - Commit once with both version and changelog changes.
   - Tag the commit as `v<new_version>`.

7. Verify commit/tag synchronization.
   - Compare `git rev-parse HEAD` and `git rev-parse v<new_version>`.
   - Stop on mismatch and report corrective action.

8. Push in safe order.
   - Push branch first.
   - Push release tag second.

## Command Reference

```bash
# Pre-flight
current_version=$(grep "current_version =" .bumpversion.cfg | awk '{print $3}')
last_tag=$(git describe --tags --abbrev=0 2>/dev/null)

# Change checks
git diff --stat "$last_tag"..HEAD
git log --oneline "$last_tag"..HEAD

# Bump without auto commit/tag
bump2version <patch|minor|major> --no-commit --no-tag
new_version=$(grep "current_version =" .bumpversion.cfg | awk '{print $3}')

# Commit + tag
git add .bumpversion.cfg pyproject.toml CHANGELOG.md
git commit -m "Bump version: $current_version -> $new_version"
git tag "v$new_version"

# Verify tag points at HEAD
[ "$(git rev-parse HEAD)" = "$(git rev-parse "v$new_version")" ]

# Push branch then tag
git push origin HEAD
git push origin "v$new_version"
```

## Output Requirements

- Show:
  - previous version
  - new version
  - release type
  - tag created
- Present final changelog entries before finishing.
- Report push status for branch and tag explicitly.

## Guardrails

- Do not skip synchronization verification.
- Do not tag before the final release commit exists.
- Do not include credentials, tokens, or secrets in output.
