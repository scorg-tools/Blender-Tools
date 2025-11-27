# operators.py
import bpy
# Import globals
from . import globals_and_threading
from . import misc_utils
from . import tint_utils
from . import import_utils
from . import blender_utils
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

        popup = ui_tools.Popup("Loading Data.p4k", prevent_close=True, blocking=False)
        
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



class SCORG_OT_cancel(bpy.types.Operator):
    """Cancel and close the popup"""
    bl_idname = "scorg.cancel"
    bl_label = "Cancel"
    bl_description = "Close the popup without taking action"
    bl_options = {'REGISTER', 'INTERNAL'}
    
    def execute(self, context):
        return {'CANCELLED'}

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
    
    show_buttons: bpy.props.BoolProperty(
        name="Show Buttons",
        description="Whether to show action buttons",
        default=True
    )
    
    is_extraction_popup: bpy.props.BoolProperty(
        name="Is Extraction Popup",
        default=False
    )

    def execute(self, context):
        if self.is_extraction_popup:
            prefs = bpy.context.preferences.addons[__package__].preferences
            
            # Only extract if the preference is enabled
            if prefs.extract_missing_files:
                # Set flag to indicate extraction has started
                globals_and_threading.extraction_started = True
                
                # Store parameters for the timer function
                file_list = self.text_content
                
                # Define the extraction function to run asynchronously
                def run_extraction():
                    try:
                        success_count, fail_count, report_lines = import_utils.SCOrg_tools_import.extract_missing_files(file_list, prefs)
                    except ValueError as e:
                        # Report error on main thread
                        def report_error():
                            bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=str(e)), title="Error", icon='ERROR')
                        bpy.app.timers.register(report_error, first_interval=0.1)
                        return
                    
                    # Show completion popup on main thread
                    def show_completion():
                        # Clear missing files list so the warning button disappears
                        import_utils.SCOrg_tools_import.missing_files = set()
                        
                        header = f"Extraction Complete\nSuccess: {success_count} | Failed: {fail_count}\n\nNow the missing files have been extracted, please re-import the model again."
                        misc_utils.SCOrg_tools_misc.show_text_popup(
                            text_content="\n".join(report_lines),
                            header_text=header,
                            show_buttons=False
                        )
                    bpy.app.timers.register(show_completion, first_interval=0.1)
                
                # Register the extraction to run asynchronously
                bpy.app.timers.register(run_extraction, first_interval=0.1)
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        if self.is_extraction_popup or not self.show_buttons:
            from . import ui_tools
            
            title = "Missing Files" if self.is_extraction_popup else "SCOrg.tools"
            popup = ui_tools.Popup(title)
            
            # Add the header if present
            if self.header_text:
                popup.add.label(self.header_text)
            
            # Add the content
            if self.text_content:
                popup.add.label(self.text_content)
            
            # Add buttons
            row = popup.add.row()
            
            if self.is_extraction_popup:
                def on_close():
                    popup.finished = True
                
                def on_extract():
                    prefs = bpy.context.preferences.addons[__package__].preferences
                    
                    if prefs.extract_missing_files:
                        globals_and_threading.extraction_started = True
                        
                        file_list = self.text_content
                        
                        def run_extraction():
                            try:
                                success_count, fail_count, report_lines = import_utils.SCOrg_tools_import.extract_missing_files(file_list, prefs)
                            except ValueError as e:
                                def report_error():
                                    bpy.context.window_manager.popup_menu(lambda self, context: self.layout.label(text=str(e)), title="Error", icon='ERROR')
                                bpy.app.timers.register(report_error, first_interval=0.1)
                                return
                            
                            def show_completion():
                                import_utils.SCOrg_tools_import.missing_files = set()
                                
                                header = f"Extraction Complete\nSuccess: {success_count} | Failed: {fail_count}\n\nNow the missing files have been extracted, please re-import the model again."
                                misc_utils.SCOrg_tools_misc.show_text_popup(
                                    text_content="\n".join(report_lines),
                                    header_text=header,
                                    show_buttons=False
                                )
                            bpy.app.timers.register(show_completion, first_interval=0.1)
                        
                        bpy.app.timers.register(run_extraction, first_interval=0.1)
                    
                    popup.finished = True
                
                row.add.button("Close", callback=on_close)
                row.add.button("Extract Missing", callback=on_extract)
            else:
                # For completion or other popups with show_buttons=False
                def on_close():
                    popup.finished = True
                
                row.add.button("OK", callback=on_close)
            
            popup.show()
            return {'FINISHED'}
        else:
            return context.window_manager.invoke_popup(self, width=600)
    
    def draw(self, context):
        layout = self.layout
        
        if self.header_text:
            # Handle multiline headers
            header_lines = self.header_text.split('\n')
            for line in header_lines:
                layout.label(text=line)
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

        layout.separator()
        
        # Action Buttons
        row = layout.row()
        row.scale_y = 1.2
        
        if self.is_extraction_popup:
            prefs = bpy.context.preferences.addons[__package__].preferences
            if prefs.extract_missing_files:
                # Instructions
                layout.label(text="Click 'Extract' to continue or hit Esc to cancel extracting missing files", icon='INFO')
                
                # Extract Button
                extract_op = row.operator("view3d.export_missing", text="Extract Missing", icon='EXPORT')
                extract_op.file_list = self.text_content
            else:
                layout.label(text="Click OK or Cancel to Close", icon='INFO')
                # Standard OK button
                row.operator("scorg.cancel", text="OK", icon='CHECKMARK')
        else:
            # Standard OK button for non-extraction popups (like completion message)
            row.operator("scorg.cancel", text="OK", icon='CHECKMARK')
    
    def cancel(self, context):
        """Called when user clicks Cancel - just close the popup without doing anything"""
        pass

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
                header = f"Extraction Complete\nSuccess: {success_count} | Failed: {fail_count}\n\nNow the missing files have been extracted, please re-import the model again."
                misc_utils.SCOrg_tools_misc.show_text_popup(
                    text_content="\n".join(report_lines),
                    header_text=header,
                    show_buttons=False
                )
            bpy.app.timers.register(show_completion, first_interval=0.1)
        
        # Register the extraction to run asynchronously
        bpy.app.timers.register(run_extraction, first_interval=0.1)
        
        return {'FINISHED'}