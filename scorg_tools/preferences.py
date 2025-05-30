import bpy
import os
from pathlib import Path

# Import globals
from . import globals_and_threading

class SCOrg_tools_OT_SelectP4K(bpy.types.Operator):
    bl_idname = "scorg_tools.select_p4k"
    bl_label = "Select .p4k File"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(
        default="*.p4k",
        options={'HIDDEN'}
    )

    def execute(self, context):
        prefs = context.preferences.addons["scorg_tools"].preferences
        prefs.p4k_path = self.filepath
        # Unload the existing p4k to force a reload
        globals_and_threading.clear_vars()
        # Reset progress display
        prefs.p4k_load_progress = 0.0
        prefs.p4k_load_message = ""
        self.report({'INFO'}, f"Selected: {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
class SCOrg_tools_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    p4k_path: bpy.props.StringProperty(
        name="P4K File Path",
        description="Path to SC Data.p4k file",
        subtype='FILE_PATH',
        default=r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Data.p4k",
    )

    extract_dir: bpy.props.StringProperty(
        name="Data Extract Directory",
        description="Data directory where extracted files are stored",
        subtype='DIR_PATH',
    )
    
    # New properties for progress display in UI
    p4k_load_progress: bpy.props.FloatProperty(
        name="Load Progress",
        description="Progress of Data.p4k loading",
        subtype='PERCENTAGE', # This tells Blender to display it as a percentage
        min=0.0,
        max=100.0,
        default=0.0
    )
    p4k_load_message: bpy.props.StringProperty(
        name="Load Message",
        description="Current message during Data.p4k loading",
        default=""
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="SCOrg.tools Settings")
        layout.label(text=f"Current P4K: {self.p4k_path}")
        layout.operator("scorg_tools.select_p4k", text="Select .p4k File")

        if self.p4k_path and not self.p4k_path.lower().endswith(".p4k"):
            layout.label(text="Warning: Not a .p4k file", icon='ERROR')
        layout.prop(self, "extract_dir")
        if self.extract_dir:
            abs_chosen_dir = os.path.abspath(bpy.path.abspath(self.extract_dir))
            objects_dir = os.path.join(abs_chosen_dir, "Objects")
            if not os.path.isdir(objects_dir):
                layout.label(text=f"Directory '{objects_dir}' not found. This doesn't appear to be the correct folder.", icon='ERROR')