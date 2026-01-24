# Paprika ↔ Skylight Grocery List Sync

**Version**: Phase 2 Complete
**Last Updated**: 2025-01-24
**Status**: ✅ Skylight Integration Complete, Ready for Phase 3

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

### 🔄 **Phase 3: State Management (NEXT)**
- **Status**: Ready to begin
- **Goal**: SQLite-based state tracking for change detection
- **Components**:
  - Database schema design
  - Change detection logic
  - Last-known state tracking
  - Conflict identification

### ⏳ **Remaining Phases**
- **Phase 4**: Sync Engine with Conflict Resolution
- **Phase 5**: Scheduling and Configuration
- **Phase 6**: Production Hardening

## 🏗️ Architecture

### **Technology Stack**
- **Language**: Python 3.10+
- **Paprika**: Custom HTTP client (no external library)
- **Skylight**: Custom HTTP client with JSON:API parsing
- **State Management**: SQLite database
- **Scheduling**: APScheduler (planned)
- **Configuration**: .env + YAML files

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
│   ├── models.py        # GroceryItem data model
│   ├── paprika_client.py    # Paprika API client ✅
│   ├── skylight_client.py   # Skylight API client ✅
│   ├── state_manager.py     # SQLite state tracking (Phase 3)
│   ├── sync_engine.py       # Bidirectional sync logic (Phase 4)
│   └── main.py              # Entry point & scheduler (Phase 5)
├── scripts/
│   ├── find_skylight_frame.py  # Frame ID discovery helper
│   └── verify_setup.py         # Setup verification
├── tests/
│   ├── test_final_crud.py      # ✅ Complete CRUD test
│   ├── test_paprika.py         # Paprika integration tests
│   └── test_skylight_full.py   # Skylight integration tests
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
- 🔄 Phase 3: State tracking and change detection
- 🔄 Phase 4: Bidirectional sync with conflict resolution
- 🔄 Phase 5: Automated scheduling
- 🔄 Phase 6: Production deployment ready

## 📈 Progress Metrics

### **API Integrations**
- **Paprika**: 100% ✅ (Create, Read, Update, Delete)
- **Skylight**: 100% ✅ (Create, Read, Update, Delete)

### **Core Functionality**
- **Authentication**: 100% ✅ Both systems
- **Data Models**: 100% ✅ GroceryItem with timestamps
- **Error Handling**: 90% ✅ Comprehensive logging
- **State Management**: 0% 🔄 (Phase 3)
- **Sync Logic**: 0% 🔄 (Phase 4)
- **Scheduling**: 0% 🔄 (Phase 5)

### **Code Quality**
- **Documentation**: Comprehensive API patterns in CLAUDE.md
- **Testing**: Full CRUD tests for both systems
- **Configuration**: Template-based setup with examples
- **Error Handling**: Structured logging with context

## 🚀 Next Steps

### **Immediate (Phase 3)**
1. Design SQLite schema for state tracking
2. Implement StateManager class
3. Add change detection logic
4. Test with mock sync scenarios

### **Short Term (Phases 4-5)**
1. Implement bidirectional sync engine
2. Add conflict resolution (timestamp-based)
3. Add scheduling with APScheduler
4. Create CLI interface with dry-run mode

### **Long Term (Phase 6)**
1. Production hardening and error recovery
2. macOS launch daemon setup
3. Comprehensive monitoring and logging
4. Documentation for handoff

## 🛡️ Risk Assessment

### **Low Risk** ✅
- API stability (both working reliably)
- Data safety (using test lists)
- Reversibility (can disable sync anytime)

### **Medium Risk** ⚠️
- Unofficial APIs may change
- Rate limiting unknown
- Token expiration handling

### **Mitigation Strategies**
- Conservative API usage patterns
- Comprehensive error handling
- Manual fallback procedures
- Test list isolation

---

**Next Milestone**: Phase 3 - State Management
**Estimated Effort**: 1-2 development sessions
**Success Criteria**: Change detection working with SQLite state tracking