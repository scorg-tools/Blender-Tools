#!/bin/bash

# Setup paths
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ADDON_DIR_NAME="scorg_tools"
ADDON_PATH="$SCRIPT_DIR/$ADDON_DIR_NAME"
RELEASES_DIR="$SCRIPT_DIR/../releases"
INIT_PATH="$ADDON_PATH/__init__.py"

# Verify addon directory exists
if [ ! -d "$ADDON_PATH" ]; then
    echo "Error: Addon directory '$ADDON_DIR_NAME' not found in $SCRIPT_DIR"
    exit 1
fi

# Create releases directory if it doesn't exist
if [ ! -d "$RELEASES_DIR" ]; then
    mkdir -p "$RELEASES_DIR"
    echo "Created releases directory: $RELEASES_DIR"
fi

# Extract version and name from __init__.py
# We use python one-liner to parse the dictionary safely, as parsing python dicts with bash regex is fragile
VERSION_INFO=$(python3 -c "
import ast
import sys

try:
    with open('$INIT_PATH', 'r') as f:
        content = f.read()
    
    import re
    match = re.search(r'bl_info\s*=\s*(\{.*?\})', content, re.DOTALL)
    if match:
        info = ast.literal_eval(match.group(1))
        version = info.get('version', (0, 0, 0))
        name = info.get('name', '')
        print(f\"{version[0]}.{version[1]}.{version[2]}|{name}\")
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
")

if [ $? -ne 0 ]; then
    echo "Error: Could not parse bl_info from __init__.py"
    exit 1
fi

# Split version and name
VERSION_STR=$(echo "$VERSION_INFO" | cut -d'|' -f1)
NAME=$(echo "$VERSION_INFO" | cut -d'|' -f2)

# Check for beta in name (case insensitive)
ZIP_NAME="scorg_tools_v${VERSION_STR}"
if [[ "${NAME,,}" == *"beta"* ]]; then
    ZIP_NAME="${ZIP_NAME}_beta"
fi
ZIP_FILENAME="${ZIP_NAME}.zip"
ZIP_PATH="$RELEASES_DIR/$ZIP_FILENAME"

echo "Preparing release: $ZIP_FILENAME"
echo "Source: $ADDON_PATH"

# Create zip file
# We cd to the script dir so that scorg_tools is at the root of the zip
cd "$SCRIPT_DIR"

# Zip command:
# -r: recursive
# -q: quiet
# -x: exclude pattern
zip -r -q "$ZIP_PATH" "$ADDON_DIR_NAME" -x "*/__pycache__/*" "*.pyc" "*.pyo"

if [ $? -eq 0 ]; then
    echo "Success! Created $ZIP_FILENAME"
    echo "Location: $ZIP_PATH"
else
    echo "Error creating zip file."
    exit 1
fi
