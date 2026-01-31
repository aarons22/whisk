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

[Unreleased]: https://github.com/aarons22/whisk/compare/v0.0.3...HEAD
[0.0.3]: https://github.com/aarons22/whisk/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/aarons22/whisk/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/aarons22/whisk/releases/tag/v0.0.1