# operators.py
import bpy
# Import globals
from . import globals_and_threading
from . import misc_utils
from . import tint_utils
from . import import_utils
from . import blender_utils
from . import ui_tools
from pathlib import Path
import subprocess
import os
import shutil
import time

class VIEW3D_OT_paint_warning_popup(bpy.types.Operator):
    bl_idname = "view3d.paint_warning_popup"
    bl_label = "Paint Warning"
    bl_description = "Warning popup for paint application"
    bl_options = {'REGISTER', 'INTERNAL'}

    button_index: bpy.props.IntProperty()
    ignore_future: bpy.props.BoolProperty(
        name="Ignore warning in future",
        description="Don't show this warning again",
        default=False
    )

    def execute(self, context):
        # If user checked "ignore future", update the preference
        if self.ignore_future:
            prefs = bpy.context.preferences.addons[__package__].preferences
            prefs.ignore_paint_warnings = True
        
        # Apply the paint/tint
        tint_utils.SCOrg_tools_tint.on_button_pressed(self.button_index)
        # Invalidate the tint cache so the UI updates immediately
        from . import panels
        panels.VIEW3D_PT_scorg_tools_panel.invalidate_tint_cache()
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.label(text="WARNING:", icon='ERROR')
        layout.separator()
        
        # Split the warning text into multiple lines for better readability
        col = layout.column(align=True)
        col.label(text="Changing paints will overwrite any changes to the base ship materials.")
        col.label(text="Your changes will be lost.")
        
        layout.separator()
        layout.prop(self, "ignore_future")

    def cancel(self, context):
        return {'CANCELLED'}

class VIEW3D_OT_dynamic_button(bpy.types.Operator):
    bl_idname = "view3d.dynamic_button"
    bl_label = "Dynamic Button"
    bl_description = "Apply the selected paint/tint to the current ship"

    button_index: bpy.props.IntProperty()

    def execute(self, context):
        # Check if we should show the warning
        prefs = bpy.context.preferences.addons[__package__].preferences
        if not prefs.ignore_paint_warnings:
            # Show the warning popup instead of applying directly
            bpy.ops.view3d.paint_warning_popup('INVOKE_DEFAULT', button_index=self.button_index)
            return {'FINISHED'}
        
        # If warnings are ignored, apply directly
        tint_utils.SCOrg_tools_tint.on_button_pressed(self.button_index)
        # Invalidate the tint cache so the UI updates immediately
        from . import panels
        panels.VIEW3D_PT_scorg_tools_panel.invalidate_tint_cache()
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

        # Clear existing data before starting new load
        if globals_and_threading.sc:
            globals_and_threading.clear_vars()
            # Ensure UI reflects cleared state immediately
            misc_utils.SCOrg_tools_misc.force_ui_update() 

        from . import ui_tools

        popup = ui_tools.Popup("Loading Data.p4k", width=600, prevent_close=True, blocking=False)
        
        progress = ui_tools.ProgressBar(text="Initializing...")
        popup.add_widget(progress)
        
        def on_cancel():
            popup.cancelled = True
            
        cancel_btn = ui_tools.Button("Cancel", callback=on_cancel)
        popup.add_widget(cancel_btn)
        
        popup.show()
        
        tm = ui_tools.ThreadManager()
        tm.start()
        
        def background_task():
            try:
                success = globals_and_threading.load_p4k_with_progress(prefs.p4k_path, prefs, lambda msg, cur, tot: progress.update(cur, tot, msg))
                
                if popup.cancelled:
                    return
                    
                if success:
                    progress.update(100, 100, "Data.p4k Loaded!")
                else:
                    progress.update(0, 100, "Failed to load")
                
                time.sleep(0.5)
                
                popup.prevent_close = False
                
                cancel_btn.text = "Close"
                cancel_btn.callback = lambda: setattr(popup, 'finished', True)
                
                progress.update(100, 100, "Done!")
                
                time.sleep(1.0)
                popup.finished = True
                
            except Exception as e:
                print(f"Error: {e}")
                popup.prevent_close = False

        tm.submit(background_task)

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
        globals_and_threading.imported_record = record  # Store the record globally for later use
        
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not find ship record. Ensure a 'base' empty object exists.")
            globals_and_threading.ship_loaded = None # Reset ship_loaded if no record found
            globals_and_threading.button_labels = [] # Clear button labels
            misc_utils.SCOrg_tools_misc.force_ui_update()
            return {'CANCELLED'}

        # Make sure the tint node group is initialised, pass the item_name
        blender_utils.SCOrg_tools_blender.init_tint_group(record.name)
        
        tint_utils.SCOrg_tools_tint.update_tints(record)
        # Invalidate the tint cache since tint data may have changed
        from . import panels
        panels.VIEW3D_PT_scorg_tools_panel.invalidate_tint_cache()
        misc_utils.SCOrg_tools_misc.force_ui_update()
        return {'FINISHED'}
    
class VIEW3D_OT_import_loadout(bpy.types.Operator):
    bl_idname = "view3d.import_loadout"
    bl_label = "Import missing loadout"
    bl_description = "Import missing ship components, and materials for the current ship and apply a number of fixes"
    bl_options = {'REGISTER', 'UNDO'}

    def __init__(self):
        self.entries = []
        self.current_index = 0
        self.empties_to_fill = []
        self.top_level_loadout = None
        self.displacement_strength = 0
        self.batch_size = 1  # Process 1 entry per modal call for better responsiveness
        self.state = 'init'  # 'init', 'hardpoints', 'postprocess'
        self.postprocess_steps = []
        self.current_step = 0

    def invoke(self, context, event):
        # Ensure extract_dir is a Path object before checking
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_dir_path = Path(prefs.extract_dir)

        if not (extract_dir_path.is_dir() and str(extract_dir_path) != ""):
            misc_utils.SCOrg_tools_misc.error("Error: Data Extract Directory not set or does not exist. Please set it in preferences.")
            return {'CANCELLED'}

        # Initialize import state
        os.system('cls')
        import_utils.SCOrg_tools_import.imported_guid_objects = {}
        import_utils.SCOrg_tools_import.INCLUDE_HARDPOINTS = [] # all
        globals_and_threading.missing_files = set()
        import_utils.SCOrg_tools_import.set_translation_new_data_preference()

        misc_utils.SCOrg_tools_misc.select_base_collection() # Ensure the base collection is active before importing
        record = misc_utils.SCOrg_tools_misc.get_ship_record()
        
        globals_and_threading.imported_record = record

        # Check if record is None before trying to access its properties
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not get ship record. Please import a StarFab Blueprint first.")
            return {'CANCELLED'}

        # Use ship displacement preference for fix_modifiers later
        self.displacement_strength = bpy.context.preferences.addons["scorg_tools"].preferences.decal_displacement_ship

        # Safely access Components and loadout
        self.top_level_loadout = import_utils.SCOrg_tools_import.get_loadout_from_record(record)

        if self.top_level_loadout is None:
            blender_utils.SCOrg_tools_blender.fix_modifiers(self.displacement_strength)
            misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            return {'CANCELLED'}

        self.empties_to_fill = import_utils.SCOrg_tools_import.get_all_empties_blueprint()

        if globals_and_threading.debug: print(f"Total hardpoints to import: {len(self.empties_to_fill)}")

        # Collect top-level entries
        self.entries = self.top_level_loadout.properties.get('entries', [])
        self.current_index = 0
        self.state = 'hardpoints'

        # Prepare post-processing steps
        self.postprocess_steps = []
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        if prefs.enable_weld_weighted_normal and not False:  # material_only=False
            self.postprocess_steps.append(('blender_utils', 'add_weld_and_weighted_normal_modifiers', []))
        if prefs.enable_displace_decals and not False:
            self.postprocess_steps.append(('blender_utils', 'add_displace_modifiers_for_decal', [self.displacement_strength]))
        if prefs.enable_remove_duplicate_displace and not False:
            self.postprocess_steps.append(('blender_utils', 'remove_duplicate_displace_modifiers', []))
        if prefs.enable_remove_proxy_geometry and not False:
            self.postprocess_steps.append(('blender_utils', 'remove_proxy_material_geometry', []))
        if prefs.enable_remap_material_users and not False:
            self.postprocess_steps.append(('blender_utils', 'remap_material_users', []))
        if prefs.enable_import_missing_materials and not False:
            self.postprocess_steps.append(('import_utils', 'import_missing_materials', []))
        if prefs.enable_fix_materials_case:
            self.postprocess_steps.append(('blender_utils', 'fix_materials_case_sensitivity', []))
        if prefs.enable_set_glass_transparent:
            self.postprocess_steps.append(('blender_utils', 'set_glass_materials_transparent', []))
        if prefs.enable_fix_stencil_materials:
            self.postprocess_steps.append(('blender_utils', 'fix_stencil_materials', []))
        if prefs.enable_3d_pom:
            self.postprocess_steps.append(('blender_utils', 'replace_pom_materials', []))
        if prefs.enable_remove_engine_flame_materials:
            self.postprocess_steps.append(('blender_utils', 'set_engine_flame_mat_transparent', []))
        if prefs.enable_tidyup:
            self.postprocess_steps.append(('blender_utils', 'tidyup', []))
        
        self.current_step = 0

        # Initialize progress
        ui_tools.progress_bar_popup("import_hardpoints", 0, len(self.entries), "Starting hardpoint import...")

        # Add a timer to keep the modal running even without user events
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            ui_tools.close_progress_bar_popup("import_hardpoints")
            context.window_manager.event_timer_remove(self._timer)
            return {'CANCELLED'}

        # Handle timer events to keep processing
        if event.type == 'TIMER':
            pass  # Continue processing below

        if self.state == 'hardpoints':
            processed = 0
            while self.current_index < len(self.entries) and processed < self.batch_size:
                entry = self.entries[self.current_index]
                
                # Process this entry
                hardpoint_mapping = {}  # For top level, no mapping
                import_utils.SCOrg_tools_import.process_single_entry(
                    entry, self.empties_to_fill, is_top_level=True, parent_guid=None, hardpoint_mapping=hardpoint_mapping
                )
                
                self.current_index += 1
                processed += 1
            
            # Update progress
            ui_tools.progress_bar_popup("import_hardpoints", self.current_index, len(self.entries), f"Importing hardpoints {self.current_index}/{len(self.entries)}...")
            
            # Force UI update
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            
            if self.current_index >= len(self.entries):
                self.state = 'postprocess'
                self.current_step = 0
                ui_tools.progress_bar_popup("postprocess", 0, len(self.postprocess_steps), "Starting post-processing...")
            
            return {'RUNNING_MODAL'}
        
        elif self.state == 'postprocess':
            if self.current_step < len(self.postprocess_steps):
                module_name, step_name, args = self.postprocess_steps[self.current_step]
                if module_name == 'blender_utils':
                    method = getattr(blender_utils.SCOrg_tools_blender, step_name)
                elif module_name == 'import_utils':
                    method = getattr(import_utils.SCOrg_tools_import, step_name)
                method(*args)
                blender_utils.SCOrg_tools_blender.update_viewport_with_timer(redraw_now=True)
                
                self.current_step += 1
                ui_tools.progress_bar_popup("postprocess", self.current_step, len(self.postprocess_steps), f"Post-processing {self.current_step}/{len(self.postprocess_steps)}...")
                
                # Force UI update
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                
                return {'RUNNING_MODAL'}
            else:
                # Finished post-processing
                print(f"Total missing files: {len(globals_and_threading.missing_files)}")
                if len(globals_and_threading.missing_files) > 0:
                    globals_and_threading.show_missing_files_popup()
                import_utils.SCOrg_tools_import.set_translation_new_data_preference(reset=True)

                ui_tools.progress_bar_popup("postprocess", len(self.postprocess_steps), len(self.postprocess_steps), "Post-processing complete")
                ui_tools.close_progress_bar_popup("postprocess")
                
                # Remove timer
                context.window_manager.event_timer_remove(self._timer)
                
                return {'FINISHED'}
        
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

class SCORG_OT_show_missing_files(bpy.types.Operator):
    bl_idname = "scorg.show_missing_files"
    bl_label = "Show Missing Files"
    bl_description = "Show a popup with the list of missing files"
    
    def execute(self, context):
        from . import globals_and_threading
        globals_and_threading.show_missing_files_popup()
        return {'FINISHED'}

class VIEW3D_OT_separate_decals(bpy.types.Operator):
    bl_idname = "view3d.separate_decals"
    bl_label = "Separate Decals"
    bl_description = "Separate decal, POM, and stencil materials into their own objects"
    
    def execute(self, context):
        blender_utils.SCOrg_tools_blender.separate_decal_materials()
        return {'FINISHED'}

class VIEW3D_OT_open_preferences(bpy.types.Operator):
    bl_idname = "view3d.open_preferences"
    bl_label = "Open Preferences"
    bl_description = "Open the SCOrg.tools addon preferences"
    
    def execute(self, context):
        # Use the built-in addon preferences operator which should automatically expand the addon
        try:
            bpy.ops.preferences.addon_show(module=__package__)
        except:
            # Fallback to the manual method if the direct operator doesn't work
            bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
            bpy.context.preferences.active_section = 'ADDONS'
            from . import bl_info
            bpy.context.window_manager.addon_search = bl_info["name"]
        
        return {'FINISHED'}

# Export Missing Operator
class VIEW3D_OT_export_missing(bpy.types.Operator):
    bl_idname = "view3d.export_missing"
    bl_label = "Extract Missing"
    bl_description = "Extract missing files from Data.p4k. Converts geometry files using cgf-converter.exe."



    file_list: bpy.props.StringProperty(
        name="File List",
        description="Internal property to pass file list directly",
        default="",
        options={'SKIP_SAVE', 'HIDDEN'}
    )

    def invoke(self, context, event):
        # File list is always provided from the missing files popup
        return self.execute(context)

    def draw(self, context):
        # Not used since invoke() goes directly to execute()
        pass

    def execute(self, context):
        # Set flag to indicate extraction has started
        globals_and_threading.extraction_started = True
        
        # Store parameters for the timer function
        file_list = self.file_list
        
        # Define the extraction function to run asynchronously
        def run_extraction():
            prefs = bpy.context.preferences.addons[__package__].preferences
            
            try:
                success_count, fail_count, report_lines = import_utils.SCOrg_tools_import.extract_missing_files(file_list, prefs)
            except ValueError as e:
                # Report error on main thread
                def report_error():
                    bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=str(e)), title="Error", icon='ERROR')
                bpy.app.timers.register(report_error, first_interval=0.1)
                return
            
            # Calculate the number of files that were actually processed (excluding comments and glossmap files)
            processed_files_count = len([f.strip() for f in file_list.split('\n') if f.strip() and not f.startswith('#') and '.ddna.glossmap' not in f.lower()])
            
            # Show completion popup on main thread
            def show_completion():
                # Clear missing files if extraction was successful
                if success_count > 0:
                    from . import globals_and_threading
                    globals_and_threading.missing_files = set()
                
                from . import ui_tools
                message = f"Extraction Complete\nSuccess: {success_count} | Failed: {fail_count}\n\nNow the missing files have been extracted, please re-import the model again."
                ui_tools.Popup("Extraction Complete", message + "\n\n" + "\n".join(report_lines), width=800).show()
            bpy.app.timers.register(show_completion, first_interval=0.1)
        
        # Register the extraction to run asynchronously
        bpy.app.timers.register(run_extraction, first_interval=0.1)
        
        return {'FINISHED'}
