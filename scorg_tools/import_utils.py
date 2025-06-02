import bpy
from pathlib import Path
import os
import re

# Import globals
from . import globals_and_threading
from . import misc_utils # For SCOrg_tools_misc.error, get_ship_record, select_base_collection
from . import blender_utils # For SCOrg_tools_blender.fix_modifiers

class SCOrg_tools_import():
    def import_by_guid(guid):
        # Access global dcb and p4k
        dcb = globals_and_threading.dcb
        p4k = globals_and_threading.p4k

        print(f"Received GUID: {guid}")
        
        if not dcb:
            misc_utils.SCOrg_tools_misc.error(f"Please load Data.p4k first")
            return False
        
        #Load item by GUID
        record = dcb.records_by_guid.get(str(guid))

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            print(dcb)
            print(p4k)
            return False

        print(record)
        hardpoint_map = {}
        hardpoint_guid_map = {}
        geometry_path = __class__.get_geometry_path_by_guid(guid)
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_path = Path(prefs.extract_dir)
        #Loop through Components
        if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
            for i, comp in enumerate(record.properties.Components):
                if comp.name == 'SItemPortContainerComponentParams':
                    try:
                        # loop though SItemPortContainerComponentParams -> Ports
                        for port in comp.properties.Ports:
                            print(port.properties)
                            #get hardpoint name: port->AttachmentImplementation->Helper->Helper->Name
                            hardpoint = port.properties.AttachmentImplementation.properties.Helper.properties.Helper.properties.Name
                            #If hardpoint name found
                            if hardpoint:
                                #map SItemPortDef-> name : hardpoint name
                                port_name = port.properties.Name # Corrected: Access port.properties.Name directly
                                if port_name and port_name not in hardpoint_map:
                                    hardpoint_map[port_name] = hardpoint
                    except AttributeError as e:
                        print(f"⚠️ Missing attribute accessing record for import_by_guid: {e}")
            # restart the loop over components as we need to build up the map first
            for i, comp in enumerate(record.properties.Components):
                if comp.name == 'SEntityComponentDefaultLoadoutParams':
                    try:
                        #Loop through loadout -> entries
                        for entry in comp.properties.loadout.properties.entries:
                            print(entry.properties)
                            #get SItemPortLoadoutEntryParams -> itemPortName
                            if entry.properties.itemPortName and entry.properties.entityClassReference and entry.properties.entityClassReference != "00000000-0000-0000-0000-000000000000":
                                itemPortName = entry.properties.itemPortName
                                hardpoint_guid = str(entry.properties.entityClassReference)
                                print(f"found {itemPortName}: {hardpoint_guid}")
                                if itemPortName in hardpoint_map:
                                    print("Mapping to "+hardpoint_map[itemPortName])
                                    hardpoint_key = hardpoint_map[itemPortName]
                                    hardpoint_guid_map.setdefault(hardpoint_key, []).append(hardpoint_guid) # safe way to add items to non existing elements
                    except AttributeError as e:
                        print(f"⚠️ Missing attribute accessing record for import_by_guid: {e}")

            print(hardpoint_map)
            print(hardpoint_guid_map)

            missing_files = []
            # load the main .dae
            if geometry_path:
                print(f"Loading geo: {geometry_path}")
                if not geometry_path.is_file():
                    misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
                    print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                    missing_files.append(str(geometry_path));
                    print(f"ERROR: Failed to import DAE for {guid}: {geometry_path} - file missing")
                    print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k:")
                    print(missing_files)
                    return None
                bpy.ops.object.select_all(action='DESELECT')
                result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
                if 'FINISHED' not in result:
                    print(f"ERROR: Failed to import DAE for {guid}: {geometry_path}")
                    return None

                imported_objs = [obj for obj in bpy.context.selected_objects]
                # TODO: get base empty & set GUID as custom property on object

                empties_to_fill = __class__.get_all_empties()
                print("empties:")
                print(empties_to_fill)
                for hardpoint, guid_list in hardpoint_guid_map.items():
                    for guid in guid_list:
                        print(f"{hardpoint}: {guid}")
                        matching_empty = next((e for e in empties_to_fill if e.name == hardpoint), None)
                        if (matching_empty):
                            print(f'Matching empty: {matching_empty}')
                            # get dae for guid
                            geometry_path = __class__.get_geometry_path_by_guid(guid)
                            # import dae
                            if geometry_path:
                                if not geometry_path.is_file():
                                    misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
                                    print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                                    missing_files.append(str(geometry_path));
                                    #return {'CANCELLED'}
                                else:
                                    result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
                                    if 'FINISHED' not in result:
                                        print(f"ERROR: Failed to import DAE for {guid}: {geometry_path}")
                                        return None
                                    # Get all the imported objects
                                    imported_objs = [obj for obj in bpy.context.selected_objects]
                                    root_objs = [obj for obj in imported_objs if obj.parent is None]
                                    if not root_objs:
                                        print(f"WARNING: No root object found for: {geometry_path}")
                                        continue
                                    root_obj = root_objs[0]
                                    # Parent the base empty
                                    root_obj.parent = matching_empty
                                    root_obj.matrix_parent_inverse.identity() # set the inverse parent
                            else:
                                print(f"Skipping {hardpoint}: {guid}: no geometry")
                        else:
                            print(f"Skipping {hardpoint}: {guid}: no matching empty")

                # add modifiers
                blender_utils.SCOrg_tools_blender.fix_modifiers();
                if missing_files.count:
                    print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k:")
                    print(missing_files)

    def get_all_empties(hardpoints_only = False):
        if hardpoints_only:
            return [
                obj for obj in bpy.data.objects
                if obj.type == 'EMPTY'
                and obj.name.startswith('hardpoint_')
            ]
        else:
            return [
                obj for obj in bpy.data.objects
                if obj.type == 'EMPTY'
            ]
    
    def get_all_empties_blueprint():
        return [
            obj for obj in bpy.data.objects
            if obj.type == 'EMPTY'
            and 'orig_name' in obj.keys()
            and obj['orig_name'].startswith('hardpoint_')
        ]
    
    def get_geometry_path_by_guid(guid):
        dcb = globals_and_threading.dcb

        if not dcb:
            misc_utils.SCOrg_tools_misc.error(f"Please load Data.p4k first")
            return None

        # Load item by GUID
        record = dcb.records_by_guid.get(str(guid))

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return None

        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_path = Path(prefs.extract_dir)
        # Loop through Components
        if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
            for i, comp in enumerate(record.properties.Components):
                # Get geometry file
                if comp.name == 'SGeometryResourceParams':
                    try:
                        path = comp.properties.Geometry.properties.Geometry.properties.Geometry.properties.path
                        dae_path = Path(path).with_suffix('.dae')
                        print(f'Found geometry: {dae_path}')
                        return extract_path / dae_path
                    except AttributeError as e:
                        print(f"⚠️ Missing attribute accessing geometry path in component {i}: {e}")
                        return None
        return None

    def get_hardpoint_mapping_from_guid(guid):
        dcb = globals_and_threading.dcb
        mapping = {}
        try:
            record = dcb.records_by_guid.get(str(guid))
            if not record:
                print(f"⚠️  No record found for GUID: {guid}")
                return None
            for i, comp in enumerate(record.properties.Components):
                if comp.name == 'SItemPortContainerComponentParams':
                    try:
                        ports = comp.properties.Ports
                        for port in ports:
                            helper_name = port.properties['AttachmentImplementation'].properties['Helper'].properties['Helper'].properties['Name']
                            port_name = port.properties['Name']
                            mapping[helper_name] = port_name
                        return mapping
                    except AttributeError as e:
                        print(f"⚠️ Error accessing ports in component {comp.name}: {e}")
            return None
        except Exception as e:
            print(f"❌ Error in get_hardpoint_mapping_from_guid GUID {guid}: {e}")
            return None

    def duplicate_hierarchy_linked(original_obj, parent_empty):
        new_obj = original_obj.copy()
        new_obj.data = original_obj.data  # share mesh data (linked duplicate)
        new_obj.animation_data_clear()
        bpy.context.collection.objects.link(new_obj)

        new_obj.parent = parent_empty
        new_obj.matrix_parent_inverse.identity()

        for child in original_obj.children:
            __class__.duplicate_hierarchy_linked(child, new_obj)
    
    def import_hardpoint_hierarchy(loadout, empties_to_fill, is_top_level=True, parent_guid=None):        
        entries = loadout.properties.get('entries', [])
        missing_files = []
        print(f"DEBUG: import_hardpoint_hierarchy called with {len(entries)} entries, empties to fill: {len(empties_to_fill)}, is_top_level={is_top_level}, parent_guid={parent_guid}")

        # For nested calls, get the mapping for the parent_guid
        hardpoint_mapping = {}
        if not is_top_level and parent_guid:
            hardpoint_mapping = __class__.get_hardpoint_mapping_from_guid(parent_guid) or {}
            print(f"DEBUG: hardpoint_mapping for parent_guid {parent_guid}: {hardpoint_mapping}")

        for i, entry in enumerate(entries):
            props = entry.properties
            item_port_name = props.get('itemPortName')
            guid = props.get('entityClassReference')
            nested_loadout = props.get('loadout')

            print(f"DEBUG: Entry {i}: item_port_name='{item_port_name}', guid={guid}, has_nested_loadout={nested_loadout is not None}")

            if not item_port_name or not guid:
                print("DEBUG: Missing item_port_name or guid, skipping")
                continue

            # Apply filter ONLY at top level
            if is_top_level and __class__.INCLUDE_HARDPOINTS and item_port_name not in __class__.INCLUDE_HARDPOINTS:
                print(f"DEBUG: Skipping '{item_port_name}' due to top-level filter")
                continue

            # Use mapping if available (for nested)
            if not is_top_level and hardpoint_mapping:
                mapped_name = hardpoint_mapping.get(item_port_name, item_port_name)
            else:
                mapped_name = item_port_name

            print(f"DEBUG: Looking for matching empty with orig_name='{mapped_name}' (from item_port_name='{item_port_name}')")
            matching_empty = next(
                (e for e in empties_to_fill if __class__.matches_blender_name(e.get('orig_name', ''), mapped_name)),
                None
            )
            if not matching_empty:
                print(f"WARNING: No matching empty found for hardpoint '{mapped_name}' (original item_port_name: '{item_port_name}')")
                continue

            guid_str = str(guid)
            if guid_str == '00000000-0000-0000-0000-000000000000':
                print("DEBUG: GUID is all zeros, skipping geometry import")
                # Still recurse into nested loadout if present
                if nested_loadout:
                    entries_count = len(nested_loadout.properties.get('entries', []))
                    print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing into GUID {guid_str} (all zeros)...")
                    __class__.import_hardpoint_hierarchy(nested_loadout, empties_to_fill, is_top_level=False, parent_guid=guid_str)
                else:
                    print("DEBUG: No nested loadout found, recursion ends here")
                continue

            if guid_str in __class__.imported_guid_objects:
                original_root = __class__.imported_guid_objects[guid_str]
                __class__.duplicate_hierarchy_linked(original_root, matching_empty)
                print(f"Duplicated hierarchy for '{item_port_name}' from GUID {guid_str}")
            else:
                # Use __class__.get_geometry_path_by_guid instead of __class__.get_geometry_path_by_guid
                geometry_path = __class__.get_geometry_path_by_guid(guid_str)
                if geometry_path is None:
                    print(f"ERROR: No geometry for GUID {guid_str}: {geometry_path}")
                    continue

                if not geometry_path.exists():
                    misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
                    print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                    missing_files.append(str(geometry_path));
                    continue

                bpy.ops.object.select_all(action='DESELECT')
                result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
                if 'FINISHED' not in result:
                    print(f"ERROR: Failed to import DAE for {guid_str}: {geometry_path}")
                    continue

                imported_objs = [obj for obj in bpy.context.selected_objects]
                root_objs = [obj for obj in imported_objs if obj.parent is None]
                if not root_objs:
                    print(f"WARNING: No root object found for: {geometry_path}")
                    continue

                root_obj = root_objs[0]
                root_obj.parent = matching_empty
                root_obj.matrix_parent_inverse.identity()
                __class__.imported_guid_objects[guid_str] = root_obj

                imported_empties = [
                    obj for obj in imported_objs
                    if obj.type == 'EMPTY'
                ]

                mapping = __class__.get_hardpoint_mapping_from_guid(guid_str) or {}
                print(f"DEBUG: Imported empties: {[e.name for e in imported_empties]}")
                print(f"DEBUG: Mapping for imported GUID {guid_str}: {mapping}")
                for empty in imported_empties:
                    # Set orig_name to the mapping key if the name matches, otherwise to the base name without suffix
                    for key in mapping:
                        if __class__.matches_blender_name(empty.name, key):
                            empty['orig_name'] = mapping[key]
                            break
                    else:
                        empty['orig_name'] = re.sub(r'\.\d+$', '', empty.name)

                print(f"Imported object for '{item_port_name}' GUID {guid_str} → {geometry_path}")

                # Recurse into nested loadout with is_top_level=False and pass guid_str as parent_guid
                if nested_loadout:
                    entries_count = len(nested_loadout.properties.get('entries', []))
                    print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing into GUID {guid_str}...")
                    __class__.import_hardpoint_hierarchy(nested_loadout, imported_empties, is_top_level=False, parent_guid=guid_str)
                else:
                    print("DEBUG: No nested loadout found, recursion ends here")
        if missing_files.count:
            print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k if you want a more complete loadout:")
            print(missing_files)

    def run_import():
        # Access global dcb
        dcb = globals_and_threading.dcb

        os.system('cls')
        __class__.imported_guid_objects = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        
        # Access addon preferences via bpy.context
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        __class__.extract_dir = Path(prefs.extract_dir) # Ensure Path object
        
        misc_utils.SCOrg_tools_misc.select_base_collection() # Ensure the base collection is active before importing
        record = misc_utils.SCOrg_tools_misc.get_ship_record(dcb)
        
        # Check if record is None before trying to access its properties
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not get ship record. Please ensure a 'base' empty object exists and Data.p4k is loaded correctly.")
            return

        # Safely access Components and loadout
        top_level_loadout = None
        if hasattr(record, 'properties') and hasattr(record.properties, 'Components') and len(record.properties.Components) > 1:
            if hasattr(record.properties.Components[1], 'reference') and hasattr(record.properties.Components[1].reference, 'properties'):
                top_level_loadout = record.properties.Components[1].reference.properties.get('loadout')

        if top_level_loadout is None:
            misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            return

        empties_to_fill = __class__.get_all_empties_blueprint()

        print(f"Total hardpoints to import: {len(empties_to_fill)}")

        __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill)
        blender_utils.SCOrg_tools_blender.fix_modifiers()

    def matches_blender_name(name, target):
        return name == target or re.match(rf"^{re.escape(target)}\.\d+$", name)
