# __init__.py
bl_info = {
    "name": "SCOrg.tools",
    "author": "Star-Destroyer@scorg.tools",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > SCOrg.tools",
    "description": "Tools to supplement StarFab",
    "category": "3D View"
}
bl_idname = "scorg_tools"

import bpy
import os
import sys

# Add addon directory to sys.path to allow relative imports
if __package__ in sys.modules:
    addon_path = os.path.dirname(os.path.abspath(__file__))
    if addon_path not in sys.path:
        sys.path.append(addon_path)

# Import all modules
from . import globals_and_threading
from . import misc_utils
from . import tint_utils
from . import blender_utils
from . import import_utils
from . import operators
from . import panels # Keep this import, as we reference panels.VIEW3D_PT_scorg_tools_panel
from . import preferences

# Classes to register (EXCLUDE panels.VIEW3D_PT_scorg_tools_panel from here)
# This panel will be registered exclusively by the delayed_panel_registration timer.
classes = (
    operators.VIEW3D_OT_dynamic_button,
    operators.VIEW3D_OT_load_p4k_button,
    operators.VIEW3D_OT_refresh_button,
    operators.VIEW3D_OT_import_loadout,
    operators.VIEW3D_OT_add_modifiers,
    operators.VIEW3D_OT_make_instance_real,
    operators.VIEW3D_OT_import_by_guid,
    operators.GetGUIDOperator,
    preferences.SCOrg_tools_AddonPreferences,
    preferences.SCOrg_tools_OT_SelectP4K,
)

# --- Deferred Panel Registration Logic ---
_timer_retries = 0
_max_timer_retries = 30 # Increased retries to give StarFab more time to load
_retry_interval = 0.25 # Reduced interval for faster checks
PARENT_PANEL_BL_IDNAME = 'VIEW3D_PT_BlenderLink_Panel'
_panel_registered_successfully = False

def delayed_panel_registration():
    global _timer_retries
    global _panel_registered_successfully

    if _panel_registered_successfully:
        # Panel successfully registered and parent found in a previous run of this timer.
        # This condition helps stop the timer if it somehow wasn't unregistered.
        print("VIEW3D_PT_scorg_tools_panel already successfully registered and parent found. Stopping timer.")
        return None

    # Check if the parent panel exists
    if hasattr(bpy.types, PARENT_PANEL_BL_IDNAME):
        print(f"Parent panel '{PARENT_PANEL_BL_IDNAME}' found. Attempting to register VIEW3D_PT_scorg_tools_panel.")
        
        # If our panel is already registered but might have been registered incorrectly
        # (e.g., without the parent being ready), unregister it first to re-attempt parenting.
        if panels.VIEW3D_PT_scorg_tools_panel.is_registered:
            try:
                print("VIEW3D_PT_scorg_tools_panel was already registered. Unregistering to re-attempt parenting.")
                bpy.utils.unregister_class(panels.VIEW3D_PT_scorg_tools_panel)
            except Exception as e:
                # If unregistration fails (e.g., it's stuck), we might have a deeper issue.
                # Log error and stop trying for this session.
                print(f"Error unregistering VIEW3D_PT_scorg_tools_panel during retry: {e}")
                _panel_registered_successfully = False # Mark as failed to register correctly
                return None # Stop the timer

        # Now, try to register the panel. This is the only place it should be registered.
        try:
            bpy.utils.register_class(panels.VIEW3D_PT_scorg_tools_panel)
            _panel_registered_successfully = True
            print("VIEW3D_PT_scorg_tools_panel registered successfully with parent.")
            return None # Stop the timer, successful registration
        except Exception as e:
            # If registration fails even when parent is found, something else is wrong.
            print(f"Error registering VIEW3D_PT_scorg_tools_panel even with parent found: {e}")
            _timer_retries += 1
            if _timer_retries <= _max_timer_retries:
                print(f"Retrying registration in {_retry_interval} seconds (Attempt {_timer_retries}/{_max_timer_retries}).")
                return _retry_interval # Retry
            else:
                print(f"Max retries reached for VIEW3D_PT_scorg_tools_panel registration after error. Giving up.")
                return None # Stop the timer, giving up after max retries
    else:
        # Parent panel not found yet, increment retries and continue waiting
        _timer_retries += 1
        if _timer_retries <= _max_timer_retries:
            print(f"Parent panel '{PARENT_PANEL_BL_IDNAME}' not found. Retrying in {_retry_interval} seconds (Attempt {_timer_retries}/{_max_timer_retries}).")
            return _retry_interval 
        else:
            print(f"Failed to register VIEW3D_PT_scorg_tools_panel: Parent panel '{PARENT_PANEL_BL_IDNAME}' not found after {_max_timer_retries} attempts. Giving up.")
            return None


def register():
    # Register all classes EXCEPT the main panel (which is handled by the timer)
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"Error registering class {cls.__name__}: {e}")

    print("Attempting to register SCOrg_tools panel with deferred parenting...")
    # Register the timer for the delayed panel registration.
    # It must be persistent so it continues running until the parent is found.
    bpy.app.timers.register(delayed_panel_registration, first_interval=_retry_interval, persistent=True)


def unregister():
    global _panel_registered_successfully
    
    # Unregister the timer if it's still active
    if bpy.app.timers.is_registered(delayed_panel_registration):
        print("Unregistering delayed_panel_registration timer...")
        bpy.app.timers.unregister(delayed_panel_registration)
    
    # Ensure to stop the loading thread if it's still running
    if globals_and_threading._loading_thread and globals_and_threading._loading_thread.is_alive():
        print("Stopping background loading thread...")
        globals_and_threading._loading_thread = None # Clear reference

    # Unregister classes registered directly
    for cls in reversed(classes):
        print(f"unregister: {cls}")
        if cls.is_registered:
            try:
                bpy.utils.unregister_class(cls)
            except Exception as e:
                print(f"Error unregistering class {cls.__name__}: {e}")
        else:
            print(f"Skipping unregister for {cls.__name__} as it's not registered.")

    # Explicitly unregister the main panel if it was registered by the timer
    # Check if it exists before trying to unregister, to avoid errors if it never registered
    if hasattr(bpy.types, panels.VIEW3D_PT_scorg_tools_panel.bl_idname):
        if panels.VIEW3D_PT_scorg_tools_panel.is_registered:
            print("Unregistering VIEW3D_PT_scorg_tools_panel...")
            try:
                bpy.utils.unregister_class(panels.VIEW3D_PT_scorg_tools_panel)
            except Exception as e:
                print(f"Error during final unregistration of VIEW3D_PT_scorg_tools_panel: {e}")
    _panel_registered_successfully = False # Reset for next session

    # Clear global data
    globals_and_threading.clear_vars()