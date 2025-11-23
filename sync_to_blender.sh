#!/bin/bash

# Sync scorg_tools addon to Blender addons directory
# This script copies the scorg_tools directory to the Blender addons folder,
# replacing existing files and cleaning up __pycache__ folders

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SOURCE_DIR="$SCRIPT_DIR/scorg_tools"
TARGET_DIR="/mnt/c/Users/$USER/AppData/Roaming/Blender Foundation/Blender/3.6/scripts/addons/scorg_tools"

echo -e "\033[0;36mSCOrg.tools Addon Sync Script (WSL)\033[0m"
echo -e "\033[0;36m===================================\033[0m"
echo ""

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "\033[0;31mERROR: Source directory not found: $SOURCE_DIR\033[0m"
    exit 1
fi

echo -e "\033[0;33mSource: $SOURCE_DIR\033[0m"
echo -e "\033[0;33mTarget: $TARGET_DIR\033[0m"
echo ""

# Create target directory if it doesn't exist
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "\033[0;35mCreating target directory...\033[0m"
    mkdir -p "$TARGET_DIR"
fi

# Copy files using rsync
# -a: archive mode (recursive, preserves permissions, times, etc.)
# -v: verbose
# --delete: delete extraneous files from dest dirs (mirroring)
# --exclude: exclude files matching pattern
echo -e "\033[0;35mCopying files...\033[0m"

rsync -av --delete --exclude "__pycache__" --exclude "*.pyc" --exclude "*.pyo" "$SOURCE_DIR/" "$TARGET_DIR/"

if [ $? -eq 0 ]; then
    echo -e "\033[0;32m  Files copied successfully!\033[0m"
else
    echo -e "\033[0;31mERROR: Failed to copy files.\033[0m"
    exit 1
fi

echo ""
echo -e "\033[0;32mSync complete!\033[0m"
echo ""
echo -e "\033[0;33mNote: If Blender is running, you may need to:\033[0m"
echo -e "\033[0;33m  1. Disable and re-enable the addon, or\033[0m"
echo -e "\033[0;33m  2. Restart Blender\033[0m"
