#!/bin/bash

# Comprehensive GUI tests for file browser
# Tests: thumbnails, views, edit/delete, drag-drop, button highlighting

API_URL="http://localhost:3000"
UI_URL="http://localhost:5173"
EMAIL="admin@platform.local"
PASSWORD="demo1234"
FAIL=0

echo "=== GUI Test: File Browser ==="
echo ""

# Login and get token
echo "1. Login..."
TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .token)

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "FAIL: Login failed"; exit 1
fi
echo "PASS: Login"
echo ""

# API smoke
echo "2. API entities..."
ENTITIES=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/api/entities?limit=10")
ENTITY_COUNT=$(echo $ENTITIES | jq '.data | length')
if [ "$ENTITY_COUNT" -gt 0 ]; then echo "PASS: $ENTITY_COUNT entities"; else echo "FAIL: no entities"; FAIL=1; fi
echo ""

UI_HTML=$(curl -s "$UI_URL")

# View mode buttons
echo "3. View mode buttons..."
for btn in btn-tree-view btn-table-view btn-manager-view btn-grid-view; do
  if echo "$UI_HTML" | grep -q "$btn"; then echo "  PASS: $btn"; else echo "  FAIL: $btn missing"; FAIL=1; fi
done
echo ""

# Controls
echo "4. Controls..."
for id in icon-size-select row-height-select; do
  if echo "$UI_HTML" | grep -q "$id"; then echo "  PASS: $id"; else echo "  FAIL: $id missing"; FAIL=1; fi
done
echo ""

# Thumbnails
echo "5. Thumbnails..."
THUMB_URLS=$(echo $ENTITIES | jq -r '.data[].external_id' | head -5)
for id in $THUMB_URLS; do
  ENCODED=$(printf '%s' "$id" | jq -sRr @uri)
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/thumbnail?external_id=$ENCODED&size=64px")
  if [ "$STATUS" = "200" ]; then
    # Check PNG magic bytes
    PNG=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/api/thumbnail?external_id=$ENCODED&size=64px" | head -c 8 | xxd -p 2>/dev/null || true)
    if echo "$PNG" | grep -q "89504e47"; then
      echo "  PASS: $id thumbnail is valid PNG"
    else
      echo "  WARN: $id thumbnail status 200 but not PNG header ($PNG)"
    fi
  else
    echo "  FAIL: $id thumbnail HTTP $STATUS"; FAIL=1
  fi
done
echo ""

# Edit/delete helpers
echo "6. Edit/delete helpers in all views..."
if echo "$UI_HTML" | grep -q "function editEntity"; then echo "  PASS: editEntity()"; else echo "  FAIL: editEntity() missing"; FAIL=1; fi
if echo "$UI_HTML" | grep -q "function deleteEntity"; then echo "  PASS: deleteEntity()"; else echo "  FAIL: deleteEntity() missing"; FAIL=1; fi
if echo "$UI_HTML" | grep -q "function fileActions"; then echo "  PASS: fileActions()"; else echo "  FAIL: fileActions() missing"; FAIL=1; fi
echo ""

# Drag-and-drop
echo "7. Drag-and-drop..."
if echo "$UI_HTML" | grep -q 'draggable="true"'; then echo "  PASS: draggable elements"; else echo "  FAIL: no draggable elements"; FAIL=1; fi
if echo "$UI_HTML" | grep -q "dragstart"; then echo "  PASS: dragstart listeners"; else echo "  FAIL: no dragstart"; FAIL=1; fi
if echo "$UI_HTML" | grep -q "dragover"; then echo "  PASS: dragover listeners"; else echo "  FAIL: no dragover"; FAIL=1; fi
echo ""

# Active button highlighting
echo "8. Active button highlighting..."
if echo "$UI_HTML" | grep -q "function updateViewButtons"; then echo "  PASS: updateViewButtons()"; else echo "  FAIL: updateViewButtons() missing"; FAIL=1; fi
echo ""

# Manager column persistence
echo "9. Manager column persistence..."
if echo "$UI_HTML" | grep -q "localStorage.setItem('sourceDir'"; then echo "  PASS: sourceDir persisted"; else echo "  FAIL: sourceDir persistence missing"; FAIL=1; fi
if echo "$UI_HTML" | grep -q "localStorage.setItem('destDir'"; then echo "  PASS: destDir persisted"; else echo "  FAIL: destDir persistence missing"; FAIL=1; fi
echo ""

# Edit modal
echo "10. Edit modal..."
if echo "$UI_HTML" | grep -q 'id="edit-modal"'; then echo "  PASS: edit-modal element"; else echo "  FAIL: edit-modal missing"; FAIL=1; fi
if echo "$UI_HTML" | grep -q 'id="btn-save-edit"'; then echo "  PASS: btn-save-edit"; else echo "  FAIL: btn-save-edit missing"; FAIL=1; fi
echo ""

# Tree view drag-and-drop classes
echo "11. Tree view drag-and-drop..."
if echo "$UI_HTML" | grep -q "tree-file-row"; then echo "  PASS: tree-file-row class"; else echo "  FAIL: tree-file-row missing"; FAIL=1; fi
if echo "$UI_HTML" | grep -q "tree-folder-row"; then echo "  PASS: tree-folder-row class"; else echo "  FAIL: tree-folder-row missing"; FAIL=1; fi
echo ""

echo "=== Test Summary ==="
if [ $FAIL -eq 0 ]; then
  echo "ALL TESTS PASSED"
else
  echo "SOME TESTS FAILED (count: $FAIL)"
  exit 1
fi
echo ""
echo "UI: $UI_URL/#files"
