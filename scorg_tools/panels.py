# panels.py
import bpy
from pathlib import Path # ADDED: Ensure Path is imported
import os
# Import globals
from . import globals_and_threading
from . import globals_and_threading
from . import misc_utils
from . import import_utils

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
    # Cache for applied tint index to avoid expensive lookups on every redraw
    _cached_applied_tint_index = None
    _cache_valid = False

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, PARENT_PANEL_BL_IDNAME)
    
    @classmethod
    def get_cached_applied_tint_index(cls):
        """Get the applied tint index with caching to avoid expensive lookups on every redraw"""
        # Check if cache is still valid
        if cls._cache_valid and cls._cached_applied_tint_index is not None:
            return cls._cached_applied_tint_index
        
        # Cache is invalid or doesn't exist, update it
        try:
            from . import tint_utils
            cls._cached_applied_tint_index = tint_utils.SCOrg_tools_tint.get_applied_tint_number()
            cls._cache_valid = True
        except Exception as e:
            # If there's an error, don't cache and return None
            cls._cached_applied_tint_index = None
            cls._cache_valid = False
            
        return cls._cached_applied_tint_index
    
    @classmethod
    def invalidate_tint_cache(cls):
        """Invalidate the tint cache to force a refresh on next access"""
        cls._cache_valid = False
        cls._cached_applied_tint_index = None
    
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
        
        # Version and preferences in two columns
        row = layout.row()
        # Always use a fixed split to ensure consistent button positioning
        split = row.split(factor=0.7)  # Version takes 70% of space
        
        # Version column (left, takes most space)
        version_col = split.column()
        # display the addon and Blender version
        blender_version = f"{bpy.app.version[0]}.{bpy.app.version[1]}.{bpy.app.version[2]}"
        version_col.label(text="v" + misc_utils.SCOrg_tools_misc.get_addon_version() + " (" + blender_version+")")
        
        # Preferences button column (right, fixed size)
        prefs_col = split.column()
        prefs_row = prefs_col.row(align=True)
        prefs_row.alignment = 'RIGHT'  # Force right alignment
        # Add reload button if developer UI is enabled
        if bpy.context.preferences.view.show_developer_ui:
            prefs_row.operator("view3d.reload", text="", icon='FILE_REFRESH')
        prefs_row.operator("view3d.open_preferences", text="", icon='PREFERENCES')
        
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
                layout.label(text=f"Loaded Ship: {globals_and_threading.ship_loaded}" if globals_and_threading.ship_loaded else "Click Refresh to find ship", icon='CHECKBOX_HLT' if globals_and_threading.ship_loaded else 'ERROR')
                layout.operator("view3d.refresh_button", text="Refresh Ship Info", icon='FILE_REFRESH')
            
            # --- Sections that should always be visible (unless in StarFab scene) ---
            layout.separator() # Separator for visual clarity
            
            # Export Missing button and debug info (always visible)
            # MOVED: Now inside p4k check below

            # Check extract directory preference (always visible)
            extract_dir = prefs.extract_dir
            dir_path = Path(extract_dir)
            if not dir_path.is_dir() or extract_dir == "":
                __class__.draw_wrapped_text(layout, message="Please set the Data Extract Directory in the addon preferences.", icon='ERROR')
                return

            # Check converter paths if extraction is enabled
            if prefs.extract_missing_files:
                cgf_path = prefs.cgf_converter_path
                tex_path = prefs.texconv_path
                
                missing_converters = []
                if not cgf_path or not Path(cgf_path).is_file() or not cgf_path.lower().endswith(".exe"):
                    missing_converters.append("CGF Converter")
                
                if not tex_path or not Path(tex_path).is_file() or not tex_path.lower().endswith(".exe"):
                    missing_converters.append("TexConv")
                
                if missing_converters:
                    msg = f"Warning: {', '.join(missing_converters)} required for extraction. Please set in preferences."
                    __class__.draw_wrapped_text(layout, message=msg, icon='ERROR')

            # Utilities section (always visible)
            layout.label(text="Utilities")

            # Show Missing Files Button (if any)
            if import_utils.SCOrg_tools_import.missing_files:
                # Sort the files for display
                sorted_files = sorted(import_utils.SCOrg_tools_import.missing_files, key=str.lower)
                
                op = layout.operator("scorg.text_popup", text="Show Missing Files", icon='ERROR')
                op.text_content = "\n".join(sorted_files)
                op.header_text = "The following files were missing, please extract them with StarFab, under Data -> Data.p4k:"
                op.is_extraction_popup = True
                layout.separator()

            # --- Sections dependent on P4K being loaded ---
            if globals_and_threading.p4k:
                # Display ship loaded status and subsequent options
                if globals_and_threading.ship_loaded:
                    layout.separator()
                    
                    # Import missing loadout button
                    if dir_path.is_dir() and extract_dir != "":
                        layout.operator("view3d.import_loadout", text="Import loadout & mats", icon='IMPORT')
                        layout.operator("view3d.separate_decals", text="Separate Decals", icon='MOD_DISPLACE')
                    layout.separator()
                else:
                    # Don't show import by guid button if a ship is loaded
                    layout.operator("wm.get_guid_operator", text="Import by GUID", icon='IMPORT')

                if globals_and_threading.ship_loaded or globals_and_threading.item_loaded:
                    # Paints section
                    layout.label(text="Paints")
                    if globals_and_threading.button_labels:
                        # Get the currently applied tint index for highlighting (cached to avoid expensive lookups)
                        applied_tint_index = self.get_cached_applied_tint_index()
                        
                        for idx, label in enumerate(globals_and_threading.button_labels):
                            # Highlight the currently applied tint
                            if applied_tint_index is not None and idx == applied_tint_index:
                                # Use both checkmark icon AND depress for maximum visual feedback
                                op = layout.operator("view3d.dynamic_button", text=label, icon='CHECKMARK', depress=True)
                            else:
                                # Normal button without icon or depress
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