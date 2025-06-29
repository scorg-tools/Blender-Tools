import bpy
from pathlib import Path
import re
import time  # Add time import for timer functionality

# Import globals
from . import globals_and_threading
from . import import_utils
from .spinners import SPINNER_LIBRARY  # Import the spinner library

class SCOrg_tools_misc():
    _last_progress_update_time = 0  # Class variable to track last progress update
    _spinner_counter = 0  # Class variable to track spinner animation
    
    # Default spinner type - change this to use different spinners
    spinner_type = "clock"
    
    @staticmethod
    def update_progress(message="", current=0, total=100, hide_message=False, hide_progress=False, update_interval=1.0, force_update=False, spinner=True, spinner_type=None):
        """
        Update the progress bar and status message in the UI with timer-based throttling.
        
        Args:
            message (str): Status message to display
            current (int/float): Current progress value
            total (int/float): Total/maximum progress value
            hide_message (bool): If True, clear the message
            hide_progress (bool): If True, set progress to 0
            update_interval (float): Minimum time interval in seconds between UI updates
            force_update (bool): If True, ignore the timer and update immediately
            spinner (bool): If True, add animated spinner character to the message
            spinner_type (str): Override the default spinner type for this call
        """
        try:
            current_time = time.time()
            
            # Check if enough time has passed since last update (or if forced)
            if not force_update and (current_time - SCOrg_tools_misc._last_progress_update_time) < update_interval:
                return  # Skip this update to avoid UI spam
            
            prefs = bpy.context.preferences.addons["scorg_tools"].preferences
            
            # Update message with animated spinner if enabled
            if hide_message:
                prefs.p4k_load_message = ""
                SCOrg_tools_misc._spinner_counter = 0  # Reset spinner counter
            else:
                display_message = message
                if spinner and message:
                    # Use provided spinner_type or fall back to class default
                    active_spinner_type = spinner_type or SCOrg_tools_misc.spinner_type
                    spinner_chars = SPINNER_LIBRARY.get(active_spinner_type, SPINNER_LIBRARY["clock"])
                    
                    if spinner_chars:
                        # Add animated spinner (cycling through all characters in the list)
                        spinner_char = spinner_chars[SCOrg_tools_misc._spinner_counter % len(spinner_chars)]
                        display_message = f"{message} {spinner_char}"
                        SCOrg_tools_misc._spinner_counter += 1
                
                prefs.p4k_load_message = display_message
            
            # Update progress bar
            if hide_progress:
                prefs.p4k_load_progress = 0.0
            else:
                if total > 0:
                    # Calculate percentage as a value between 0 and 100 (not 0 and 1)
                    progress_percentage = min(max((current / total) * 100, 0.0), 100.0)  # Clamp between 0 and 100
                    prefs.p4k_load_progress = progress_percentage
                else:
                    prefs.p4k_load_progress = 0.0
            
            # Update the last update time
            SCOrg_tools_misc._last_progress_update_time = current_time
            
            # Force UI redraw with multiple approaches
            SCOrg_tools_misc.force_ui_update()
            
        except Exception as e:
            print(f"Error updating progress: {e}")
            import traceback
            traceback.print_exc()

    @staticmethod
    def clear_progress():
        """Clear both the progress bar and status message."""
        SCOrg_tools_misc.update_progress(hide_message=True, hide_progress=True, force_update=True)

    def get_ship_record(skip_error = False):
        dcb = globals_and_threading.dcb
        empty_name = SCOrg_tools_misc.find_base_name()
        if empty_name:
            print(f"Found Empty object: {empty_name}")
            name = re.sub(r'\.\d+$', '', empty_name)  # Remove any trailing .001, .002, etc.
            records = dcb.search_filename(f'libs/foundry/records/entities/spaceships/*{name}.xml')
            if records == []:
                records = dcb.search_filename(f'libs/foundry/records/entities/groundvehicles/*{name}.xml')
            if records == []:
                print(f"❌ Error, could not match ship or vehicle for {name}")
                return None
            
            # Get ship name:
            ship_name = import_utils.SCOrg_tools_import.get_record_name(records[0])
        
            if globals_and_threading.localizer:
                ship_name = globals_and_threading.localizer.gettext("vehicle_name"+name.lower())
                globals_and_threading.ship_loaded = ship_name
            else:
                print("Warning: localizer not loaded, ship name might not be localized.")
                globals_and_threading.ship_loaded = name # Fallback
            return records[0]
        else:
            if not skip_error: print("❌ Error, no Empty object with 'container_name' = 'base' found.")
            return None
        
    def find_base_name():
        for obj in bpy.context.scene.objects:
            if obj.type == 'EMPTY':
                if 'container_name' in obj:
                    if obj["container_name"] == "base":
                        return obj.name
        return None
    
    def recurLayerCollection(layerColl, collName):
        """Recursively finds a LayerCollection by its name within the view layer hierarchy."""
        if layerColl.name == collName:
            return layerColl
        for layer in layerColl.children:
            found = SCOrg_tools_misc.recurLayerCollection(layer, collName)
            if found:
                return found
        return None

    def select_base_collection():
        """
        Finds a specific 'base' empty object, determines its direct parent collection,
        and sets that collection as the active one for new imports/items.
        """
        # Only change mode if there's an active object
        if bpy.context.active_object is not None:
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT') # Deselect all objects for a clean slate

        found_base_empty = None
        # Search for the base empty object in the scene
        for obj in bpy.context.scene.objects:
            if obj.type == 'EMPTY' and "container_name" in obj and obj["container_name"] == "base":
                found_base_empty = obj
                print(f"Found base empty: '{found_base_empty.name}'")
                break

        if not found_base_empty:
            print("ERROR: Base empty object with 'container_name' == 'base' not found.")
            return

        # Determine the target bpy.data.Collection (the actual collection data block)
        target_data_collection = None
        # Prioritize a non-Scene Collection as the 'direct parent'
        for coll_data in found_base_empty.users_collection:
            if coll_data != bpy.context.scene.collection:
                target_data_collection = coll_data
                break
        # If only linked to the Scene Collection, use that
        if not target_data_collection:
            target_data_collection = bpy.context.scene.collection

        if not target_data_collection:
            print("ERROR: No suitable parent collection determined for the base empty.")
            return

        # Use recurLayerCollection to find the corresponding bpy.types.LayerCollection
        desired_layer_collection = SCOrg_tools_misc.recurLayerCollection(
            bpy.context.view_layer.layer_collection, target_data_collection.name
        )

        if desired_layer_collection:
            # Set this LayerCollection as the active one for new items
            bpy.context.view_layer.active_layer_collection = desired_layer_collection
            print(f"SUCCESS: Collection '{desired_layer_collection.name}' is now active for new items.")
        else:
            print(f"ERROR: Could not find LayerCollection for '{target_data_collection.name}'.")
    
    @staticmethod
    def force_ui_update():
        """Force UI update using more aggressive methods to ensure visibility"""
        try:
            # Suppress console output during redraw operations to avoid warnings
            import sys
            import os
            from contextlib import redirect_stdout, redirect_stderr
            
            # Temporarily redirect both stdout and stderr to suppress warnings
            with open(os.devnull, 'w') as devnull:
                with redirect_stdout(devnull), redirect_stderr(devnull):
                    # Method 1: Tag ALL areas for redraw (not just specific ones)
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            area.tag_redraw()
                    
                    # Method 2: Force immediate UI redraw specifically for UI regions
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            for region in area.regions:
                                region.tag_redraw()
                    
                    # Method 3: Force redraw timer - this is what actually makes it visible
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                    
                    # Method 4: Update depsgraph
                    if hasattr(bpy.context, 'view_layer'):
                        bpy.context.view_layer.update()
            
        except Exception as e:
            print(f"Error in force_ui_update: {e}")

    def error(message="An error occurred"):
        bpy.context.window_manager.popup_menu(
            lambda self, context: self.layout.label(text=message),
            title="Error",
            icon='ERROR'
        )

    def reload_addon():
        """
        Reloads the current addon, useful for applying changes without restarting Blender.
        """
        import importlib
        import sys

        # Unregister the addon if it's already loaded
        if "scorg_tools" in sys.modules:
            try:
                scorg_tools.unregister()
            except Exception as e:
                print(f"Error during unregister: {e}")

            # List of submodules to reload (order matters: submodules first, then __init__)
            submodules = [
                "scorg_tools.globals_and_threading",
                "scorg_tools.misc_utils",
                "scorg_tools.tint_utils",
                "scorg_tools.blender_utils",
                "scorg_tools.import_utils",
                "scorg_tools.operators",
                "scorg_tools.panels",
                "scorg_tools.preferences",
                "scorg_tools",  # __init__.py last
            ]

            for modname in submodules:
                if modname in sys.modules:
                    importlib.reload(sys.modules[modname])

            # Now re-register the addon
            import scorg_tools
            scorg_tools.register()

    @staticmethod
    def show_text_popup(text_content="", header_text=""):
        """Show a popup with multi-line text and copy functionality"""
        # Convert list to string if needed
        if isinstance(text_content, list):
            text_content = '\n'.join(text_content)
        
        # Use the persistent operator instead of a temporary one
        bpy.ops.scorg.text_popup('INVOKE_DEFAULT', 
                                 text_content=text_content, 
                                 header_text=header_text)
    
    @staticmethod
    def get_addon_version():
        """
        Get the addon version from bl_info.
        Returns the version as a tuple (major, minor, patch)
        """
        from . import bl_info
        return ".".join(map(str, bl_info.get('version', None))) if bl_info else None

    @staticmethod
    def capture_console_output(func, *args, **kwargs):
        """
        Capture console output from a function call while still displaying it in the console.
        Returns a tuple: (function_result, captured_stdout, captured_stderr)
        """
        import sys
        import io
        import logging
        
        # Create string buffers to capture output
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        
        # Also capture logging output
        log_buffer = io.StringIO()
        
        # Custom tee class to duplicate output
        class TeeOutput:
            def __init__(self, original, buffer):
                self.original = original
                self.buffer = buffer
            
            def write(self, text):
                self.original.write(text)  # Write to console
                self.buffer.write(text)    # Write to buffer
                return len(text)
            
            def flush(self):
                self.original.flush()
                self.buffer.flush()
        
        # Custom log handler to capture logging output
        class BufferHandler(logging.Handler):
            def __init__(self, buffer):
                super().__init__()
                self.buffer = buffer
            
            def emit(self, record):
                log_msg = self.format(record)
                self.buffer.write(log_msg + '\n')
        
        # Set up tee outputs
        tee_stdout = TeeOutput(sys.stdout, stdout_buffer)
        tee_stderr = TeeOutput(sys.stderr, stderr_buffer)
        
        # Set up logging capture
        buffer_handler = BufferHandler(log_buffer)
        buffer_handler.setLevel(logging.WARNING)  # Capture WARNING and above
        
        # Get the scdatatools logger if it exists
        scdatatools_logger = logging.getLogger('scdatatools')
        original_level = scdatatools_logger.level
        
        function_result = None
        try:
            # Redirect both stdout and stderr through tee
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            sys.stdout = tee_stdout
            sys.stderr = tee_stderr
            
            # Add our buffer handler to capture logging output
            scdatatools_logger.addHandler(buffer_handler)
            scdatatools_logger.setLevel(logging.WARNING)
            
            # Run the function
            function_result = func(*args, **kwargs)
            
        finally:
            # Restore original outputs
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Remove our logging handler
            scdatatools_logger.removeHandler(buffer_handler)
            scdatatools_logger.setLevel(original_level)
        
        # Combine all captured output
        combined_stdout = stdout_buffer.getvalue() + log_buffer.getvalue()
        combined_stderr = stderr_buffer.getvalue()
        
        return function_result, combined_stdout, combined_stderr