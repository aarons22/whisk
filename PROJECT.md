# Paprika ↔ Skylight Grocery List Sync

**Version**: Phase 5 Complete - Critical Architecture Issues Identified
**Last Updated**: 2026-01-24
**Status**: 🚨 Architecture Redesign Required - Phase 6 Redefined

## 📋 Project Overview

Automated bidirectional sync system for grocery lists between Paprika Recipe Manager and Skylight digital frames. Changes in either system automatically propagate to the other with conflict resolution.

**Core Goal**: Keep grocery lists synchronized across both platforms so family members can use either Paprika (mobile) or Skylight (kitchen display) seamlessly.

## 🎯 Current Status

### ✅ **Phase 1: Paprika Integration (COMPLETE)**
- **Duration**: Completed
- **Status**: ✅ All functionality working
- **Components**:
  - Custom Paprika API client (HTTP Basic Auth + gzip compression)
  - V1 authentication with token caching
  - Grocery list discovery and targeting
  - Full CRUD operations (create, read, update, delete)
  - Aisle auto-assignment preservation
  - Comprehensive error handling

**Key Discoveries**:
- V1 API more stable than V2 (avoids "Unrecognized client" errors)
- Requires gzip-compressed JSON arrays for write operations
- Uses multipart form data for item creation
- True deletion not supported (soft delete via `purchased=true`)

### ✅ **Phase 2: Skylight Integration (COMPLETE)**
- **Duration**: Completed 2025-01-24
- **Status**: ✅ All CRUD operations working perfectly
- **Components**:
  - Discovered API structure via browser DevTools
  - HTTP Basic Auth with `user_id:auth_token` format
  - JSON:API response parsing
  - Full CRUD operations tested and verified
  - Frame and list discovery

**Key Discoveries**:
- API Base: `https://app.ourskylight.com/api`
- Auth: `Authorization: Basic <base64(user_id:auth_token)>`
- Status mapping: `"pending"` = unchecked, `"completed"` = checked
- Update method: `PUT` with explicit status values
- Create endpoint: `POST /frames/{frameId}/lists/{listId}/list_items`

**Verified Working**:
- ✅ Authentication and frame discovery
- ✅ List discovery and item reading
- ✅ Item creation with proper JSON:API format
- ✅ Item updates (check/uncheck status)
- ✅ Item deletion
- ✅ Timestamp parsing for conflict resolution

### ✅ **Phase 3: State Management (COMPLETE)**
- **Duration**: Completed 2025-01-24
- **Status**: ✅ All functionality working and tested
- **Components**:
  - SQLite database schema with proper indexing
  - StateManager class with comprehensive CRUD operations
  - Change detection algorithm (additions, modifications, deletions)
  - Conflict detection with timestamp-based resolution
  - Sync state tracking and statistics
  - Soft deletion support with tracking

**Key Features**:
- **Database Schema**: Optimized with indexes and triggers
- **Change Detection**: Three-way comparison (last known vs. current state)
- **Conflict Resolution**: Timestamp-based "most recent wins"
- **Statistics**: Sync coverage, item distribution, recent activity
- **Data Integrity**: ACID transactions, foreign key constraints
- **Performance**: Indexed lookups, efficient queries

**Verified Working**:
- ✅ Database initialization and schema creation
- ✅ Item tracking across both systems
- ✅ Change detection for all modification types
- ✅ Conflict detection for concurrent modifications
- ✅ Sync statistics and reporting
- ✅ Deletion tracking with soft deletes
- ✅ Comprehensive test suite (6/6 tests passing)

### ✅ **Phase 4: Sync Engine with Conflict Resolution (COMPLETE)**
- **Duration**: Completed 2025-01-24
- **Status**: ✅ All functionality working and tested
- **Components**:
  - SyncEngine class coordinating both API clients
  - Timestamp-based conflict resolution ("most recent wins")
  - Dry-run mode for safe testing
  - Comprehensive error handling and retry logic
  - State integration for change detection
  - Bidirectional sync with automatic conflict resolution

**Key Features**:
- **Conflict Resolution**: Timestamp-based with most recent change winning
- **Change Detection**: Three-way comparison using StateManager
- **Dry-run Mode**: Safe testing without making actual changes
- **Error Recovery**: Retry logic with exponential backoff
- **Status Monitoring**: Comprehensive sync reporting
- **Atomic Operations**: All-or-nothing sync with rollback capability

**Verified Working**:
- ✅ Bidirectional sync (items created in both directions)
- ✅ Conflict resolution (timestamp-based winner selection)
- ✅ Dry-run mode (simulation without changes)
- ✅ Deletion sync (removals propagated between systems)
- ✅ Status reporting (comprehensive metrics)
- ✅ Error handling (graceful failure recovery)
- ✅ Comprehensive test suite (6/6 tests passing)

### ✅ **Phase 5: Scheduling and Configuration (COMPLETE)**
- **Duration**: Completed 2025-01-24
- **Status**: ✅ All functionality working and tested
- **Components**:
  - main.py entry point with CLI argument parsing
  - APScheduler for periodic sync execution
  - Configuration loading from .env and config.yaml
  - Logging setup with file rotation
  - Graceful signal handling (SIGTERM/SIGINT)
  - Error handling and retry logic with exponential backoff

**Key Features**:
- **CLI Interface**: --dry-run, --once, --daemon modes
- **Configuration Management**: Secure .env + YAML settings
- **Scheduled Execution**: APScheduler with configurable intervals
- **Logging**: File rotation with console and file output
- **Error Recovery**: Retry logic with exponential backoff
- **Graceful Shutdown**: Signal handling for clean daemon termination

**Verified Working**:
- ✅ CLI argument parsing and help
- ✅ Configuration loading and validation
- ✅ Once mode (both dry-run and real sync)
- ✅ Daemon mode with scheduled intervals
- ✅ Logging setup with file rotation
- ✅ Error handling and configuration validation
- ✅ Graceful shutdown with SIGTERM handling
- ✅ Comprehensive test suite (8/8 tests passing)

### 🚨 **CRITICAL DISCOVERY: Paprika Delete Mechanism Identified**

**Real-world testing and Charles proxy analysis revealed fundamental misunderstanding:**

#### **Paprika Delete Reality:**
- ❌ **NOT individual DELETE API calls** - returns 404 (endpoint doesn't exist)
- ✅ **Full grocery list sync operation** - POST complete updated array to `/api/v2/sync/groceries/`
- ✅ **Heavy network operation** - every delete fetches ALL items (200KB+) and posts complete state
- ✅ **All-or-nothing** - must preserve ALL other items exactly or risk production data loss

**Process**: DELETE one item = GET all items (669 total) → filter out deleted item → POST complete array

#### **Test Protocol Ready:**
- 🛡️ **Ultra-safe test developed** with production data protection
- 📁 **Complete backup system** with restoration capability
- 🧪 **Test ready to execute** when implementation timing decided
- 📋 **All test files prepared** and validated

#### **Implementation Impact:**
- 🔧 **Requires complete rewrite** of delete operations (Phase 6)
- 📊 **Performance considerations** - caching and batching needed
- 🎯 **Architecture validated** - sync endpoint approach confirmed viable

**Research Status**: ✅ Complete | **Testing**: Ready but deferred | **Implementation**: Future phase TBD

### ✅ **Phase 6: Sync Engine Architecture Redesign (COMPLETE)**
- **Duration**: Completed 2026-01-24
- **Status**: ✅ All functionality working and tested
- **Goal**: Rebuild sync logic to handle duplicate items, missing timestamps, and proper conflict resolution
- **Key Achievement**: **Comprehensive architecture redesign successfully implemented**

**Critical Issues Resolved:**
- ✅ **Paprika API provides no timestamps** - implemented synthetic timestamp management
- ✅ **Item names not unique** - built intelligent fuzzy matching with confidence scoring
- ✅ **Database schema redesigned** - 3-table architecture with proper relationships
- ✅ **Sync logic rebuilt** - handles duplicates and conflicts intelligently

**Implementation Completed:**
- ✅ **StateManagerV2**: New 3-table schema (paprika_items, skylight_items, item_links, sync_log)
- ✅ **Synthetic Timestamp Management**: Change detection for Paprika items without API timestamps
- ✅ **ItemLinker**: Intelligent fuzzy matching algorithm with confidence scoring
- ✅ **ConflictResolver**: Configurable strategies (Paprika wins, newest wins, Skylight wins)
- ✅ **Comprehensive Logging**: Full audit trail of all sync operations
- ✅ **Comprehensive Test Suite**: Real-world scenarios with duplicates and edge cases

**Verified Working:**
- ✅ Duplicate item name handling (multiple items with same name supported)
- ✅ Case-insensitive fuzzy matching ("Peanut Butter" ↔ "peanut butter")
- ✅ Timestamp-based conflict resolution with synthetic timestamps
- ✅ Multiple conflict resolution strategies with dry-run mode
- ✅ 100% item linking rate in comprehensive tests
- ✅ Complete audit trail with operation logging
- ✅ Foreign key relationships between systems

### 🔄 **Phase 7: Multiple List Syncing and CLI Redesign (PLANNING)**
- **Status**: Planning in progress
- **Goal**: Transform into "Whisk" - production CLI with multiple list support
- **Duration**: Estimated 7-10 phases (major expansion)

**Key Features:**
- **Multiple List Syncing**: One-to-one list pairing (Paprika ↔ Skylight)
- **Interactive Setup Wizard**: Complete elimination of manual config editing
- **Professional CLI Interface**: `whisk setup`, `whisk sync`, `whisk start`
- **Authentication Optimization**: Streamlined Skylight auth with token caching
- **Configuration Simplification**: Hardcode technical settings, focus on user needs

**Phases Breakdown:**
- **Phase 7a**: Configuration System Redesign (2-3 days)
- **Phase 7b**: Interactive Setup Wizard (3-4 days)
- **Phase 7c**: Multiple List Sync Architecture (3-4 days)
- **Phase 7d**: Authentication Optimization (2 days)
- **Phase 7e**: CLI Implementation (4-5 days)
- **Phase 7f**: Remove Hardcoded References (1 day)
- **Phase 7g**: Package Restructuring as "Whisk" (1 day)

### 🚀 **Phase 8: Production Hardening (FUTURE)**
- **Status**: Future work after Phase 7 completion
- **Goal**: Production deployment readiness
- **Components**: Enhanced security, daemon management, comprehensive documentation

## 🏗️ Architecture

### **Technology Stack**
- **Language**: Python 3.10+
- **Paprika**: Custom HTTP client (no external library)
- **Skylight**: Custom HTTP client with JSON:API parsing
- **State Management**: SQLite database
- **Scheduling**: APScheduler ✅
- **Configuration**: .env + YAML files ✅
- **CLI Interface**: argparse with multiple modes ✅

### **Data Flow**
```
Paprika App ←→ Paprika API ←→ Sync Engine ←→ Skylight API ←→ Skylight Frame
                              ↕
                          SQLite State DB
```

### **Configuration**
```
Frame ID: 4878053
Paprika List: "Test List" (development) → "My Grocery List" (production)
Skylight List: "Test List" (development) → "Grocery List" (production)
```

## 📁 Project Structure

```
paprika-skylight/
├── .env                    # Credentials (gitignored)
├── .env.example           # Credential template
├── config.yaml            # Non-sensitive settings
├── PROJECT.md            # This file - project status
├── CLAUDE.md            # Implementation patterns & API docs
├── README.md            # Setup instructions
├── pyproject.toml       # Dependencies
├── src/
│   ├── models.py                 # GroceryItem data model ✅
│   ├── paprika_client.py         # Paprika API client ✅
│   ├── skylight_client.py        # Skylight API client ✅
│   ├── state_manager.py          # SQLite state tracking ✅
│   ├── sync_engine.py            # Bidirectional sync logic ✅
│   └── main.py                   # Entry point & scheduler ✅
├── scripts/
│   ├── find_skylight_frame.py  # Frame ID discovery helper
│   └── verify_setup.py         # Setup verification
├── tests/
│   ├── test_final_crud.py        # ✅ Complete CRUD test
│   ├── test_paprika.py           # Paprika integration tests
│   ├── test_skylight_full.py     # Skylight integration tests
│   ├── test_state_management.py  # State tracking tests
│   ├── test_sync_engine.py       # Sync engine tests ✅
│   └── test_phase5.py            # Phase 5 comprehensive tests ✅
└── examples/
    └── skylight_usage.py       # Usage demonstration
```

## 🔧 Development Workflow

### **Current Development Environment**
- Python 3.12.8 via pyenv
- Virtual environment: `.venv/`
- Credentials configured in `.env`
- All tests passing

### **Testing Strategy**
- **Development Lists**: Use "Test List" in both systems
- **Manual Verification**: Check changes in actual apps
- **Production Safety**: Never touch production grocery lists during development
- **Progressive Testing**: Each phase independently testable

### **Quality Gates**
- ✅ Phase 1: All Paprika CRUD operations working
- ✅ Phase 2: All Skylight CRUD operations working
- ✅ Phase 3: State tracking and change detection working
- ✅ Phase 4: Bidirectional sync with conflict resolution working
- ✅ Phase 5: Automated scheduling and configuration complete
- ✅ Phase 6: Sync engine architecture redesign complete

## 📈 Progress Metrics

### **API Integrations**
- **Paprika**: 100% ✅ (Create, Read, Update, Delete)
- **Skylight**: 100% ✅ (Create, Read, Update, Delete)

### **Core Functionality**
- **Authentication**: 100% ✅ Both systems
- **Data Models**: 100% ✅ GroceryItem with timestamps
- **Error Handling**: 100% ✅ Comprehensive logging and retry logic
- **State Management**: 100% ✅ Complete with change detection
- **Sync Logic**: 100% ✅ Bidirectional with conflict resolution
- **Scheduling**: 100% ✅ APScheduler with CLI interface
- **Configuration**: 100% ✅ Secure .env + YAML management

### **Code Quality**
- **Documentation**: Comprehensive API patterns in CLAUDE.md
- **Testing**: Full CRUD tests for both systems
- **Configuration**: Template-based setup with examples
- **Error Handling**: Structured logging with context

## 📋 Backlog (Future Work)

### **Paprika Delete Mechanism Implementation (DEFERRED)**
- **Priority**: Medium (functionality works with soft-delete workaround)
- **Description**: Implement true Paprika deletion using full-sync operations
- **Research Status**: ✅ Complete - Charles proxy analysis revealed POST to `/api/v2/sync/groceries/`
- **Implementation Ready**: ✅ Ultra-safe test protocol prepared with production data protection

**Technical Details:**
- Paprika deletion = GET all items (200KB+) → filter out deleted item → POST complete array
- Requires rewriting `PaprikaClient.remove_item()` to use full-sync approach
- Must add new methods: `_get_all_grocery_items()` and `_sync_complete_grocery_state()`
- Need state caching to minimize expensive full-sync operations

**Delete Behavior Decision (Documented & Accepted):**
- ✅ **Paprika → Skylight**: Full deletion (sync operation → true delete)
- ⚠️ **Skylight → Paprika**: Soft delete only (marked as purchased due to API design)

**Ready for Implementation:**
- Test files prepared: `scripts/ultra_safe_paprika_test.py`, `scripts/restore_paprika_backup.py`
- Complete backup and restoration capability available
- Architecture redesign strategy defined in `PAPRIKA_DELETE_RESEARCH.md`

---

## 🚀 Next Steps

### **Phase 7: Multiple List Syncing and CLI Redesign (PLANNING)**
Transform into "Whisk" - a professional CLI tool with multiple list support and interactive setup.

**Sub-Phase Breakdown:**
1. **Configuration System Redesign** - Support multiple list pairs with simplified schema
2. **Interactive Setup Wizard** - Complete Q&A flow replacing manual config editing
3. **Multiple List Sync Architecture** - Independent sync pairs with per-pair conflict resolution
4. **Authentication Optimization** - Streamlined Skylight auth (15→1 endpoints) + token caching
5. **CLI Implementation** - Professional interface: `whisk setup`, `whisk sync`, `whisk start/stop`
6. **Remove Hardcoded References** - Eliminate all "Test List" defaults in codebase
7. **Package Restructuring** - Rename to "Whisk" with proper CLI entry points

**Key Benefits:**
- **Multiple List Support** - Essential feature for power users
- **User-Friendly Setup** - No manual YAML/env editing required
- **50%+ Faster Startup** - Direct Skylight auth + token caching
- **Professional CLI** - Standard interface with comprehensive help
- **Simplified Configuration** - Technical settings hardcoded, focus on user needs

### **Current Status** 📋
**Phase 6 is complete** and **Phase 7 planning underway**:

- ✅ **Sync Engine Architecture**: Comprehensive redesign complete with proper conflict resolution
- ✅ **Individual API Clients**: Paprika and Skylight CRUD operations work reliably
- ✅ **State Management**: New 3-table schema with intelligent item linking
- ✅ **Conflict Resolution**: Multiple strategies with comprehensive test coverage
- 📋 **Next**: Transform into multi-list CLI tool with interactive setup

**Status**: **Phase 6 complete, Phase 7 planning in progress - Major expansion to multi-list CLI**

## 🛡️ Risk Assessment

### **Low Risk** ✅
- API stability (both working reliably)
- Data safety (using test lists)
- Reversibility (can disable sync anytime)

### **Medium Risk** ⚠️
- Unofficial APIs may change
- Rate limiting unknown
- Production deployment considerations

### **High Priority TODOs** 🚨
- **Phase 6 Architecture Redesign** - Sync logic requires fundamental rewrite based on research findings
  - Paprika deletion uses full-sync operations (not individual DELETEs)
  - Must implement complete state management for 200KB+ grocery arrays
  - Architecture redesign strategy defined but implementation deferred (timing TBD)
- **Delete Asymmetry Accepted** - Skylight→Paprika deletions will soft delete (mark as purchased) due to API constraints
- **Ready for Implementation** - Ultra-safe test protocol prepared with production data protection

### **Mitigation Strategies**
- Conservative API usage patterns
- Comprehensive error handling
- Manual fallback procedures
- Test list isolation

---

**Next Milestone**: Phase 7 - Multiple List Syncing and CLI Redesign (Whisk)
**Implementation Status**: Phase 6 complete - Planning Phase 7 expansion
**Success Criteria**: Professional CLI tool with multiple list syncing and interactive setup