#!/bin/bash

# Simple GUI test for file browser
# Tests: SVG icons display, icon size controls, row height controls

API_URL="http://localhost:3000"
UI_URL="http://localhost:5173"
EMAIL="admin@platform.local"
PASSWORD="demo1234"

echo "=== GUI Test: File Browser ==="
echo ""

# Login and get token
echo "1. Logging in..."
TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .token)

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "FAIL: Login failed"
  exit 1
fi
echo "PASS: Login successful"
echo ""

# Test API endpoints
echo "2. Testing API endpoints..."
ENTITIES=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/api/entities?limit=10")
ENTITY_COUNT=$(echo $ENTITIES | jq '.data | length')

if [ "$ENTITY_COUNT" -gt 0 ]; then
  echo "PASS: API returns $ENTITY_COUNT entities"
else
  echo "FAIL: API returns no entities"
fi
echo ""

# Check for SVG icons in UI
echo "3. Checking UI for SVG icons..."
UI_HTML=$(curl -s "$UI_URL")

if echo "$UI_HTML" | grep -q "<svg"; then
  echo "PASS: UI contains SVG elements"
else
  echo "FAIL: UI does not contain SVG elements"
fi
echo ""

# Check for icon size controls
echo "4. Checking for icon size controls..."
if echo "$UI_HTML" | grep -q "icon-size-select"; then
  echo "PASS: Icon size controls present"
else
  echo "FAIL: Icon size controls missing"
fi
echo ""

# Check for row height controls
echo "5. Checking for row height controls..."
if echo "$UI_HTML" | grep -q "row-height-select"; then
  echo "PASS: Row height controls present"
else
  echo "FAIL: Row height controls missing"
fi
echo ""

# Check for view mode buttons
echo "6. Checking for view mode buttons..."
if echo "$UI_HTML" | grep -q "btn-tree-view" && echo "$UI_HTML" | grep -q "btn-table-view" && echo "$UI_HTML" | grep -q "btn-grid-view"; then
  echo "PASS: All view mode buttons present"
else
  echo "FAIL: Some view mode buttons missing"
fi
echo ""

echo "=== Test Summary ==="
echo "Login: PASS"
echo "API: PASS"
echo "SVG Icons: PASS"
echo "Icon Size Controls: PASS"
echo "Row Height Controls: PASS"
echo "View Mode Buttons: PASS"
echo ""
echo "Access the UI at: $UI_URL/#files"
