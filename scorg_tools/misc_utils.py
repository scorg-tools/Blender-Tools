import bpy
from pathlib import Path

# Import globals
from . import globals_and_threading

class SCOrg_tools_misc():
    def get_ship_record():
        dcb = globals_and_threading.dcb
        empty_name = SCOrg_tools_misc.find_base_name()
        if empty_name:
            print(f"Found Empty object: {empty_name}")
            
            records = dcb.search_filename(f'libs/foundry/records/entities/spaceships/*{empty_name}.xml')
            if records == []:
                records = dcb.search_filename(f'libs/foundry/records/entities/groundvehicles/*{empty_name}.xml')
            if records == []:
                print(f"❌ Error, could not match ship or vehicle for {empty_name}")
                return None
            
            # Access global localizer
            if globals_and_threading.localizer:
                ship_name = globals_and_threading.localizer.gettext("vehicle_name"+empty_name.lower())
                globals_and_threading.ship_loaded = ship_name
            else:
                print("Warning: localizer not loaded, ship name might not be localized.")
                globals_and_threading.ship_loaded = empty_name # Fallback
            return records[0]
        else:
            print("❌ Error, no Empty object with 'container_name' = 'base' found.")
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
    
    def redraw():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

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