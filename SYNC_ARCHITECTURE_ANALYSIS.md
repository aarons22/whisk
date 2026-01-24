# Sync Engine Architecture Issues & Phase 6 Redesign

**Date**: 2026-01-24
**Status**: Critical architectural flaws identified requiring Phase 6 redesign
**Impact**: Core sync functionality non-functional due to incorrect API assumptions

## 🚨 Critical Issues Identified

### 1. **Paprika API Limitations**

**Issue**: Paprika grocery API does not provide timestamp data for conflict resolution.

**API Response Analysis**:
```json
{
  "uid": "0DF6EAD9-3AED-4110-9448-C7EFA572AD24",
  "recipe_uid": null,
  "name": "olive oil",
  "order_flag": 3,
  "purchased": true,  // ✅ This is the "checked" field
  "aisle": "Oils and Dressings",
  "ingredient": "olive oil",
  "recipe": null,
  "instruction": "",
  "quantity": "",
  "separate": false,
  "aisle_uid": "F467DB0B4693D48071CF16A4D9576DA358666D36AE0E4699F03D54BA505853E2",
  "list_uid": "A35D5BB9-3EB3-4DE0-A883-CD786E8564FB"
  // ❌ NO created_at, updated_at, or timestamp fields
}
```

**Impact**:
- Timestamp-based conflict resolution impossible
- Cannot determine which system has "newer" data
- All Paprika items appear as `paprika_timestamp: None`

### 2. **Item Name Duplication Problem**

**Issue**: Item names are NOT unique keys - users commonly have duplicate entries.

**Evidence from Current State**:
```
Skylight Test List (12 items with duplicates):
- milk (checked=True, ID: 121645421)
- milk (checked=False, ID: 121645494)  // DUPLICATE NAME
- olive oil (checked=True, ID: 121645514)
- olive oil (checked=True, ID: 121645504)  // DUPLICATE NAME
- Peanut Butter (ID: 121645511)
- Peanut Butter (ID: 121645517)  // DUPLICATE NAME (case-sensitive)
- peanuts (ID: 121645519)
- peanuts (ID: 121645506)  // DUPLICATE NAME
```

**Impact**:
- Name-based matching creates false conflicts
- Cannot reliably identify "same" items across systems
- Database foreign key relationships impossible with names alone

### 3. **State Management Architecture Flaws**

**Current Database Design Issues**:
```sql
-- Current flawed schema
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    paprika_id TEXT,           -- ❌ Can be NULL
    skylight_id TEXT,          -- ❌ Can be NULL
    checked INTEGER DEFAULT 0,
    paprika_timestamp TEXT,    -- ❌ Always NULL for Paprika
    skylight_timestamp TEXT,
    last_synced_at TEXT,
    UNIQUE(item_name, paprika_list_uid)  -- ❌ Breaks with duplicates
);
```

**Problems**:
- Single table tries to represent items from two different systems
- No foreign key relationships between Paprika and Skylight items
- Cannot handle duplicate item names
- Cannot track item lifecycle (created, modified, deleted)

### 4. **Sync Logic Architectural Flaws**

**Current Flow**:
1. Fetch all items from both systems ✅
2. Compare timestamps for conflict resolution ❌ (No Paprika timestamps)
3. Match items by name ❌ (Names not unique)
4. Update single state table ❌ (Creates duplicates)

**Result**: Creates duplicates instead of syncing, no conflict resolution possible.

### 5. **Delete Operation Handling (DEFERRED)**

**🚨 MAJOR DISCOVERY** (via Charles Proxy analysis):

**Status**: ⏸️ **IMPLEMENTATION DEFERRED** - Research complete, moved to backlog

**Paprika Delete Behavior - CORRECTED**:
```http
POST /api/v2/sync/groceries/ HTTP/1.1
Content-Type: multipart/form-data; boundary=alamofire.boundary.6993f2e2a60b8e82
Authorization: Bearer [token]

--alamofire.boundary.6993f2e2a60b8e82
Content-Disposition: form-data; name="data"; filename="file"
Content-Type: application/octet-stream

[gzipped JSON array - likely with deleted item removed or marked]
```

**Key Insights**:
- ✅ DELETE is actually a SYNC operation using POST `/api/v2/sync/groceries/`
- ✅ Same multipart + gzipped format as CREATE/UPDATE operations
- ✅ Explains why `DELETE /groceries/{id}` returns 404 - wrong endpoint!
- ❓ Need to decode gzipped payload to understand deletion representation
- ❓ Deleted items might be omitted from array OR marked with deletion flag

**Skylight Behavior**:
- DELETE API works (true deletion via `DELETE /items/{id}`)
- Items are permanently removed

**Current Handling**: Using wrong DELETE endpoint for Paprika - should use sync endpoint with proper item state.

**📋 MOVED TO BACKLOG**: Full implementation details moved to PROJECT.md backlog section.

---

## 🏗️ Proposed Phase 6 Architecture Redesign

### **New Database Schema: Separate Tables**

```sql
-- Paprika items table
CREATE TABLE paprika_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paprika_id TEXT NOT NULL UNIQUE,
    list_uid TEXT NOT NULL,
    name TEXT NOT NULL,
    checked INTEGER DEFAULT 0,  -- purchased field from API
    aisle TEXT,
    ingredient TEXT,
    -- Synthetic timestamp management
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_modified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- Sync state
    is_deleted INTEGER DEFAULT 0,
    last_synced_at DATETIME,
    INDEX(paprika_id),
    INDEX(list_uid, name)
);

-- Skylight items table
CREATE TABLE skylight_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skylight_id TEXT NOT NULL UNIQUE,
    list_id TEXT NOT NULL,
    name TEXT NOT NULL,
    checked INTEGER DEFAULT 0,
    -- Real timestamps from API
    skylight_created_at DATETIME,
    skylight_updated_at DATETIME,
    -- Sync state
    last_synced_at DATETIME,
    INDEX(skylight_id),
    INDEX(list_id, name)
);

-- Foreign key relationships between items
CREATE TABLE item_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paprika_item_id INTEGER REFERENCES paprika_items(id),
    skylight_item_id INTEGER REFERENCES skylight_items(id),
    linked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    confidence_score REAL DEFAULT 1.0,  -- For fuzzy name matching
    UNIQUE(paprika_item_id, skylight_item_id)
);

-- Sync operations log for debugging
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,  -- 'CREATE', 'UPDATE', 'DELETE', 'CONFLICT'
    paprika_item_id INTEGER,
    skylight_item_id INTEGER,
    details TEXT,  -- JSON with before/after states
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### **New Sync Algorithm**

#### **Phase 1: Data Collection & Synthetic Timestamps**
```python
def collect_paprika_items():
    """Collect Paprika items and assign synthetic timestamps"""
    current_items = paprika_api.get_items()

    for item in current_items:
        existing = db.get_paprika_item(item.paprika_id)

        if not existing:
            # New item - assign current timestamp
            item.created_at = datetime.utcnow()
            item.last_modified_at = datetime.utcnow()
        else:
            # Existing item - check if modified
            if item.checked != existing.checked or item.name != existing.name:
                item.created_at = existing.created_at
                item.last_modified_at = datetime.utcnow()  # NOW
            else:
                # No changes
                item.created_at = existing.created_at
                item.last_modified_at = existing.last_modified_at

        item.last_seen_at = datetime.utcnow()
        db.upsert_paprika_item(item)

    # Mark items not seen as potentially deleted
    db.mark_unseen_paprika_items_as_deleted()
```

#### **Phase 2: Item Linking Strategy**
```python
def link_items():
    """Create foreign key relationships between systems"""

    # Strategy 1: Exact name match + timing proximity
    unlinked_paprika = db.get_unlinked_paprika_items()
    unlinked_skylight = db.get_unlinked_skylight_items()

    for p_item in unlinked_paprika:
        candidates = [s for s in unlinked_skylight
                     if s.name.lower() == p_item.name.lower()]

        if len(candidates) == 1:
            # Perfect match
            create_link(p_item, candidates[0], confidence=1.0)
        elif len(candidates) > 1:
            # Multiple matches - use timing heuristics
            # Link with most recent Skylight item
            best_match = max(candidates, key=lambda x: x.skylight_updated_at)
            create_link(p_item, best_match, confidence=0.8)

    # Strategy 2: Fuzzy matching for near-misses
    # (e.g., "Peanut Butter" vs "peanut butter")
    remaining_matches = fuzzy_match_items()
    for match in remaining_matches:
        create_link(match.paprika_item, match.skylight_item,
                   confidence=match.score)
```

#### **Phase 3: Conflict Resolution (Paprika as Source of Truth)**
```python
def resolve_conflicts():
    """Resolve conflicts with Paprika as source of truth"""

    linked_items = db.get_linked_items()

    for link in linked_items:
        p_item = link.paprika_item
        s_item = link.skylight_item

        # Check for conflicts
        if p_item.checked != s_item.checked:
            if p_item.last_modified_at > s_item.skylight_updated_at:
                # Paprika is newer - update Skylight
                skylight_api.update_item(s_item.skylight_id,
                                       checked=p_item.checked)
                log_sync_operation('CONFLICT_RESOLVED_PAPRIKA_WINS',
                                 p_item, s_item)
            else:
                # Skylight is newer - but Paprika is source of truth
                # User preference: always favor Paprika or ask user?
                if config.paprika_always_wins:
                    skylight_api.update_item(s_item.skylight_id,
                                           checked=p_item.checked)
                else:
                    # Update Paprika to match Skylight
                    paprika_api.update_item(p_item.paprika_id,
                                          checked=s_item.checked)
                    p_item.last_modified_at = datetime.utcnow()
```

#### **Phase 4: Sync Operations (DELETE LOGIC DEFERRED)**
```python
# NOTE: Delete operations moved to backlog - implementing sync without delete for Phase 6

def handle_item_additions():
    """Handle new items that need to be created in other system"""
    unlinked_paprika = db.get_unlinked_paprika_items()
    unlinked_skylight = db.get_unlinked_skylight_items()

    for p_item in unlinked_paprika:
        # Create in Skylight
        skylight_id = skylight_api.add_item(p_item.name, p_item.checked, skylight_list_name)
        create_link(p_item, skylight_id)

    for s_item in unlinked_skylight:
        # Create in Paprika
        paprika_id = paprika_api.add_item(s_item.name, s_item.checked, paprika_list_name)
        create_link(paprika_id, s_item)

def handle_item_updates():
    """Handle checked status updates between systems"""
    linked_items = db.get_linked_items_with_conflicts()

    for link in linked_items:
        p_item = link.paprika_item
        s_item = link.skylight_item

        if p_item.checked != s_item.checked:
            # Apply conflict resolution
            if config.paprika_always_wins:
                skylight_api.update_item(s_item.skylight_id, checked=p_item.checked)
            else:
                paprika_api.update_item(p_item.paprika_id, checked=s_item.checked)

# DELETE HANDLING DEFERRED TO BACKLOG
# - Paprika delete via full-sync operation (complex implementation)
# - Current soft-delete approach sufficient for Phase 6
```

### **Configuration Options**

```yaml
# config.yaml additions
sync:
  conflict_resolution:
    strategy: "paprika_wins"  # or "skylight_wins", "newest_wins", "prompt_user"
    paprika_always_wins: true

  item_matching:
    exact_name_match: true
    fuzzy_matching: true
    fuzzy_threshold: 0.85
    case_sensitive: false

  deletion_handling:
    paprika_delete_strategy: "soft_delete"  # mark as purchased
    skylight_delete_strategy: "hard_delete"  # actually remove
    propagate_deletions: true

  synthetic_timestamps:
    enabled: true
    change_detection_interval: 5  # seconds between checks
```

### **Benefits of New Architecture**

1. **Proper Foreign Key Relationships**: Clear links between Paprika and Skylight items
2. **Synthetic Timestamp Management**: Create reliable timestamps for Paprika items
3. **Duplicate Name Handling**: Multiple items with same name can coexist and be properly linked
4. **Configurable Conflict Resolution**: Paprika as source of truth, with fallback strategies
5. **Proper Delete Handling**: Handle both soft and hard deletes appropriately
6. **Audit Trail**: Full sync operation logging for debugging
7. **Scalability**: Separate tables can handle thousands of items efficiently

---

## 🚀 Implementation Plan: New Phase 6

### **Phase 6: Sync Engine Redesign (DELETE LOGIC EXCLUDED)**
- **Goal**: Rebuild sync logic with proper architecture for no-timestamp scenario
- **Duration**: 2-3 development sessions
- **Success Criteria**: Reliable bidirectional sync with duplicate handling and Paprika as source of truth

**Tasks (Phase 6)**:
1. ✅ Design and implement new database schema (3 tables)
2. ✅ Create synthetic timestamp management for Paprika items
3. ✅ Implement item linking algorithm with fuzzy matching
4. ✅ Build new conflict resolution with configurable strategies
5. ❌ **DEFERRED**: Proper deletion handling for both systems (moved to backlog)
6. ✅ Create comprehensive test suite with duplicate scenarios
7. ✅ Add sync operation logging and debugging tools

**Phase 7: Production Hardening** (formerly Phase 6)
- Enhanced credential security
- macOS LaunchAgent for auto-start
- Comprehensive documentation
- Production monitoring

**BACKLOG: Paprika Delete Implementation**
- Implement full-sync delete mechanism using POST `/api/v2/sync/groceries/`
- Add methods: `_get_all_grocery_items()`, `_sync_complete_grocery_state()`
- Test with ultra-safe protocol (scripts already prepared)
- Handle asymmetric delete behavior (Paprika→Skylight full delete, Skylight→Paprika soft delete)

---

## 🧪 Demonstration Script

To demonstrate current issues, run:
```bash
# Shows duplicate items and failed sync logic
python scripts/demonstrate_sync_issues.py
```

This comprehensive redesign addresses all the fundamental architectural flaws and creates a robust foundation for reliable grocery list synchronization.