# preferences.py
import bpy
from bpy.props import StringProperty, FloatProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper # Needed for file browser
from pathlib import Path # Needed for path validation

# Import globals and misc_utils for update callbacks
from . import globals_and_threading
from . import misc_utils

class SCOrg_tools_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    # --- Update Callback for p4k_path ---
    def update_p4k_path_callback(self, context):
        """
        Callback function executed when the p4k_path preference is changed.
        Clears the currently loaded P4K data to force a reload.
        """
        print("SCOrg.tools: Data.p4k path preference changed. Clearing loaded P4K data.")
        globals_and_threading.clear_vars()
        misc_utils.SCOrg_tools_misc.force_ui_update()

    # --- Update Callback for debug_mode ---
    def update_debug_mode_callback(self, context):
        """
        Callback function executed when the debug_mode preference is changed.
        Updates the global debug setting.
        """
        globals_and_threading.debug = self.debug_mode
        status = "enabled" if self.debug_mode else "disabled"
        print(f"SCOrg.tools: Debug mode {status}")

    p4k_path: StringProperty(
        name="Star Citizen Data.p4k Path",
        subtype='FILE_PATH',
        description="Path to your Star Citizen Data.p4k file (e.g., C:\\Program Files\\Roberts Space Industries\\StarCitizen\\LIVE\\Data.p4k)",
        default=r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Data.p4k",
        update=update_p4k_path_callback
    )

    extract_dir: StringProperty(
        name="Extracted Data Directory",
        subtype='DIR_PATH',
        description="Directory where StarFab extracts game data (e.g., C:\\StarFab\\extracted_data\\Data)"
    )

    extract_missing_files: BoolProperty(
        name="Extract and convert missing files",
        description="If enabled, missing files will be extracted when clicking OK on the missing files popup",
        default=True
    )

    max_extraction_threads: bpy.props.IntProperty(
        name="Max Extraction Threads",
        description="Maximum number of threads to use for file extraction and conversion",
        default=4,
        min=1,
        max=32
    )

    cgf_converter_path: StringProperty(
        name="CGF Converter Path",
        subtype='FILE_PATH',
        description="Optional path to cgf-converter.exe for converting CryEngine geometry files",
        default=""
    )

    texconv_path: StringProperty(
        name="TexConv Path",
        subtype='FILE_PATH',
        description="Optional path to texconv.exe for converting DDS texture files",
        default=""
    )

    # Properties for displaying P4K load progress and messages
    p4k_load_progress: FloatProperty(
        name="P4K Load Progress",
        subtype='PERCENTAGE',
        min=0.0,
        max=100.0
    )

    p4k_load_message: StringProperty(
        name="P4K Load Message",
        default=""
    )

    debug_mode: BoolProperty(
        name="Enable Debug Mode",
        description="Enable debug output to console for troubleshooting",
        default=False,
        update=update_debug_mode_callback
    )

    decal_displacement_ship: FloatProperty(
        name="Decal Displacement (Ship)",
        description="Displacement strength (m) for decal materials on ships",
        default=0.001,
        min=0.0,
        max=0.05,
        step=0.0001,
        precision=4
    )

    decal_displacement_non_ship: FloatProperty(
        name="Decal Displacement (Non-Ship)",
        description="Displacement strength (m) for decal materials on non-ship items (weapons, equipment, etc.)",
        default=0.0001,
        min=0.0,
        max=0.05,
        step=0.0001,
        precision=4
    )

    enable_3d_pom: BoolProperty(
        name="Enable 3D POM",
        description="Enable 3D Parallax Occlusion Mapping (POM) material replacement for better visual quality",
        default=True
    )

    # New modifier function preferences
    enable_weld_weighted_normal: BoolProperty(
        name="Add Weld and Weighted Normal Modifiers",
        description="Add Weld and Weighted Normal modifiers to mesh objects",
        default=True
    )
    
    enable_displace_decals: BoolProperty(
        name="Add Displace Modifiers for Decals",
        description="Add displacement modifiers for decal, POM, and stencil materials",
        default=True
    )
    
    enable_remove_duplicate_displace: BoolProperty(
        name="Remove Duplicate Displace Modifiers",
        description="Remove duplicate displacement modifiers with the same vertex group",
        default=True
    )
    
    enable_remove_proxy_geometry: BoolProperty(
        name="Remove Proxy Material Geometry",
        description="Remove geometry with proxy, nodraw, and physics_proxy materials",
        default=True
    )
    
    enable_remap_material_users: BoolProperty(
        name="Remap Material Users",
        description="Remap duplicate materials (with .001 suffixes) to their base versions",
        default=True
    )
    
    enable_import_missing_materials: BoolProperty(
        name="Import Missing Materials",
        description="Import missing material files and apply proper shaders",
        default=True
    )
    
    enable_fix_materials_case: BoolProperty(
        name="Fix Materials Case Sensitivity",
        description="Fix materials that were imported due to case sensitivity differences",
        default=True
    )
    
    enable_set_glass_transparent: BoolProperty(
        name="Set Glass Materials Transparent",
        description="Set glass materials to be transparent in the viewport",
        default=True
    )
    
    enable_fix_stencil_materials: BoolProperty(
        name="Fix Stencil Materials",
        description="Fix stencil materials by setting UseAlpha to 1.0",
        default=True
    )

    enable_remove_engine_flame_materials: BoolProperty(
        name="Remove Engine Flame Materials",
        description="Set engine flame materials to transparent",
        default=True
    )
    
    enable_tidyup: BoolProperty(
        name="Cleanup Scene",
        description="Perform scene cleanup (deduplicate images, remove orphaned data)",
        default=True
    )

    ignore_paint_warnings: BoolProperty(
        name="Ignore Paint Warnings",
        description="Skip the warning dialog when applying paints/tints",
        default=False
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="SCOrg.tools Settings")
        
        # Debug mode checkbox
        layout.prop(self, "debug_mode")
        layout.separator()

        layout.label(text=f"Current P4K: {self.p4k_path}")
        layout.operator("scorg_tools.select_p4k", text="Select .p4k File")

        if self.p4k_path and not self.p4k_path.lower().endswith(".p4k"):
            layout.label(text="Warning: Not a .p4k file", icon='ERROR')
        layout.prop(self, "extract_dir")
        if self.extract_dir:
            from os import path
            abs_chosen_dir = path.abspath(bpy.path.abspath(self.extract_dir))
            objects_dir = path.join(abs_chosen_dir, "Objects")
            if not path.isdir(objects_dir):
                layout.label(text=f"Directory '{objects_dir}' not found. This doesn't appear to be the correct folder.", icon='ERROR')
        
        layout.prop(self, "extract_missing_files")
        if self.extract_missing_files:
            layout.prop(self, "max_extraction_threads")
        
        layout.separator()
        layout.label(text="CGF Converter:")
        layout.prop(self, "cgf_converter_path")
        
        from os import path
        if self.cgf_converter_path:
            if not path.isfile(bpy.path.abspath(self.cgf_converter_path)):
                layout.label(text="Warning: File not found", icon='ERROR')
            elif not self.cgf_converter_path.lower().endswith(".exe"):
                layout.label(text="Warning: Not an .exe file", icon='ERROR')
        elif self.extract_missing_files:
            layout.label(text="Warning: CGF Converter required for extraction", icon='ERROR')
        
        layout.separator()
        layout.label(text="TexConv:")
        layout.prop(self, "texconv_path")
        if self.texconv_path:
            if not path.isfile(bpy.path.abspath(self.texconv_path)):
                layout.label(text="Warning: File not found", icon='ERROR')
            elif not self.texconv_path.lower().endswith(".exe"):
                layout.label(text="Warning: Not an .exe file", icon='ERROR')
        elif self.extract_missing_files:
            layout.label(text="Warning: TexConv required for extraction", icon='ERROR')
        
        col = layout.column()        
        # Displacement settings
        col.label(text="Modifier Functions:", icon='MODIFIER')
        col.prop(self, "enable_displace_decals")
        col.prop(self, "enable_remove_duplicate_displace")
        col.separator()
        col.label(text="Physical decal displacement settings:", icon='MOD_DISPLACE')
        col.prop(self, "decal_displacement_ship")
        col.prop(self, "decal_displacement_non_ship")
        col.prop(self, "enable_weld_weighted_normal")
        col.separator()
        col.label(text="Geometry settings:", icon='MESH_DATA')
        col.prop(self, "enable_remove_proxy_geometry")
        col.separator()
        col.label(text="Material settings:", icon='MATERIAL')
        col.prop(self, "enable_3d_pom")
        col.prop(self, "enable_remap_material_users")
        col.prop(self, "enable_import_missing_materials")
        col.prop(self, "enable_fix_materials_case")
        col.prop(self, "enable_set_glass_transparent")
        col.prop(self, "enable_fix_stencil_materials")
        col.prop(self, "enable_remove_engine_flame_materials")
        col.separator()
        col.label(text="Misc settings:", icon='SETTINGS')
        col.prop(self, "enable_tidyup")
        col.prop(self, "ignore_paint_warnings")


class SCOrg_tools_OT_SelectP4K(bpy.types.Operator, ExportHelper):
    """Select the Data.p4k file"""
    bl_idname = "scorg_tools.select_p4k"
    bl_label = "Select Data.p4k"

    filename_ext = ".p4k"
    filter_glob: StringProperty(default="*.p4k", options={'HIDDEN'})

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        prefs.p4k_path = self.filepath
        return {'FINISHED'}