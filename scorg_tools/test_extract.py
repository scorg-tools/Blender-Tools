# test_extract.py - Simple test script for extract_missing_files
import bpy
from scorg_tools import globals_and_threading
from scorg_tools import import_utils

def test_extract_single_file(file_path):
    """
    Test extract_missing_files with a single file path.
    
    Args:
        file_path: Path to the file to extract (relative to Data/, e.g. "Data/Objects/.../file.cga")
    """
    # Check if P4K is loaded
    if not globals_and_threading.p4k:
        print("ERROR: P4K not loaded. Please load Data.p4k first.")
        return
    
    # Get addon preferences
    prefs = bpy.context.preferences.addons["scorg_tools"].preferences
    
    # Check required paths
    if not prefs.extract_dir:
        print("ERROR: Extract directory not set in preferences.")
        return
    
    if not prefs.cgf_converter_path:
        print("ERROR: CGF converter path not set in preferences.")
        return
    
    # Call extract_missing_files with single file
    print(f"Testing extraction of: {file_path}")
    success_count, fail_count, report_lines = import_utils.SCOrg_tools_import.extract_missing_files(file_path, prefs)
    
    print(f"Results: {success_count} succeeded, {fail_count} failed")
    for line in report_lines:
        print(line)

# Example usage:
test_extract_single_file("Data/Objects/Spaceships/Ships/DRAK/Corsair/exterior/DRAK_Corsair_Elevator_Door_Ext_Upper.dae")