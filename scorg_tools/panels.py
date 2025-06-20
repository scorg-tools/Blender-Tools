# panels.py
import bpy
from pathlib import Path # ADDED: Ensure Path is imported
# Import globals
from . import globals_and_threading
from . import misc_utils

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
    
    # Class variable to track last known width for responsive updates
    _last_known_width = None

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, PARENT_PANEL_BL_IDNAME)
    
    def draw(self, context):
        layout = self.layout
        
        # Check if panel width has changed and force redraw if needed
        current_width = self.get_current_region_width()
        if current_width != self.__class__._last_known_width:
            self.__class__._last_known_width = current_width
            # Force a redraw by tagging the region
            try:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()
                                break
                        break
            except:
                pass

        prefs = context.preferences.addons[__package__].preferences # Access addon preferences
        layout.label(text="v" + misc_utils.SCOrg_tools_misc.get_addon_version(), icon='INFO')
        if bpy.context.preferences.view.show_developer_ui:
            layout.operator("view3d.reload", text="Reload Addon", icon='FILE_REFRESH')
        
        # Always show progress/status if there's something to display
        if prefs.p4k_load_message or prefs.p4k_load_progress > 0:
            layout.label(text=prefs.p4k_load_message)
            row = layout.row(align=True)
            row.prop(prefs, "p4k_load_progress", text="", slider=True)
            layout.separator()
        
        # Check if StarFab scene exists
        if 'StarFab' in bpy.data.scenes:
            layout.operator("view3d.make_instance_real", text="Make Instance Real", icon='OUTLINER_OB_GROUP_INSTANCE')
        else:
            # Determine if loading is in progress
            is_loading = globals_and_threading._loading_thread and globals_and_threading._loading_thread.is_alive()

            # State 1: P4K is currently loading in a background thread
            if is_loading:
                # Progress is already shown above, just show the disabled button
                loading_button_row = layout.row()
                loading_button_row.enabled = False # This disables all UI elements within this row
                loading_button_row.operator("view3d.load_p4k_button", text="Loading...", icon='IMPORT', emboss=False)
                
            # State 2: P4K is NOT loaded (initial state or previous load failed)
            elif globals_and_threading.p4k is None:
                # The button is enabled by default here as the layout is not explicitly disabled
                layout.operator("view3d.load_p4k_button", text="Load Data.p4k", icon='IMPORT')
            # State 3: P4K is successfully loaded
            else:
                layout.label(text=f"Loaded Ship: {globals_and_threading.ship_loaded}" if globals_and_threading.ship_loaded else "Click Check to find ship", icon='CHECKBOX_HLT' if globals_and_threading.ship_loaded else 'ERROR')
                layout.operator("view3d.refresh_button", text="Refresh Ship Info", icon='FILE_REFRESH')
            
            # --- Sections that should always be visible (unless in StarFab scene) ---
            layout.separator() # Separator for visual clarity
            
            # Check extract directory preference (always visible)
            extract_dir = prefs.extract_dir
            dir_path = Path(extract_dir)
            if not dir_path.is_dir() or extract_dir == "":
                __class__.draw_wrapped_text(layout, message="Please set the Data Extract Directory in the addon preferences.", icon='ERROR')
                return

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

    def get_current_region_width(self):
        """Get the current UI region width"""
        try:
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'UI':
                            return region.width
        except:
            pass
        return None

    @staticmethod
    def draw_wrapped_text(layout, message, icon='NONE', width=None):
        """
        Draw a message across multiple labels with word wrapping.
        Only the first label gets the icon.
        
        Args:
            layout: The layout object to draw to
            message (str): The message to display
            icon (str): The icon to show on the first line only
            width (int): Character width per line. If None, auto-detect from context.
        """
        if not message:
            return
        
        # Auto-detect width if not provided - recalculate each time for responsive resizing
        if width is None:
            try:
                # Get the current region width
                if bpy.context.region:
                    region_width = bpy.context.region.width
                    effective_width = region_width - 90  # Deduct margin for UI elements
                    char_width = 7.9 # Average character width in pixels
                    estimated_chars = int(effective_width / char_width)
                    width = max(10, estimated_chars) # Ensure at least 10 characters wide
                else:
                    width = 20  # Conservative fallback
            except:
                width = 20
        
        # Account for icon taking up space on first line
        first_line_width = width - 5 if icon != 'NONE' else width
        
        words = message.split()
        lines = []
        current_line = ""
        is_first_line = True
        
        for word in words:
            # Use different width for first line if it has an icon
            current_width = first_line_width if is_first_line else width
            # Check if adding this word would exceed the width
            test_line = current_line + (" " if current_line else "") + word
            if len(test_line) <= current_width:
                current_line = test_line
            else:
                # Current line is full, start a new one
                if current_line:
                    lines.append(current_line)
                    is_first_line = False
                current_line = word        
        # Add the last line if it has content
        if current_line:
            lines.append(current_line)
        # Draw the lines
        for i, line in enumerate(lines):
            if i == 0:
                # First line with icon
                layout.label(text=line, icon=icon)
            else:
                # Subsequent lines without icon
                layout.label(text=line)