# Paprika-Skylight Sync Implementation Patterns

## Overview
This document captures high-level implementation patterns, sync logic decisions, and architectural approaches for the grocery list sync automation.

For detailed API reference (endpoints, request/response formats, error codes), refer to `./API_REFERENCE.md`.

**IMPORTANT** - If you learn about new API structures or examples, you should update the API_REFERENCE.md file accordingly.

---

## Implementation Approach

### Authentication Strategy
- **Paprika**: V1 authentication with token caching for stability
- **Skylight**: Multi-method authentication with frame discovery
- **Token Management**: File-based caching with automatic refresh on 401

### Client Architecture
- **Custom Implementations**: Direct API clients for full control over sync behavior
- **Error Handling**: Graceful degradation with detailed logging
- **State Management**: SQLite-based tracking for conflict resolution and change detection

### Key Design Decisions
1. **Unidirectional Deletion**: Paprika → Skylight only (due to Paprika API limitations)
2. **Bulk Operations**: Use bulk endpoints for efficiency where available
3. **Conservative Sync**: Preserve existing data structures (e.g., Paprika aisles)
4. **Timestamp-Based Conflicts**: "Last edit wins" approach for simplicity
5. **Wrapper Pattern**: Maintain backward compatibility while using working endpoints
6. **State Comparison**: Database-driven change detection for reliable sync

### Implementation Patterns Discovered

**Paprika Integration:**
- V1 authentication proves more stable than V2
- HTTP Basic Auth + form data required for login
- Gzip compression handling needed for responses
- Client-generated UUID4 (uppercase) for new items
- Soft deletion only - mark items as `purchased=True`

**Skylight Integration:**
- Multi-method authentication approach for robustness
- JSON:API format compliance required
- Individual deletion broken - must use bulk destroy endpoint
- Base64 token encoding: `base64(user_id:auth_token)`

**Sync Engine:**
- Three-way state comparison (DB, Paprika, Skylight)
- Bulk operations for efficiency
- Error isolation - single operation failures don't break sync
- Database-first approach for reliable change detection

---

## Sync Logic Decisions

### Timestamp-Based Conflict Resolution
**Why:** Simple, reliable, and user-intuitive

**Algorithm:**
1. Fetch current state from both systems
2. Compare with last-known state (from SQLite DB)
3. Detect changes by comparing timestamps
4. For conflicts (both modified since last sync):
   - Compare `paprika_timestamp` vs `skylight_timestamp`
   - Apply the most recent change to the other system
   - Update local DB with new state

**Pros:**
- Easy to understand ("last edit wins")
- No user intervention needed
- Works well for single-user/family use case

**Cons:**
- Can lose simultaneous edits (rare in practice)
- Requires accurate timestamps from both APIs

### Checked Status Sync
Both systems support checked/purchased status:
- Paprika: `purchased` boolean field
- Skylight: `checked` boolean field

Sync bidirectionally whenever status changes.

### Aisle Preservation
**Key Decision:** Never sync aisle data from Skylight to Paprika

**Rationale:**
- Paprika auto-assigns aisles based on item categorization
- Skylight doesn't have aisle concept
- Overwriting Paprika's aisle field would lose categorization
- Only sync item name and checked status

**Implementation:**
- When creating item in Paprika from Skylight: Let Paprika auto-assign aisle
- When updating Paprika item: Never touch aisle field
- Aisle field excluded from sync operations

### Deletion Handling
**Challenge:** Paprika doesn't support true deletion; Skylight individual deletion is non-functional

**✅ Implemented Solution:**
- **Detection Method:** Compare current API responses with previous sync state in database
- **Paprika → Skylight:** When items missing from Paprika API response, bulk delete from Skylight
- **Skylight Individual Deletion:** Not implemented (Paprika can't truly delete items)
- **Database Tracking:** Items marked as deleted to prevent recreation

**Implementation Details:**
1. **State Comparison:** `get_linked_items_for_pair()` queries database for previously synced items
2. **Missing Item Detection:** Items in database but absent from current Paprika response = deleted
3. **Bulk Deletion:** Use `bulk_delete_items()` with `bulk_destroy` endpoint for efficiency
4. **Error Handling:** Deletion failures don't break entire sync process

**Python Implementation:**
```python
# Detect deletions by comparing API response to database state
current_paprika_ids = {item.paprika_id for item in paprika_items}
linked_items = state_manager.get_linked_items_for_pair(paprika_uid, skylight_id)

# Find items missing from current response
deleted_skylight_ids = []
for link in linked_items:
    if link.paprika_item.paprika_id not in current_paprika_ids:
        deleted_skylight_ids.append(link.skylight_item.skylight_id)

# Bulk delete from Skylight
if deleted_skylight_ids:
    skylight_client.bulk_delete_items(deleted_skylight_ids, list_name)
```

**Scope:**
- ✅ **Paprika → Skylight deletion** (fully implemented)
- ❌ **Skylight → Paprika deletion** (not feasible due to Paprika limitations)

### Change Detection Algorithm

**Three-way comparison:**
1. **Last Known State** (from SQLite DB)
2. **Current Paprika State** (from API)
3. **Current Skylight State** (from API)

**Change Types:**
- **Addition:** Item exists in system but not in DB
- **Deletion:** Item in DB but missing from system (or marked purchased in Paprika)
- **Modification:** Item timestamp changed since last sync
- **Conflict:** Both timestamps changed since last sync

**State Transitions:**
```
Item added in Paprika only → Create in Skylight, add to DB
Item added in Skylight only → Create in Paprika, add to DB
Item deleted from Paprika (purchased) → Delete from Skylight, mark deleted in DB
Item deleted from Skylight → Mark as purchased in Paprika, mark deleted in DB
Item modified in Paprika → Update Skylight
Item modified in Skylight → Update Paprika
Item modified in both → Compare timestamps, apply newer change
```

### SQLite Schema Design

**Schema:**
```sql
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    paprika_id TEXT,
    paprika_list_uid TEXT,  -- Added: Track which Paprika list
    skylight_id TEXT,
    skylight_list_id TEXT,  -- Added: Track which Skylight list
    checked INTEGER DEFAULT 0,  -- Boolean: 0=unchecked, 1=checked
    deleted INTEGER DEFAULT 0,  -- Boolean: Track deleted items
    paprika_timestamp TEXT,     -- ISO 8601 format
    skylight_timestamp TEXT,    -- ISO 8601 format
    last_synced_at TEXT,        -- ISO 8601 format
    UNIQUE(item_name, paprika_list_uid)  -- Unique per list
);
```

**Rationale:**
- Track last-known state to detect changes
- Store IDs and list IDs from both systems
- Timestamps enable conflict resolution
- Deleted flag prevents recreation
- Unique constraint per list (same item name can exist in different lists)

**Why SQLite:**
- Lightweight, no server needed
- ACID transactions for data integrity
- Persists across restarts
- Single file for easy backup
- Built into Python standard library

---

## Research Sources

### Paprika
- **Primary Source:** [Paprika API Gist by Matt Steele](https://gist.github.com/mattdsteele/7386ec363badfdeaad05a418b9a1f30a)
- **Kappari Library:** https://github.com/johnwbyrd/kappari (reference only - not used)
- **Key Findings:**
  - V1 auth more stable than V2
  - Requires HTTP Basic Auth + form data
  - Supports multiple grocery lists via list_uid
  - DELETE not supported - soft delete only
  - Gzip compression required for POST

### Skylight
- **Primary Research Method:** Browser DevTools network inspection
- **Expected Format:** JSON:API specification
- **Key Finding:** Individual deletion non-functional, bulk deletion works

### General
- **Sync Strategy:** Inspired by Dropbox conflict resolution patterns
- **SQLite State Tracking:** Common pattern in sync tools (e.g., rclone)
- **APScheduler:** Standard Python library for cron-like scheduling

---

## Implementation Notes

### Error Handling Strategy
1. **Transient failures:** Retry with exponential backoff
2. **Authentication failures:** Re-authenticate and retry once
3. **Data conflicts:** Log and apply timestamp-based resolution
4. **API changes:** Log errors with full context for debugging
5. **Network issues:** Graceful degradation, log for manual review

### Logging Philosophy
- **INFO:** Sync start/complete, items synced count, list operations
- **WARNING:** Conflict resolutions, retry attempts, soft deletes
- **ERROR:** API failures, authentication issues, data inconsistencies
- **DEBUG:** Full request/response details (credentials redacted)

### Security Considerations
- Never log credentials or tokens
- Store .env with restrictive permissions (chmod 600)
- Cache tokens with restrictive permissions (chmod 600)
- Validate .env exists before starting daemon
- Use HTTPS for all API communications

### Testing Strategy
- Use "Test List" in both apps during development
- Separate from production grocery lists
- Manual verification after automated tests
- Incremental testing (auth → read → write → sync)

---

## Future Improvements (Out of Scope)
- Web UI for monitoring sync status
- Support for syncing multiple list pairs simultaneously
- Manual conflict resolution UI (prompt user instead of automatic)
- Quantity and notes field sync
- Real-time sync via webhooks (if APIs support)
- Multi-user conflict resolution (family sharing scenarios)
- Proper item deletion when Paprika API supports it

---

## Development Workflow Guidelines

### Phase Completion Protocol

When completing any development phase, always follow this cleanup protocol:

1. **Remove Temporary Files**:
   ```bash
   # Remove debug scripts
   rm scripts/debug_*.py scripts/test_*.py scripts/manual_*.py

   # Remove temporary test files
   rm tests/test_*_temp.py tests/debug_*.py

   # Keep only final working tests and essential utilities
   ```

2. **Update Documentation**:
   - Update PROJECT.md with phase status and progress
   - Document any API discoveries in API_REFERENCE.md
   - Update README.md if setup process changed

3. **Verify Clean State**:
   - Run essential tests to ensure functionality still works
   - Check that no broken imports or references exist
   - Commit clean state before starting next phase

4. **File Organization**:
   - Keep only production-ready files and final working tests
   - Move research notes to API_REFERENCE.md if valuable
   - Remove duplicate or obsolete implementations

**Rationale**: Each phase generates many experimental files during development. Cleaning up prevents:
- Confusion about which files are authoritative
- Import errors from deleted dependencies
- Cluttered project structure
- Difficulty finding the correct implementation

### Phase Status Tracking

**Use PROJECT.md for all progress tracking**, not CLAUDE.md. CLAUDE.md should contain:
- High-level implementation patterns and decisions
- Sync logic and conflict resolution strategies
- Research findings and architectural choices
- Code examples for key algorithms

API_REFERENCE.md should contain:
- Detailed API endpoints and formats
- Request/response examples
- Error codes and troubleshooting
- Technical limitations and behaviors

PROJECT.md should contain:
- Overall project status and milestones
- Phase completion tracking
- Architecture overview
- Current development state

---