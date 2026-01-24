# Paprika Delete Operation Research Findings

**Date**: 2026-01-24
**Status**: Research Complete - Implementation Deferred
**Next Phase**: TBD - Requires full sync endpoint implementation

---

## 🔍 **Major Discovery: Paprika Delete Mechanism**

### **Critical Finding**
Paprika deletion is **NOT** an individual item operation. It's a **full grocery list sync operation**.

### **Actual Delete Process**
When a user deletes ONE item in Paprika:

1. **GET** `/api/v2/sync/groceries/` → Fetch ALL items from ALL grocery lists
2. **Client-side filtering** → Remove deleted item from the complete array
3. **POST** `/api/v2/sync/groceries/` → Send entire updated array back
4. **Server replacement** → Paprika replaces ALL grocery state with provided array

### **Evidence**
- ✅ Charles proxy capture shows POST to `/api/v2/sync/groceries/` (not individual DELETE)
- ✅ GET response shows 669+ items from ALL grocery lists
- ✅ DELETE `/groceries/{id}` returns 404 - endpoint doesn't exist
- ✅ Sync endpoint accepts complete arrays and replaces full state

### **Performance Implications**
- **Heavy operation**: Every delete = full state sync (200KB+ data)
- **Network intensive**: All grocery items fetched and posted for single deletion
- **All-or-nothing**: Must preserve ALL other items exactly or risk data loss

---

## 🧪 **Test Protocol for Future Implementation**

### **Why Testing is Required**
Current sync logic is fundamentally broken due to incorrect assumptions about Paprika API. The sync endpoint approach is **completely different** from our current individual-item-based logic.

### **Test Objectives**
1. **Prove true deletion works** via sync endpoint
2. **Verify production data safety** (preserve 668+ production items)
3. **Validate complete state replacement** model
4. **Confirm Phase 6 architecture viability**

### **Safe Test Protocol**

#### **Pre-Test Setup**
```bash
# 1. Create backup
python scripts/ultra_safe_paprika_test.py
# Creates: paprika_ultra_safe_backup_YYYYMMDD_HHMMSS.json

# 2. Test only affects items with "test" or "sync" in name
# 3. Requires triple confirmation: SAFE → DELETE → PROCEED
```

#### **Test Execution**
```python
# Current test item ready: "ultra_sync_test_item"
# Will delete ONLY this test item
# Will preserve ALL 668+ production items unchanged

# Safety measures:
- Full backup created automatically
- Only deletes items with "test"/"sync" in name
- Triple confirmation required
- Complete state restoration available
```

#### **Verification Steps**
1. Confirm test item deleted from Paprika
2. Verify ALL production items unchanged
3. Check total item count decreased by exactly 1
4. Test restoration if needed: `python scripts/restore_paprika_backup.py <backup_file>`

### **Test Files Ready**
- ✅ `scripts/ultra_safe_paprika_test.py` - Main test with safety protocols
- ✅ `scripts/restore_paprika_backup.py` - Restoration capability
- ✅ `scripts/show_test_plan.py` - Non-destructive preview
- ✅ Backup files created: `paprika_ultra_safe_backup_20260124_133316.json`

---

## 🏗️ **Phase 6 Architecture Implications**

### **Required Changes**
1. **Complete rewrite of delete operations** - use sync endpoint instead of individual DELETEs
2. **State caching** - avoid repeated full-list GETs for performance
3. **Batch operations** - minimize full sync operations
4. **Production data protection** - ensure ALL non-target items preserved exactly

### **New PaprikaClient.remove_item() Design**
```python
def remove_item(self, paprika_id):
    """Delete item using full-sync approach"""
    # 1. GET all items from ALL grocery lists
    all_items = self._get_all_grocery_items()

    # 2. Filter out the deleted item
    updated_items = [item for item in all_items
                    if item['uid'] != paprika_id]

    # 3. POST complete updated array
    return self._sync_complete_grocery_state(updated_items)
```

### **Performance Considerations**
- **Cache full state** to minimize GET requests
- **Validate item existence** before attempting sync
- **Handle large payloads** (200KB+ gzipped JSON arrays)
- **Error recovery** - restoration from cached state if sync fails

---

## 📋 **Implementation Checklist for Future Phase**

### **Phase 6A: Delete Operation Redesign**
- [ ] Run ultra-safe test to prove sync endpoint deletion works
- [ ] Implement new `_get_all_grocery_items()` method
- [ ] Implement new `_sync_complete_grocery_state()` method
- [ ] Rewrite `PaprikaClient.remove_item()` using sync approach
- [ ] Add state caching to minimize GET requests
- [ ] Add comprehensive error handling and rollback

### **Phase 6B: Sync Engine Integration**
- [ ] Update sync engine to use new delete mechanism
- [ ] Implement bidirectional delete mapping:
  - Skylight delete → Paprika sync operation (mark as deleted in our DB)
  - Paprika delete (via sync) → Skylight true delete
- [ ] Add delete operation batching for performance
- [ ] Update state management to track deletion intentions

### **Phase 6C: Testing & Validation**
- [ ] Test with real grocery data (using test lists)
- [ ] Validate production data protection
- [ ] Performance testing with large item counts
- [ ] Bidirectional delete sync testing

---

## ⚠️ **Limitations & Accepted Behavior**

### **Asymmetric Delete Handling**
Due to fundamental API differences between Paprika and Skylight:

- **Paprika → Skylight**: ✅ **Will work**
  - Paprika deletion (sync operation) → Delete corresponding Skylight item

- **Skylight → Paprika**: ❌ **Cannot implement true deletion**
  - Skylight deletion → Paprika item remains (marked as purchased/checked)
  - This is **accepted limitation** due to Paprika's sync-only delete model

### **User Experience Impact**
- Users deleting items in Skylight will see them "checked off" in Paprika (not removed)
- Users deleting items in Paprika will see them disappear from Skylight
- This asymmetry is **documented and accepted** due to API constraints

### **Performance Impact**
- Paprika deletions will be slower (full sync operation)
- Network usage higher for Paprika operations
- Skylight deletions remain fast (direct DELETE API)

---

## 🎯 **Current Status**

### **Research**: ✅ **Complete**
- Paprika delete mechanism fully understood
- Safe test protocol developed and ready
- Implementation strategy designed

### **Testing**: ⏸️ **Deferred**
- Ultra-safe test ready to execute
- Production data protection verified
- Awaiting decision on implementation timing

### **Implementation**: ⏸️ **Future Phase TBD**
- Architecture redesign required for Phase 6
- Current sync engine remains non-functional for deletions
- Will require 2-3 development sessions when implemented

---

**Next Decision Point**: When to execute test and implement Phase 6 delete redesign.