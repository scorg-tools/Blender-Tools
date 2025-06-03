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

    button_index: bpy.props.IntProperty()

    def execute(self, context):
        tint_utils.SCOrg_tools_tint.on_button_pressed(self.button_index)
        return {'FINISHED'}


class VIEW3D_OT_load_p4k_button(bpy.types.Operator):
    bl_idname = "view3d.load_p4k_button"
    bl_label = "Load Data.p4k"

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
            misc_utils.SCOrg_tools_misc.redraw() 

        # Start the loading in a separate thread
        globals_and_threading._loading_thread = globals_and_threading.LoadP4KThread(prefs.p4k_path, prefs)
        globals_and_threading._loading_thread.start()

        # Register a timer to periodically check the thread's status and update UI
        bpy.app.timers.register(globals_and_threading.check_load_status, first_interval=globals_and_threading._ui_update_interval, persistent=True)
        
        self.report({'INFO'}, "Started loading Data.p4k in background...")
        return {'FINISHED'}

class VIEW3D_OT_refresh_button(bpy.types.Operator):
    bl_idname = "view3d.refresh_button"
    bl_label = "Check Loaded Ship"

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
            misc_utils.SCOrg_tools_misc.redraw()
            return {'CANCELLED'}

        # Get tints for loaded ship
        tints = tint_utils.SCOrg_tools_tint.get_tint_pallet_list(record)

        tint_names = []
        for i, tint_guid in enumerate(tints):
            tint_record = dcb.records_by_guid.get(tint_guid)
            if tint_record:
                #print(dcb.dump_record_json(tint_record))
                # FIX: Access properties safely, check for existence
                tint_name = tint_record.properties.root.properties.get('name')
                if tint_name:
                    if i == 0:
                        name = f"Default Paint ({tint_name.replace('_', ' ').title()})"
                    else:
                        name = localizer.gettext(tint_utils.SCOrg_tools_tint.convert_paint_name(tint_name).lower())
                    tint_names.append(name)
                else:
                    print(f"WARNING: Tint record {tint_guid} missing 'name' property.")
            else:
                print(f"WARNING: Tint record not found for GUID: {tint_guid}")
        
        globals_and_threading.button_labels = tint_names
        misc_utils.SCOrg_tools_misc.redraw()
        return {'FINISHED'}
    
class VIEW3D_OT_import_loadout(bpy.types.Operator):
    bl_idname = "view3d.import_loadout"
    bl_label = "Import missing loadout"

    def execute(self, context):
        # Ensure extract_dir is a Path object before checking
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_dir_path = Path(prefs.extract_dir)

        if extract_dir_path.is_dir() and str(extract_dir_path) != "": # Also check if it's not an empty string
            import_utils.SCOrg_tools_import.run_import()
        else:
            misc_utils.SCOrg_tools_misc.error("Error: Data Extract Directory not set or does not exist. Please set it in preferences.")
        return {'FINISHED'}

class VIEW3D_OT_add_modifiers(bpy.types.Operator):
    bl_idname = "view3d.add_modifiers"
    bl_label = "Add modifiers"

    def execute(self, context):
        blender_utils.SCOrg_tools_blender.fix_modifiers()
        return {'FINISHED'}

class VIEW3D_OT_make_instance_real(bpy.types.Operator):
    bl_idname = "view3d.make_instance_real"
    bl_label = "Make Instance Real" # Corrected label
    
    def execute(self, context):
        blender_utils.SCOrg_tools_blender.run_make_instances_real()
        return {'FINISHED'}

class VIEW3D_OT_import_by_guid(bpy.types.Operator):
    bl_idname = "view3d.import_by_guid"
    bl_label = "Import"

    def execute(self, context):
        # This operator is deprecated. The GetGUIDOperator handles the actual import logic.
        self.report({'ERROR'}, "This operator is deprecated. Use 'Import by GUID' dialog.")
        return {'CANCELLED'}
    
class GetGUIDOperator(bpy.types.Operator):
    bl_idname = "wm.get_guid_operator"
    bl_label = "Import by GUID"

    guid: bpy.props.StringProperty(
        name="GUID",
        description="Please enter the GUID",
        default=""
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):
        if self.guid:
            import_utils.SCOrg_tools_import.import_by_guid(self.guid)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No GUID entered.")
            return {'CANCELLED'}