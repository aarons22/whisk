# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New features go here

### Changed
- Changes to existing functionality go here

### Fixed
- Bug fixes go here

### Removed
- Removed features go here

## [0.0.7] - 2026-05-03

### Added
- Added `scripts/pull_external_api_specs.sh` to refresh local snapshots of canonical Paprika and Skylight API specs with pinned commit SHAs

### Changed
- Changed Skylight authentication to use OAuth2 authorization-code flow with bearer and refresh tokens for API access
- Changed project API guidance to treat `paprika-tools` and `skylight-tools` repositories as canonical sources of truth

### Fixed
- Fixed `--config-dir` handling so sync, daemon, list, and config commands consistently use the selected configuration directory
- Fixed Skylight authentication reliability by replacing the brittle multi-endpoint login approach with explicit token exchange and refresh handling

### Removed
- Removed obsolete API reference and debug/research artifacts that no longer match the current API-source-of-truth workflow

## [0.0.6] - 2026-03-07

### Changed
- Changed CLI version reporting to read from the shared package version source instead of a hardcoded value

### Fixed
- Fixed `whisk --version` output mismatch so it now aligns with the released project version

## [0.0.5] - 2026-03-07

### Changed
- Changed `whisk upgrade` to use the active Python interpreter when running inside a virtual environment
- Changed dependency upgrade fallback behavior to retry with `--break-system-packages --user` when non-venv installs fail

### Fixed
- Fixed upgrade failures on externally managed Python environments by broadening fallback handling beyond a single error-string match
- Fixed upgrade error output to show clearer recovery steps for creating and using `~/.whisk/venv`

## [0.0.4] - 2026-03-07

### Added
- Added Paprika recipe index/details integration to sync full recipe content into Skylight meal recipes
- Added persistent Paprika-to-Skylight recipe link tracking to keep recipe-backed meal entries connected across sync runs

### Changed
- Changed meal sync behavior to preserve per-meal fidelity (one Paprika meal entry now maps to one Skylight sitting)
- Changed Skylight meal sitting sync to support linked `meal_recipe_id`, recipe descriptions, and notes for richer meal entries

### Fixed
- Fixed existing SQLite database compatibility by adding automatic meal schema migrations and new indexes during startup
- Fixed Skylight meal update/create handling to align with API requirements when a meal recipe is attached

## [0.0.3] - 2026-01-31

### Fixed
- Fixed upgrade command for externally-managed Python environments (PEP 668 compliance)
- Added virtual environment detection with fallback to --break-system-packages
- Improved GitHub Actions release workflow with proper changelog extraction
- Enhanced release management with atomic version bumping

## [0.0.2] - 2026-01-31

### Added
- Complete meal planning sync between Paprika and Skylight
- Automated release management with version bumping and changelog generation
- Comprehensive API reference documentation
- GitHub Actions CI/CD pipeline for automated testing and releases
- Installation script improvements with proper shell profile integration

### Changed
- Improved meal sync to concatenate multiple Paprika meals into single Skylight meal plans
- Enhanced documentation structure with separate API reference
- Streamlined project organization and removed temporary development files

### Fixed
- Corrected meal type mapping issues in Paprika integration
- Fixed deletion sync to properly remove items deleted in Paprika from Skylight
- Resolved installation script issues with directory detection and shell configuration

## [0.0.1] - 2025-01-31

### Added
- Initial implementation of bidirectional sync between Paprika and Skylight
- SQLite-based state management for conflict resolution
- Automatic token refresh and authentication handling
- Bulk operations for efficient sync operations
- Deletion detection and handling (Paprika → Skylight)

[Unreleased]: https://github.com/aarons22/whisk/compare/v0.0.7...HEAD
[0.0.7]: https://github.com/aarons22/whisk/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/aarons22/whisk/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/aarons22/whisk/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/aarons22/whisk/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/aarons22/whisk/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/aarons22/whisk/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/aarons22/whisk/releases/tag/v0.0.1
