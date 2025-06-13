# panels.py
import bpy
from pathlib import Path # ADDED: Ensure Path is imported
# Import globals
from . import globals_and_threading

# Define the parent panel ID here, as it's used by the panel's poll method
PARENT_PANEL_BL_IDNAME = 'VIEW3D_PT_BlenderLink_Panel'

# Panel in the sidebar
class VIEW3D_PT_scorg_tools_panel(bpy.types.Panel):
    bl_label = "SCOrg.tools Blender utils"
    bl_idname = "VIEW3D_PT_scorg_tools_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SCOrg.tools"
    bl_parent_id = PARENT_PANEL_BL_IDNAME # Use the defined parent ID

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, PARENT_PANEL_BL_IDNAME)
    
    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__package__].preferences # Access addon preferences

        if bpy.context.preferences.view.show_developer_ui:
            layout.operator("view3d.reload", text="Reload Addon", icon='FILE_REFRESH')
        
        # Check if StarFab scene exists
        if 'StarFab' in bpy.data.scenes:
            layout.operator("view3d.make_instance_real", text="Make Instance Real", icon='OUTLINER_OB_GROUP_INSTANCE')
        else:
            # Determine if loading is in progress
            is_loading = globals_and_threading._loading_thread and globals_and_threading._loading_thread.is_alive()

            # State 1: P4K is currently loading in a background thread
            if is_loading:
                layout.label(text=prefs.p4k_load_message)
                row = layout.row(align=True)
                row.prop(prefs, "p4k_load_progress", text="")
                
                # Disable the load button while loading is in progress
                # Create a sub-layout (a new row or column) and set its 'enabled' property
                loading_button_row = layout.row()
                loading_button_row.enabled = False # This disables all UI elements within this row
                loading_button_row.operator("view3d.load_p4k_button", text="Loading...", icon='IMPORT', emboss=False)
                
            # State 2: P4K is NOT loaded (initial state or previous load failed)
            elif globals_and_threading.p4k is None:
                # Show message and progress bar if there's a message (e.g., error from previous load)
                if prefs.p4k_load_message:
                    layout.label(text=prefs.p4k_load_message)
                    row = layout.row(align=True)
                    row.prop(prefs, "p4k_load_progress", text="")
                # The button is enabled by default here as the layout is not explicitly disabled
                layout.operator("view3d.load_p4k_button", text="Load Data.p4k", icon='IMPORT')
            # State 3: P4K is successfully loaded
            else:
                # Clear any lingering load messages/progress from preferences
                prefs.p4k_load_message = ""
                prefs.p4k_load_progress = 0.0 
                
                layout.label(text=f"Loaded Ship: {globals_and_threading.ship_loaded}" if globals_and_threading.ship_loaded else "Click Check to find ship", icon='CHECKBOX_HLT' if globals_and_threading.ship_loaded else 'ERROR')
                layout.operator("view3d.refresh_button", text="Refresh Ship Info", icon='FILE_REFRESH')
            
            # --- Sections that should always be visible (unless in StarFab scene) ---
            layout.separator() # Separator for visual clarity
            
            # Check extract directory preference (always visible)
            extract_dir = prefs.extract_dir
            dir_path = Path(extract_dir)
            if not dir_path.is_dir() or extract_dir == "":
                layout.label(text="To import loadout, set Data Extract Directory in Preferences", icon='ERROR')

            # Utilities section (always visible)
            layout.label(text="Utilities")

            # --- Sections dependent on P4K being loaded ---
            if globals_and_threading.p4k:
                # Display ship loaded status and subsequent options
                if globals_and_threading.ship_loaded:
                    layout.separator()
                    
                    # Import missing loadout button
                    if dir_path.is_dir() and extract_dir != "":
                        layout.operator("view3d.import_loadout", text="Import loadout & mats", icon='IMPORT')
                    layout.separator()
                else:
                    # Don't show import by guid button if a ship is loaded
                    layout.operator("wm.get_guid_operator", text="Import by GUID", icon='IMPORT')

                if globals_and_threading.ship_loaded or globals_and_threading.item_loaded:
                    # Paints section
                    layout.label(text="Paints")
                    if globals_and_threading.button_labels:
                        for idx, label in enumerate(globals_and_threading.button_labels):
                            op = layout.operator("view3d.dynamic_button", text=label)
                            op.button_index = idx
                    else:
                        layout.label(text="No paints found for this ship.", icon='INFO')