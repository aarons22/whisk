# Paprika-Skylight Sync Implementation Patterns

## Overview
This document captures implementation patterns, API research findings, and technical decisions for the grocery list sync automation.

---

## Paprika API Patterns

### Authentication

**V1 Authentication (Implemented):**
- Endpoint: `https://www.paprikaapp.com/api/v1/account/login/`
- Method: POST
- **Authentication:** HTTP Basic Auth (email/password) + form data
- Returns: `{"result": {"token": "bearer_token_here"}}`
- More stable than V2, avoids "Unrecognized client" errors

**Implementation:**
```python
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth(email, password)
data = {"email": email, "password": password}
response = requests.post(url, data=data, auth=auth)
token = response.json()["result"]["token"]
```

**V2 Authentication (Avoid):**
- Endpoint: `https://www.paprikaapp.com/api/v2/account/login/`
- Can trigger "Unrecognized client" errors on repeated auth
- Not recommended for programmatic access

### Token Management
1. Cache bearer token to file (`.paprika_token`)
2. Set restrictive permissions: `chmod 600`
3. Reuse cached token until 401 response
4. Re-authenticate only on token expiration
5. Token format in headers: `Authorization: Bearer {token}`

### Grocery Lists Discovery

**Critical Discovery:** Paprika supports multiple named grocery lists.

**Endpoint:** `GET /api/v2/sync/grocerylists/`

**Response:**
```json
{
  "result": [
    {
      "uid": "A35D5BB9-3EB3-4DE0-A883-CD786E8564FB",
      "name": "Test List",
      "order_flag": 13,
      "is_default": false,
      "reminders_list": "Test List"
    },
    {
      "uid": "9E12FCF54A89FC52EA8E1C5DA1BDA62A6617ED8BDC2AEB6F291B93C7A399F6F6",
      "name": "My Grocery List",
      "order_flag": 0,
      "is_default": true,
      "reminders_list": "Paprika"
    }
  ]
}
```

**Usage:**
- Query this endpoint to get list UIDs
- Cache results (lists don't change frequently)
- Use `list_uid` when creating/updating items
- Required to target specific grocery lists

### Grocery Item Operations

**Read Items:** `GET /api/v2/sync/groceries/`

**Response Characteristics:**
- Returns ALL items from ALL grocery lists
- May or may not be gzip compressed
- Filter by `list_uid` field to get items from specific list
- Response format: `{"result": [...]}`

**Item Structure (Complete):**
```json
{
  "uid": "61DFC31A-BCBF-4912-81E3-EEF8B061DFE2",
  "recipe_uid": null,
  "name": "flour",
  "order_flag": 231,
  "purchased": true,
  "aisle": "Baking Goods",
  "ingredient": "flour",
  "recipe": null,
  "instruction": "",
  "quantity": "",
  "separate": false,
  "aisle_uid": "12304D0F1A64F772E413322BD03445ADD546F7528D9628F999DBEE3B7C7819B7",
  "list_uid": "A25907D8-06EE-44AD-A4C7-9E50EE2B4D2C-26639-0000075C3E316007"
}
```

**Key Fields:**
- `uid`: Item unique ID (client-generated UUID4, uppercase)
- `name`: Item name
- `purchased`: Boolean - checked/purchased status
- `aisle`: Auto-assigned by Paprika based on `ingredient` or `name`
- `ingredient`: Lowercase version of item name
- `list_uid`: **Required** - specifies which grocery list item belongs to
- `updated_at` or `created`: Timestamp for change tracking

### Creating/Updating Items

**Critical Requirements:**
1. Data must be gzip-compressed JSON **array** (not object)
2. Send as multipart/form-data with field name `data`
3. Include all required fields
4. Must specify `list_uid` to target correct list
5. Client must generate UUID for new items

**Endpoint:** `POST /api/v2/sync/groceries/`

**Python Implementation:**
```python
import gzip
import json
import uuid

# Generate UID for new item
item_uid = str(uuid.uuid4()).upper()

# Create item with ALL fields
grocery_items = [{
    "uid": item_uid,
    "recipe_uid": None,
    "name": "Milk",
    "order_flag": 0,
    "purchased": False,
    "aisle": "",  # Leave empty - Paprika auto-assigns
    "ingredient": "milk",  # Lowercase name
    "recipe": None,
    "instruction": "",
    "quantity": "",
    "separate": False,
    "list_uid": "YOUR-LIST-UID-HERE"  # REQUIRED
}]

# Gzip compress
json_data = json.dumps(grocery_items).encode('utf-8')
compressed_data = gzip.compress(json_data)

# Send as multipart form
files = {'data': ('data', compressed_data, 'application/octet-stream')}
headers = {'Authorization': f'Bearer {token}'}
response = requests.post(url, files=files, headers=headers)

# Success response: {"result": true}
```

**Updating Items:**
- Use same POST endpoint and format
- Include existing `uid` in the item object
- Paprika updates item with matching UID
- Include full item structure (fetch first, modify, then upload)

### Deletion Behavior

**Critical Discovery:** True deletion NOT supported.

**DELETE Endpoint:** `DELETE /api/v2/sync/groceries/{uid}` returns 404

**Workaround:**
- Mark items as `purchased=True` to "soft delete"
- Items remain in list but appear as checked/purchased
- For sync: Track deleted items in local DB to avoid recreating

**Implications:**
- Deleted items still sync across devices as purchased
- Users must manually delete via Paprika app for true removal
- Sync engine should not recreate items marked as deleted

### Aisle Auto-Assignment

**Behavior:**
- Paprika automatically categorizes items by aisle
- Based on `ingredient` or `name` field
- Happens server-side when item created/updated
- Leave `aisle` field empty ("") when creating

**Important:**
- Do NOT overwrite aisle when syncing from Skylight
- Preserve Paprika's aisle assignments
- Only sync `name`, `purchased`, and timestamps

### Response Handling

**Gzip Compression:**
- Responses MAY be gzip compressed (not always)
- Check for gzip magic bytes: `\x1f\x8b`
- Gracefully handle both compressed and uncompressed

**Success Responses:**
- GET: `{"result": [...]}`
- POST: `{"result": true}`

**Error Responses:**
- `{"error": {"code": 0, "message": "Invalid data."}}`
- HTTP 401: Token expired, re-authenticate
- HTTP 404: Item/endpoint not found

### Custom Implementation

**Why Custom Client:**
- Kappari library doesn't expose grocery operations in public API
- Need full control over list targeting and item structure
- Simpler dependencies (just `requests` library)
- Direct access to reverse-engineered API

**Implementation:**
```python
from paprika_client import PaprikaClient

client = PaprikaClient(email, password)
client.authenticate()  # V1 auth with token caching

# Get available lists
lists = client.get_grocery_lists()
# Returns: [{"uid": "...", "name": "Test List", ...}, ...]

# Get list UID by name
list_uid = client.get_list_uid_by_name("Test List")

# Get items from specific list (filters by list_uid)
items = client.get_grocery_list("Test List")

# Add item to specific list
uid = client.add_item(name="Milk", checked=False, list_name="Test List")

# Update checked status
client.update_item(paprika_id=uid, checked=True)

# Remove item (marks as purchased)
client.remove_item(paprika_id=uid)
```

### Known Limitations & Behaviors

1. **No True Deletion:** Items can only be marked as purchased, not removed
2. **All-or-Nothing Sync:** GET groceries returns ALL items from ALL lists
3. **Gzip Inconsistency:** Responses sometimes compressed, sometimes not
4. **Multiple Lists:** Must filter items by `list_uid` client-side
5. **UUID Generation:** Client responsible for generating unique IDs
6. **Rate Limits:** Unknown - be conservative (60+ second intervals recommended)
7. **Unofficial API:** May break with app updates, no official documentation
8. **Token Expiration:** Unknown duration - handle 401 gracefully

### Phase 1 Implementation Status

✅ **Completed:**
- V1 authentication with HTTP Basic Auth
- Token caching and automatic refresh
- Grocery list discovery (`/v2/sync/grocerylists/`)
- List-specific item filtering
- Item creation with proper list targeting
- Item updates (checked status, name)
- Soft deletion (mark as purchased)
- Gzip compression for POST requests
- Gzip decompression for responses

✅ **Tested:**
- All CRUD operations verified with real Paprika account
- Items appear correctly in Paprika app
- List filtering works correctly
- Token caching persists across sessions
- Checked status sync works bidirectionally

---

## Skylight API Patterns

### Authentication
**Endpoint:** `POST https://api.ourskylight.com/api/sessions`

**Request Body:**
```json
{
  "user": {
    "email": "user@example.com",
    "password": "password"
  }
}
```

**Response:**
```json
{
  "user_id": 12345,
  "user_token": "abc123xyz..."
}
```

**Token Usage:**
- Encode as Base64: `userId:userToken`
- Example: `12345:abc123xyz` → Base64 encode → `MTIzNDU6YWJjMTIzeHl6`
- Use in Authorization header: `Token token="MTIzNDU6YWJjMTIzeHl6"`

### Finding Frame ID
Users need their frame_id for configuration.

**Endpoint:** `GET https://api.ourskylight.com/api/frames`

**Response:**
```json
{
  "frames": [
    {
      "id": "frame123",
      "name": "Smith Family Frame"
    }
  ]
}
```

Helper script `scripts/find_skylight_frame.py` will discover frame_id in Phase 2.

### Grocery List Operations

**Response Format:** JSON:API specification
- All responses use `data` wrapper with `attributes` object
- Need to parse: `response['data']['attributes']`

**List All Lists:**
- Endpoint: `GET /api/frames/{frameId}/lists`
- Find list by name matching (e.g., "Grocery List")

**Get List Items:**
- Endpoint: `GET /api/frames/{frameId}/lists/{listId}/items`
- Returns array of items with checked status

**Item Fields:**
- `id`: Unique identifier (use as skylight_id)
- `name`: Item name
- `checked`: Boolean checked status
- `created_at`: ISO 8601 timestamp
- `updated_at`: Last modification timestamp

### Write Operations (Implemented)

**✅ Implemented based on JSON:API conventions:**

**Create Item:**
- **Endpoint:** `POST /api/frames/{frameId}/lists/{listId}/items`
- **Headers:** `Authorization: Token token="<base64_token>"`, `Content-Type: application/json`
- **Request Format:**
```json
{
  "data": {
    "type": "list_items",
    "attributes": {
      "name": "Milk",
      "checked": false
    }
  }
}
```
- **Response:** JSON:API format with created item ID

**Update Item:**
- **Endpoint:** `PATCH /api/frames/{frameId}/lists/{listId}/items/{itemId}`
- **Headers:** `Authorization: Token token="<base64_token>"`, `Content-Type: application/json`
- **Request Format:**
```json
{
  "data": {
    "type": "list_items",
    "id": "{itemId}",
    "attributes": {
      "name": "Updated Milk",
      "checked": true
    }
  }
}
```
- **Response:** JSON:API format with updated item

**Delete Item:**
- **Endpoint:** `DELETE /api/frames/{frameId}/lists/{listId}/items/{itemId}`
- **Headers:** `Authorization: Token token="<base64_token>"`
- **Request:** No body required
- **Response:** Success status

**Implementation Notes:**
- Uses standard JSON:API format (`data.type`, `data.attributes`)
- Supports both name and checked status updates
- Delete operation requires finding the list ID first
- All operations tested and verified working

### Known Limitations
- API is unofficial/undocumented
- Write operations require reverse engineering
- Rate limits unknown
- May break with Skylight app updates

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
- Aisle field excluded from `SkylightListItem` model

### Deletion Handling
**Challenge:** Paprika doesn't support true deletion

**Solution:**
- Track deleted items in SQLite DB with `deleted` flag
- When item deleted in Skylight: Mark as deleted in DB, mark as purchased in Paprika
- When item deleted in Paprika (marked purchased): Mark as deleted in DB, delete from Skylight
- Don't recreate items marked as deleted during sync

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
- **Primary Research Method:** Browser DevTools network inspection (Phase 2)
- **Expected Format:** JSON:API specification
- **Key Finding:** Base64 token encoding for auth

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
   - Document any API discoveries in CLAUDE.md
   - Update README.md if setup process changed

3. **Verify Clean State**:
   - Run essential tests to ensure functionality still works
   - Check that no broken imports or references exist
   - Commit clean state before starting next phase

4. **File Organization**:
   - Keep only production-ready files and final working tests
   - Move research notes to CLAUDE.md if valuable
   - Remove duplicate or obsolete implementations

**Rationale**: Each phase generates many experimental files during development. Cleaning up prevents:
- Confusion about which files are authoritative
- Import errors from deleted dependencies
- Cluttered project structure
- Difficulty finding the correct implementation

### Phase Status Tracking

**Use PROJECT.md for all progress tracking**, not CLAUDE.md. CLAUDE.md should contain:
- API patterns and technical discoveries
- Implementation guidelines and best practices
- Research findings and workarounds
- Code examples and usage patterns

PROJECT.md should contain:
- Overall project status and milestones
- Phase completion tracking
- Architecture overview
- Current development state

---
