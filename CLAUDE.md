# Paprika-Skylight Sync Implementation Patterns

## Overview
This document captures implementation patterns, API research findings, and technical decisions for the grocery list sync automation.

## Paprika API Patterns

### Authentication
The Paprika API has two versions for authentication:

**V1 Authentication** (recommended):
- Endpoint: `https://www.paprikaapp.com/api/v1/account/login/`
- Method: POST with email/password
- Returns: Bearer token directly
- More stable, avoids "Unrecognized client" errors

**V2 Authentication** (avoid):
- Endpoint: `https://www.paprikaapp.com/api/v2/account/login/`
- Can trigger "Unrecognized client" errors on repeated auth
- Requires more complex token handling

### Token Caching
To avoid authentication issues:
1. Cache bearer token to file (`.paprika_token`)
2. Reuse cached token until it expires (401 response)
3. Only re-authenticate on token expiration
4. Token format: `Bearer {token_string}`

### Grocery List Operations

**Endpoints:**
- List all grocery items: `GET /api/v2/sync/groceries/`
- Add item: `POST /api/v2/sync/groceries/`
- Update item: `POST /api/v2/sync/groceries/{uid}`
- Delete item: `DELETE /api/v2/sync/groceries/{uid}`

**Response Format:**
- Gzip compressed JSON
- Need to decompress before parsing
- Use `Accept-Encoding: gzip` header

**Aisle Handling:**
- Paprika automatically assigns aisles when items are added
- Aisle field is auto-populated based on item name/category
- No need to specify aisle in API calls
- Do NOT overwrite aisle field when syncing from Skylight

**Item Fields:**
- `uid`: Unique identifier (use as paprika_id)
- `name`: Item name (required)
- `purchased`: Boolean (maps to checked status)
- `aisle`: Auto-assigned category
- `created`: Timestamp (ISO 8601 format)
- `updated_at`: Last modification timestamp

### Custom Implementation
We implemented a custom Paprika API client using the `requests` library directly:

**Why custom implementation:**
- Kappari library doesn't expose grocery list operations in its public API
- Paprika API is reverse-engineered and not officially documented
- Custom implementation gives us full control over grocery CRUD operations
- Simpler dependency management (just requests + standard library)

**Implementation approach:**
- Direct REST API calls to `/api/v2/sync/groceries/`
- V1 authentication endpoint for stability
- Token caching with file permissions (chmod 600)
- Gzip response decompression
- Automatic token refresh on 401 errors

**Usage Example:**
```python
from paprika_client import PaprikaClient

client = PaprikaClient(email, password)
client.authenticate()  # V1 authentication with token caching

# Get grocery items
items = client.get_grocery_list("Test List")

# Add item (aisle auto-assigned)
uid = client.add_item(name="Milk", checked=False)

# Update checked status
client.update_item(paprika_id=uid, checked=True)

# Delete item
client.remove_item(paprika_id=uid)
```

### Known Limitations
- API is reverse-engineered, not officially documented
- May break with Paprika app updates
- Rate limits unknown (be conservative)
- Token expiration time not documented (cache and retry on 401)

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

Use helper script `scripts/find_skylight_frame.py` to discover frame_id.

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

### Write Operations (Research Needed)

**⚠️ NOT YET DOCUMENTED - Requires Research in Phase 2:**

These endpoints need to be discovered via browser DevTools network inspection:

1. **Create Item:** Likely `POST /api/frames/{frameId}/lists/{listId}/items`
2. **Update Item:** Likely `PATCH /api/frames/{frameId}/lists/{listId}/items/{itemId}`
3. **Delete Item:** Likely `DELETE /api/frames/{frameId}/lists/{listId}/items/{itemId}`

**Research Approach:**
1. Open Skylight web app in browser
2. Open DevTools → Network tab
3. Add/edit/delete items in UI
4. Inspect HTTP requests to find endpoints and payload formats
5. Document JSON:API format requirements
6. Test endpoints with curl/Postman
7. Implement in `skylight_client.py`

**Expected JSON:API Format:**
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

### Known Limitations
- API is unofficial/undocumented
- Write operations not publicly known (requires reverse engineering)
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
- Works well for single-user use case

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
- Aisle field excluded from `GroceryItem` model

### Change Detection Algorithm

**Three-way comparison:**
1. **Last Known State** (from SQLite DB)
2. **Current Paprika State** (from API)
3. **Current Skylight State** (from API)

**Change Types:**
- **Addition:** Item exists in system but not in DB
- **Deletion:** Item in DB but missing from system
- **Modification:** Item timestamp changed since last sync
- **Conflict:** Both timestamps changed since last sync

**State Transitions:**
```
Item added in Paprika only → Create in Skylight, add to DB
Item added in Skylight only → Create in Paprika, add to DB
Item deleted from Paprika → Delete from Skylight, remove from DB
Item deleted from Skylight → Delete from Paprika, remove from DB
Item modified in Paprika → Update Skylight
Item modified in Skylight → Update Paprika
Item modified in both → Compare timestamps, apply newer change
```

### SQLite Schema Design

**Rationale:**
- Track last-known state to detect changes
- Store IDs from both systems for mapping
- Timestamps enable conflict resolution
- Unique constraint on `item_name` prevents duplicates

**Schema:**
```sql
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    paprika_id TEXT,
    skylight_id TEXT,
    checked INTEGER DEFAULT 0,  -- Boolean: 0=unchecked, 1=checked
    paprika_timestamp TEXT,      -- ISO 8601 format
    skylight_timestamp TEXT,     -- ISO 8601 format
    last_synced_at TEXT,         -- ISO 8601 format
    UNIQUE(item_name)
);
```

**Why SQLite:**
- Lightweight, no server needed
- ACID transactions for data integrity
- Persists across restarts
- Single file for easy backup
- Built into Python standard library

---

## Research Sources

### Paprika
- **Kappari Library:** https://github.com/mwaddoups/kappari
- **Paprika API Reverse Engineering:** Various GitHub repos with Paprika integrations
- **Key Finding:** V1 auth more stable than V2

### Skylight
- **Unofficial API Documentation:** Limited community resources
- **Primary Research Method:** Browser DevTools network inspection
- **Key Finding:** Uses JSON:API specification

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

### Logging Philosophy
- **INFO:** Sync start/complete, items synced count
- **WARNING:** Conflict resolutions, retry attempts
- **ERROR:** API failures, data inconsistencies
- **DEBUG:** Full request/response details (no credentials)

### Security Considerations
- Never log credentials or tokens
- Store .env with restrictive permissions (chmod 600)
- Cache tokens securely (not world-readable)
- Validate .env exists before starting daemon

---

## Future Improvements (Out of Scope)
- Web UI for monitoring sync status
- Support for multiple grocery lists simultaneously
- Manual conflict resolution (prompt user instead of automatic)
- Quantity and notes field sync
- Real-time sync via webhooks (if APIs support)
- Multi-user conflict resolution (family sharing scenarios)

---

*This document will be updated as implementation progresses and new API patterns are discovered.*
