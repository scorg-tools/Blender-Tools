# operators.py
import bpy
# Import globals
from . import globals_and_threading
from . import misc_utils
from . import tint_utils
from . import import_utils
from . import blender_utils
from pathlib import Path

class VIEW3D_OT_dynamic_button(bpy.types.Operator):
    bl_idname = "view3d.dynamic_button"
    bl_label = "Dynamic Button"
    bl_description = "Apply the selected paint/tint to the current ship"

    button_index: bpy.props.IntProperty()

    def execute(self, context):
        tint_utils.SCOrg_tools_tint.on_button_pressed(self.button_index)
        return {'FINISHED'}


class VIEW3D_OT_load_p4k_button(bpy.types.Operator):
    bl_idname = "view3d.load_p4k_button"
    bl_label = "Load Data.p4k"
    bl_description = "Load the Star Citizen Data.p4k file to access ship and item data"

    def execute(self, context):
        prefs = bpy.context.preferences.addons[__package__].preferences

        if globals_and_threading._loading_thread and globals_and_threading._loading_thread.is_alive():
            self.report({'INFO'}, "Data.p4k is already loading.")
            return {'CANCELLED'}

        # Reset progress display at the start of loading
        prefs.p4k_load_progress = 0.0
        prefs.p4k_load_message = "Loading Data.p4k..."
        globals_and_threading._last_ui_update_time = 0.0 # Reset the timer for the monitor

        # Clear existing data before starting new load
        if globals_and_threading.sc:
            globals_and_threading.clear_vars()
            # Ensure UI reflects cleared state immediately
            misc_utils.SCOrg_tools_misc.force_ui_update() 

        # Start the loading in a separate thread
        globals_and_threading._loading_thread = globals_and_threading.LoadP4KThread(prefs.p4k_path, prefs)
        globals_and_threading._loading_thread.start()

        # Register a timer to periodically check the thread's status and update UI
        bpy.app.timers.register(globals_and_threading.check_load_status, first_interval=globals_and_threading._ui_update_interval, persistent=True)
        
        #self.report({'INFO'}, "Started loading Data.p4k in background...")
        return {'FINISHED'}

class VIEW3D_OT_refresh_button(bpy.types.Operator):
    bl_idname = "view3d.refresh_button"
    bl_label = "Check Loaded Ship"
    bl_description = "Check for ship data in the current scene"

    def execute(self, context):
        # Access global dcb, localizer, ship_loaded
        dcb = globals_and_threading.dcb
        localizer = globals_and_threading.localizer

        if dcb is None or localizer is None:
            misc_utils.SCOrg_tools_misc.error("Data.p4k not loaded. Please load it first.")
            return {'CANCELLED'}

        #Load the record for the ship
        record = misc_utils.SCOrg_tools_misc.get_ship_record()
        
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not find ship record. Ensure a 'base' empty object exists.")
            globals_and_threading.ship_loaded = None # Reset ship_loaded if no record found
            globals_and_threading.button_labels = [] # Clear button labels
            misc_utils.SCOrg_tools_misc.force_ui_update()
            return {'CANCELLED'}

        tint_utils.SCOrg_tools_tint.update_tints(record)
        misc_utils.SCOrg_tools_misc.force_ui_update()
        return {'FINISHED'}
    
class VIEW3D_OT_import_loadout(bpy.types.Operator):
    bl_idname = "view3d.import_loadout"
    bl_label = "Import missing loadout"
    bl_description = "Import missing ship components, and materials for the current ship and apply a number of fixes"

    def execute(self, context):
        # Ensure extract_dir is a Path object before checking
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_dir_path = Path(prefs.extract_dir)

        if extract_dir_path.is_dir() and str(extract_dir_path) != "": # Also check if it's not an empty string
            import_utils.SCOrg_tools_import.run_import()
        else:
            misc_utils.SCOrg_tools_misc.error("Error: Data Extract Directory not set or does not exist. Please set it in preferences.")
        return {'FINISHED'}

class VIEW3D_OT_make_instance_real(bpy.types.Operator):
    bl_idname = "view3d.make_instance_real"
    bl_label = "Make Instance Real"
    bl_description = "Convert collection instances to real objects and clean up the scene, required for more options"
    
    def execute(self, context):
        blender_utils.SCOrg_tools_blender.run_make_instances_real()
        return {'FINISHED'}

class VIEW3D_OT_reload(bpy.types.Operator):
    bl_idname = "view3d.reload"
    bl_label = "Reload Addon"
    bl_description = "Reload the SCOrg.tools addon (for development purposes)"
    
    def execute(self, context):
        misc_utils.SCOrg_tools_misc.reload_addon()
        return {'FINISHED'}
    
class GetGUIDOperator(bpy.types.Operator):
    bl_idname = "wm.get_guid_operator"
    bl_label = "Import by ID"
    bl_description = "Import a specific item by entering its GUID or name from StarFab Datacore"

    guid: bpy.props.StringProperty(
        name="GUID ",
        description="Please enter the GUID",
        default=""
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        if self.guid:
            import_utils.SCOrg_tools_import.import_by_id(self.guid)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No GUID entered.")
            return {'CANCELLED'}

class SCORG_OT_copy_text_to_clipboard(bpy.types.Operator):
    """Copy text to clipboard"""
    bl_idname = "scorg.copy_text_to_clipboard"
    bl_label = "Copy to Clipboard"
    bl_description = "Copy the text content to clipboard"
    
    text_to_copy: bpy.props.StringProperty(
        name="Text to Copy",
        description="The text that will be copied to clipboard",
        default=""
    )
    
    def execute(self, context):
        context.window_manager.clipboard = self.text_to_copy
        return {'FINISHED'}

class SCORG_OT_text_popup(bpy.types.Operator):
    """Display text in a popup dialog"""
    bl_idname = "scorg.text_popup"
    bl_label = "SCOrg.tools"
    bl_options = {'REGISTER'}
    
    text_content: bpy.props.StringProperty(
        name="Text Content",
        description="The text to display",
        default=""
    )
    
    header_text: bpy.props.StringProperty(
        name="Header Text", 
        description="Header text for the popup",
        default=""
    )
    
    def execute(self, context):
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)
    
    def draw(self, context):
        layout = self.layout
        
        if self.header_text:
            layout.label(text=self.header_text)
            layout.separator()
        
        box = layout.box()
        col = box.column(align=True)
        
        if self.text_content:
            lines = self.text_content.split('\n')
            
            for line in lines:
                row = col.row()
                row.scale_y = 0.8
                row.label(text=line)
        
        layout.separator()
        
        # Copy button
        row = layout.row()
        row.scale_y = 1.2
        copy_op = row.operator("scorg.copy_text_to_clipboard", 
                              text="📋 Copy to Clipboard", 
                              icon='PASTEDOWN')
        copy_op.text_to_copy = self.text_content