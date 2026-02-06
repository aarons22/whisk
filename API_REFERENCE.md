# Paprika & Skylight API Reference

This document contains real API request/response examples for both Paprika Recipe Manager and Skylight Calendar APIs. This serves as the authoritative reference for API structure and prevents dependency on code comments.

For high-level implementation patterns and sync logic, refer to `./CLAUDE.md`.

---

## Critical API Discoveries

### Paprika Key Findings
- **V1 Authentication Required**: V2 can trigger "Unrecognized client" errors
- **HTTP Basic Auth + Form Data**: Unique authentication pattern
- **Gzip Response Handling**: Some responses compressed, some not
- **No True Deletion**: Only soft delete via `purchased=True` (groceries) or `in_trash=True` (recipes)
- **Client UUID Generation**: Must generate UUID4 (uppercase) for new items
- **Two-Step Recipe Fetch**: List endpoint returns only `{uid, hash}` pairs; must fetch each recipe individually
- **Hash-Based Change Detection**: Compare recipe hashes to detect changes without downloading full data

### Skylight Key Findings
- **Individual Deletion Broken**: Standard REST DELETE /items/{id} non-functional
- **Bulk Destroy Works**: Only `/list_items/bulk_destroy` endpoint functional for deletion
- **JSON:API Format**: All requests/responses follow JSON:API specification
- **Base64 Token Format**: Must encode as `base64(user_id:auth_token)`
- **Frame-Scoped Operations**: All operations require correct frame_id

---

## Paprika Recipe Manager API

### Base URL
- **Production**: `https://www.paprikaapp.com/api`
- **Authentication**: Bearer token (obtained via login)

### Authentication

#### Login (V1 - Recommended)
**Request:**
```http
POST /v1/account/login/
Authorization: Basic <base64(email:password)>
Content-Type: application/x-www-form-urlencoded

email=user@example.com&password=userpassword
```

**Response:**
```json
{
  "result": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
}
```

**Usage:**
- Use HTTP Basic Auth + form data
- More stable than V2, avoids "Unrecognized client" errors
- Token cached to `.paprika_token` with 600 permissions

---

### Grocery Lists

#### Get All Grocery Lists
**Request:**
```http
GET /v2/sync/grocerylists/
Authorization: Bearer <token>
```

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

#### Get All Grocery Items
**Request:**
```http
GET /v2/sync/groceries/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "result": [
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
  ]
}
```

**Key Fields:**
- `uid`: Item unique ID (client-generated UUID4, uppercase)
- `name`: Item display name
- `purchased`: Boolean - checked/purchased status
- `aisle`: Auto-assigned by Paprika based on `ingredient`
- `ingredient`: Lowercase version of item name
- `list_uid`: **Required** - specifies which grocery list item belongs to

#### Create/Update Grocery Items
**Request:**
```http
POST /v2/sync/groceries/
Authorization: Bearer <token>
Content-Type: multipart/form-data

data: <gzip-compressed JSON array>
```

**Request Data (before gzip compression):**
```json
[
  {
    "uid": "NEW-ITEM-UUID-HERE",
    "recipe_uid": null,
    "name": "Milk",
    "order_flag": 0,
    "purchased": false,
    "aisle": "",
    "ingredient": "milk",
    "recipe": null,
    "instruction": "",
    "quantity": "",
    "separate": false,
    "list_uid": "YOUR-LIST-UID-HERE"
  }
]
```

**Response:**
```json
{
  "result": true
}
```

**Critical Requirements:**
1. Data must be gzip-compressed JSON **array** (not object)
2. Send as multipart/form-data with field name `data`
3. Client must generate UUID for new items
4. Must specify `list_uid` to target correct list
5. Leave `aisle` empty - Paprika auto-assigns

#### Delete Grocery Items
**Request:**
```http
DELETE /v2/sync/groceries/{uid}
Authorization: Bearer <token>
```

**Response:**
```http
404 Not Found
```

**Note:** True deletion NOT supported. Use soft delete by setting `purchased: true`.

---

### Meal Plans

#### Get All Meal Plans
**Request:**
```http
GET /v2/sync/meals/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "result": [
    {
      "uid": "DA523295-931A-4A56-93C5-4A9B0A672C45",
      "recipe_uid": "07975578-DE1A-42AB-B184-6E8FCB9AB753",
      "date": "2026-02-01 00:00:00",
      "type": 0,
      "name": "Jordan Marsh's Blueberry Muffins",
      "order_flag": 2,
      "type_uid": "913D33C7FD39DB8C8C4514669B011F617D911345592CC77B309B812667959720",
      "scale": null,
      "is_ingredient": false
    },
    {
      "uid": "048DE1ED-BE02-4D76-BBFE-D6F1A6D0A327",
      "recipe_uid": "081835AE-B714-4A3D-97B3-81764AA96706",
      "date": "2026-02-01 00:00:00",
      "type": 1,
      "name": "Golden Get Well Soup",
      "order_flag": 1,
      "type_uid": "74B7DE10D8791D7B501CB5DC41365994F2CC80227B7CE5CB2548E24AF26DC939",
      "scale": null,
      "is_ingredient": false
    },
    {
      "uid": "8F5ECCFF-02DC-4DAB-9C20-22B8AB5D3444",
      "recipe_uid": "790369BB-A019-4148-B0CB-4D08C62F20D3",
      "date": "2026-02-02 00:00:00",
      "type": 2,
      "name": "Roasted Salmon with Marinated Olives and Potato Chips",
      "order_flag": 1,
      "type_uid": "216713D08860CFA0D9787EA5C6CEBC8A8F5B73777F91C904853AC234BB9DF642",
      "scale": null,
      "is_ingredient": false
    },
    {
      "uid": "TEST-SNACK",
      "recipe_uid": null,
      "date": "2026-02-01 00:00:00",
      "type": 3,
      "name": "Mixed Nuts",
      "order_flag": 0,
      "type_uid": "SNACK-TYPE-UID",
      "scale": null,
      "is_ingredient": false
    }
  ]
}
```

**Key Fields:**
- `uid`: Meal unique ID
- `recipe_uid`: Reference to recipe (null for text-only meals)
- `date`: Meal date in "YYYY-MM-DD HH:MM:SS" format
- `type`: **Numeric meal type** (see mapping table below)
- `name`: Meal display name
- `type_uid`: Meal category identifier
- `order_flag`: Display order within same type/date

**Meal Type Mapping:**
| Numeric Type | Meal Type | Description |
|-------------|-----------|-------------|
| 0           | breakfast | Morning meals |
| 1           | lunch     | Midday meals |
| 2           | dinner    | Evening meals |
| 3           | snack     | Snacks/appetizers |

---

### Recipes

The recipe API uses a two-step sync pattern: a lightweight list endpoint returns `{uid, hash}` pairs for change detection, and individual recipe details must be fetched one at a time.

**Sources:** [Matt Steele's Paprika API Gist](https://gist.github.com/mattdsteele/7386ec363badfdeaad05a418b9a1f30a), [paprika-recipes Python library](https://github.com/coddingtonbear/paprika-recipes), [paprika-rs Rust client](https://github.com/Syfaro/paprika-rs)

#### List All Recipes (Lightweight)
**Request:**
```http
GET /v2/sync/recipes/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "result": [
    {
      "uid": "07975578-DE1A-42AB-B184-6E8FCB9AB753",
      "hash": "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890"
    },
    {
      "uid": "081835AE-B714-4A3D-97B3-81764AA96706",
      "hash": "f6e5d4c3b2a1098765fedcba0987654321fedcba0987654321fedcba09876543"
    }
  ]
}
```

**Key Points:**
- Returns ONLY `uid` and `hash` pairs — NOT full recipe data
- Designed for efficient change detection: compare `hash` against cached values
- Must fetch individual recipes via `/sync/recipe/{uid}/` for full details
- V1 endpoint (`/v1/sync/recipes/`) also works with Basic Auth

#### Get Single Recipe (Full Details)
**Request:**
```http
GET /v2/sync/recipe/{uid}/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "result": {
    "uid": "07975578-DE1A-42AB-B184-6E8FCB9AB753",
    "name": "Jordan Marsh's Blueberry Muffins",
    "ingredients": "2 cups flour\n1/2 cup sugar\n2 tsp baking powder\n1/2 tsp salt\n1/3 cup butter\n1 egg\n1 cup milk\n1.5 cups blueberries",
    "directions": "1. Preheat oven to 375F.\n2. Mix dry ingredients.\n3. Cut in butter.\n4. Beat egg with milk, add to dry mix.\n5. Fold in blueberries.\n6. Fill muffin cups 2/3 full.\n7. Bake 25 minutes.",
    "description": "Classic blueberry muffin recipe from the Jordan Marsh department store",
    "notes": "Best with fresh blueberries. Can substitute frozen (don't thaw).",
    "nutritional_info": "",
    "servings": "12 muffins",
    "difficulty": "",
    "prep_time": "15 min",
    "cook_time": "25 min",
    "total_time": "40 min",
    "rating": 5,
    "categories": ["Breakfast", "Baking"],
    "source": "New York Times",
    "source_url": "https://cooking.nytimes.com/recipes/...",
    "image_url": "",
    "photo": "photo_filename.jpg",
    "photo_hash": "abc123def456...",
    "photo_large": null,
    "photo_url": "https://uploads.paprikaapp.com/...",
    "hash": "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
    "created": "2024-06-15 10:30:00",
    "on_favorites": true,
    "on_grocery_list": null,
    "in_trash": false,
    "is_pinned": false,
    "scale": null
  }
}
```

**Note:** The V1 endpoint (`/v1/sync/recipe/{uid}/`) also works with Basic Auth.

#### Recipe Object Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `uid` | `string` | UUID4 (uppercase) | Unique recipe identifier |
| `name` | `string` | `""` | Recipe title |
| `ingredients` | `string` | `""` | Newline-separated ingredient list |
| `directions` | `string` | `""` | Step-by-step cooking instructions |
| `description` | `string` | `""` | Recipe summary or notes |
| `notes` | `string` | `""` | Additional notes |
| `nutritional_info` | `string` | `""` | Nutritional data |
| `servings` | `string` | `""` | Serving quantity (free text) |
| `difficulty` | `string` | `""` | Recipe complexity level |
| `prep_time` | `string` | `""` | Preparation duration |
| `cook_time` | `string` | `""` | Cooking duration |
| `total_time` | `string` | `""` | Total time |
| `rating` | `int` | `0` | Star rating (0=unrated, 1-5) |
| `categories` | `list[string]` | `[]` | Category names |
| `source` | `string` | `""` | Attribution / source name |
| `source_url` | `string` | `""` | Original recipe URL |
| `image_url` | `string` | `""` | External image URL |
| `photo` | `string` | `""` | Photo filename |
| `photo_hash` | `string` | `""` | SHA256 hash of photo file |
| `photo_large` | `string/null` | `null` | Large photo filename |
| `photo_url` | `string/null` | `null` | Server-hosted photo URL (read-only) |
| `hash` | `string` | SHA256(UUID4) | Change detection hash (64-char hex) |
| `created` | `string` | Current datetime | Creation timestamp (`YYYY-MM-DD HH:MM:SS`) |
| `on_favorites` | `bool` | `false` | Whether recipe is favorited |
| `on_grocery_list` | `string/null` | `null` | Grocery list reference (if ingredients added) |
| `in_trash` | `bool` | `false` | Soft deletion flag |
| `is_pinned` | `bool` | `false` | Quick access marker |
| `scale` | `string/null` | `null` | Serving size adjustment factor |

#### Create/Update Recipe
**Request:**
```http
POST /v2/sync/recipe/{uid}/
Authorization: Bearer <token>
Content-Type: multipart/form-data

data: <gzip-compressed JSON recipe object>
```

**Response:**
```json
{
  "result": true
}
```

**Critical Requirements:**
1. Data must be gzip-compressed JSON of the **full recipe object** (not partial)
2. Send as `multipart/form-data` with field name `data`
3. Client must generate UUID4 (uppercase) for new recipes
4. Must include ALL fields — empty strings for unused text fields, `false` for booleans, `0` for rating, `[]` for categories
5. Update the `hash` field whenever recipe content changes (any 64-char hex string works)
6. Do **NOT** use the bulk endpoint (`POST /v2/sync/recipes/`) for creating recipes — it returns 500 errors. Use the individual `/sync/recipe/{uid}/` endpoint instead

#### Delete Recipe (Soft Delete Only)
**Method:** Set `in_trash: true` on the recipe object and POST the update.

```http
POST /v2/sync/recipe/{uid}/
Authorization: Bearer <token>
Content-Type: multipart/form-data

data: <gzip-compressed JSON with in_trash=true>
```

**Note:** No true DELETE endpoint exists for recipes.

#### Recommended Sync Workflow

1. **GET `/v2/sync/recipes/`** → get list of `{uid, hash}` pairs
2. **Compare hashes** against locally cached values
3. **GET `/v2/sync/recipe/{uid}/`** for each recipe with a changed or new hash
4. **Cache** the full recipe data and hash locally for future comparison

This two-step approach minimizes bandwidth — most syncs only need the lightweight list, and full recipe data is only fetched when changes are detected.

---

### Sync Status

#### Get Sync Status
**Request:**
```http
GET /v2/sync/status/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "result": {
    "recipes": 42,
    "categories": 5,
    "meals": 12,
    "groceries": 8,
    "groceryaisles": 15,
    "groceryingredients": 30,
    "grocerylists": 3,
    "mealtypes": 4,
    "menuitems": 0,
    "menus": 0,
    "pantry": 10,
    "photos": 25,
    "bookmarks": 2
  }
}
```

**Key Points:**
- Values are **change counters** that increment on modifications, not total counts
- Useful for smart syncing: only fetch a resource type if its counter has changed since last check
- Compare against previously stored values to detect which types need re-syncing

---

### Categories

#### List All Categories
**Request:**
```http
GET /v2/sync/categories/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "result": [
    {
      "uid": "CAT-UID-1",
      "name": "Breakfast",
      "order_flag": 0,
      "parent_uid": null
    },
    {
      "uid": "CAT-UID-2",
      "name": "Baking",
      "order_flag": 1,
      "parent_uid": null
    }
  ]
}
```

**Note:** Recipe `categories` field contains category names (strings), not UIDs.

---

## Skylight Calendar API

### Base URL
- **Production**: `https://api.ourskylight.com/api`
- **Authentication**: Base64-encoded token (userId:userToken)

### Authentication

#### Login
**Request:**
```http
POST /sessions
Content-Type: application/json

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
  "user_token": "abc123xyz789..."
}
```

**Usage:**
- Encode as Base64: `12345:abc123xyz789` → `MTIzNDU6YWJjMTIzeHl6Nzg5`
- Use in Authorization header: `Token token="MTIzNDU6YWJjMTIzeHl6Nzg5"`

#### Get Frames
**Request:**
```http
GET /frames
Authorization: Token token="<base64_token>"
```

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

---

### Lists (Grocery Lists)

#### Get All Lists for Frame
**Request:**
```http
GET /frames/{frameId}/lists
Authorization: Token token="<base64_token>"
```

**Response (JSON:API format):**
```json
{
  "data": [
    {
      "id": "list456",
      "type": "lists",
      "attributes": {
        "name": "Grocery List",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      }
    }
  ]
}
```

#### Get List Items
**Request:**
```http
GET /frames/{frameId}/lists/{listId}/items
Authorization: Token token="<base64_token>"
```

**Response:**
```json
{
  "data": [
    {
      "id": "item789",
      "type": "list_items",
      "attributes": {
        "name": "Milk",
        "checked": false,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      }
    }
  ]
}
```

#### Create List Item
**Request:**
```http
POST /frames/{frameId}/lists/{listId}/items
Authorization: Token token="<base64_token>"
Content-Type: application/json

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

**Response:**
```json
{
  "data": {
    "id": "new_item_id",
    "type": "list_items",
    "attributes": {
      "name": "Milk",
      "checked": false,
      "created_at": "2024-01-15T10:05:00Z",
      "updated_at": "2024-01-15T10:05:00Z"
    }
  }
}
```

#### Update List Item
**Request:**
```http
PATCH /frames/{frameId}/lists/{listId}/items/{itemId}
Authorization: Token token="<base64_token>"
Content-Type: application/json

{
  "data": {
    "type": "list_items",
    "id": "item789",
    "attributes": {
      "name": "Updated Milk",
      "checked": true
    }
  }
}
```

#### Delete List Item (Individual - Non-functional)
**Request:**
```http
DELETE /frames/{frameId}/lists/{listId}/items/{itemId}
Authorization: Token token="<base64_token>"
```

**Status:** ❌ **NOT WORKING** - Endpoint exists but deletion does not occur

#### Bulk Delete List Items (Working Solution)
**Request:**
```http
DELETE /frames/{frameId}/lists/{listId}/list_items/bulk_destroy
Authorization: Token token="<base64_token>"
Content-Type: application/json

{
  "ids": ["item_id_1", "item_id_2", "item_id_3"]
}
```

**Response:**
```http
200 OK
```

**Note:** Only the bulk destruction endpoint is functional for deleting items.

---

### Meals (Meal Sittings)

#### Get Meal Categories
**Request:**
```http
GET /frames/{frameId}/meals/categories
Authorization: Token token="<base64_token>"
```

**Response:**
```json
{
  "data": [
    {
      "id": "breakfast_category_id",
      "type": "meal_categories",
      "attributes": {
        "label": "Breakfast"
      }
    },
    {
      "id": "lunch_category_id",
      "type": "meal_categories",
      "attributes": {
        "label": "Lunch"
      }
    },
    {
      "id": "dinner_category_id",
      "type": "meal_categories",
      "attributes": {
        "label": "Dinner"
      }
    },
    {
      "id": "snacks_category_id",
      "type": "meal_categories",
      "attributes": {
        "label": "Snacks"
      }
    }
  ]
}
```

#### Get Meal Sittings (Date Range)
**Request:**
```http
GET /frames/{frameId}/meals/sittings?filter[date_from]=2024-01-15&filter[date_to]=2024-01-20&include=meal_category,meal_recipe
Authorization: Token token="<base64_token>"
```

**Response:**
```json
{
  "data": [
    {
      "id": "sitting123",
      "type": "meal_sitting",
      "attributes": {
        "summary": "Pancakes and Eggs",
        "date": "2024-01-15"
      },
      "relationships": {
        "meal_category": {
          "data": {
            "id": "breakfast_category_id",
            "type": "meal_category"
          }
        },
        "meal_recipe": {
          "data": {
            "id": "recipe456",
            "type": "meal_recipe"
          }
        }
      }
    }
  ],
  "included": [
    {
      "id": "breakfast_category_id",
      "type": "meal_category",
      "attributes": {
        "label": "Breakfast"
      }
    },
    {
      "id": "recipe456",
      "type": "meal_recipe",
      "attributes": {
        "summary": "Pancakes and Eggs Recipe"
      }
    }
  ]
}
```

**Key Fields:**
- `id`: Skylight meal sitting ID
- `attributes.summary`: Meal name/description
- `attributes.date`: Meal date (YYYY-MM-DD)
- `meal_category.label`: Meal type (Breakfast, Lunch, Dinner, Snacks)

#### Create Meal Sitting
**Request:**
```http
POST /frames/{frameId}/meals/sittings
Authorization: Token token="<base64_token>"
Content-Type: application/json

{
  "meal_recipe_id": null,
  "meal_category_id": "breakfast_category_id",
  "summary": "Oatmeal with Berries",
  "date": "2024-01-15"
}
```

**Response:**
```json
{
  "id": "new_sitting_id"
}
```

#### Update Meal Sitting
**Request:**
```http
PUT /frames/{frameId}/meals/sittings/{sittingId}
Authorization: Token token="<base64_token>"
Content-Type: application/json

{
  "meal_recipe_id": null,
  "meal_category_id": "breakfast_category_id",
  "summary": "Updated Oatmeal with Berries",
  "date": "2024-01-15"
}
```

#### Delete Meal Sitting
**Request:**
```http
DELETE /frames/{frameId}/meals/sittings/{sittingId}
Authorization: Token token="<base64_token>"
```

**Response:**
```http
200 OK
```

---

## API Behavior Notes

### Paprika Specific
1. **Gzip Compression**: Responses MAY be gzip compressed (check for `\x1f\x8b` magic bytes)
2. **All-or-Nothing**: GET endpoints return ALL items from ALL lists/categories
3. **Client-Generated IDs**: Must generate UUID4 (uppercase) for new items
4. **Soft Delete Only**: True deletion not supported — use `purchased: true` for groceries, `in_trash: true` for recipes
5. **Rate Limits**: Unknown - recommend 60+ second intervals
6. **Multiple Lists**: Must filter items by `list_uid` client-side
7. **Unofficial API**: May break with app updates, no official documentation
8. **Token Expiration**: Unknown duration - handle 401 gracefully
9. **Aisle Auto-Assignment**: Server assigns aisles based on `ingredient`/`name` - leave `aisle` field empty when creating
10. **Preserve Aisles**: Don't overwrite aisle field when syncing - only sync `name`, `purchased`, timestamps
11. **Two-Step Recipe Sync**: `/sync/recipes/` returns only `{uid, hash}` pairs; must fetch each recipe individually via `/sync/recipe/{uid}/`
12. **No Bulk Recipe Create**: `POST /v2/sync/recipes/` (plural) returns 500 errors; use individual `/sync/recipe/{uid}/` endpoint
13. **Recipe Hash**: Any 64-char hex string works; server does not strictly validate format. Update hash when content changes
14. **Full Object Required**: Recipe POST/update requires ALL fields, not partial updates

### Skylight Specific
1. **JSON:API Format**: All responses follow JSON:API specification
2. **Include Parameter**: Use `?include=` for relationship data
3. **Date Filtering**: Use `filter[date_from]` and `filter[date_to]` parameters
4. **Meal Categories**: Must map meal types to category IDs via `/meals/categories`
5. **Individual Deletion Broken**: Only bulk destroy endpoint works for list item deletion

### Common Patterns
- Both APIs use bearer token authentication
- Both support create, read, update, delete operations
- Error responses typically include descriptive messages
- Timestamps are in ISO 8601 format

---

## Rate Limiting & Best Practices

### Paprika
- **Conservative approach**: Wait 60+ seconds between requests
- **Token caching**: Cache bearer tokens until 401 response
- **Batch operations**: Use arrays for multiple item operations

### Skylight
- **Rate limits**: Unknown, be conservative
- **Base64 encoding**: Always encode userId:userToken for auth
- **JSON:API compliance**: Follow specification for request structure

---

## Troubleshooting

### Common Errors

**Paprika 401 Unauthorized:**
- Token expired, re-authenticate with V1 login

**Paprika 404 on DELETE:**
- True deletion not supported, use soft delete

**Paprika gzip compression issues:**
- Check for gzip magic bytes `\x1f\x8b` before decompressing
- Some responses are not compressed

**Paprika error responses:**
- Standard format: `{"error": {"code": 0, "message": "Invalid data."}}`
- Success responses: GET returns `{"result": [...]}`, POST returns `{"result": true}`

**Skylight Individual Delete Fails:**
- Individual DELETE /items/{id} endpoint non-functional
- Use bulk_destroy endpoint instead with array of IDs

**Skylight 404 on meal operations:**
- Check frame_id is correct
- Verify meal_category_id exists

**Gzip decompression errors:**
- Check for gzip magic bytes before decompressing
- Some responses are not compressed

---

*Last updated: 2026-02-06*
*Based on reverse engineering, actual API responses, and community implementations*