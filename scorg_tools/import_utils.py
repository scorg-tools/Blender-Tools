import bpy
from pathlib import Path
import os
import re

# Import globals
from . import globals_and_threading
from . import misc_utils # For SCOrg_tools_misc.error, get_ship_record, select_base_collection
from . import blender_utils # For SCOrg_tools_blender.fix_modifiers

class SCOrg_tools_import():
    def get_record(id):
        """
        Get a record by GUID from the global dcb.
        If name is provided, it will return the record with that name.
        """
        dcb = globals_and_threading.dcb
        if not dcb:
            misc_utils.SCOrg_tools_misc.error("Please load Data.p4k first")
            return None
        id = str(id).strip()  # Ensure id is a string and strip whitespace
        if __class__.is_guid(id): # is a non-zero GUID format
            record = dcb.records_by_guid.get(id)
            if record:
                return record
            else:
                misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
                return None
        else:
            # Otherwise, try to get by name
            for record in dcb.records:
                if hasattr(record, 'name') and record.name.lower() == id.lower():
                    return record
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record with name: {id}")
            return None

    def get_guid_by_name(name):
        record = __class__.get_record(name)
        if record:
            return str(record.id)
        else:
            return None
    
    def import_by_id(id):
        os.system('cls')
        print(f"Received ID: {id}")
        if __class__.is_guid(id):
            guid = str(id)
        else:
            guid = __class__.get_guid_by_name(id)
        print(f"Resolved GUID: {guid}")
        if not __class__.is_guid(guid):
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Invalid: {guid}")
            return False

        __class__.imported_guid_objects = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        
        # Access addon preferences via bpy.context
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        __class__.extract_dir = Path(prefs.extract_dir) # Ensure Path object
                
        #Load item by GUID
        record = __class__.get_record(guid)

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return False

        geometry_path = __class__.get_geometry_path_by_guid(guid)

        missing_files = []
        # load the main .dae
        if geometry_path:
            print(f"Loading geo: {geometry_path}")
            if not geometry_path.is_file():
                misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
                print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                if str(geometry_path) not in missing_files:
                    missing_files.append(str(geometry_path))
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


            # Safely access Components and loadout
            top_level_loadout = __class__.get_loadout_from_record(record)

            if top_level_loadout is None:
                misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
                return

            empties_to_fill = __class__.get_all_empties_blueprint()
            print(empties_to_fill)
            print(f"Total hardpoints to import: {len(empties_to_fill)}")

            # Pretend that it's not the top level, so we can import the hierarchy without needing the orig_name custom property on the empties
            __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill, is_top_level=False, parent_guid=guid)

            # add modifiers
            blender_utils.SCOrg_tools_blender.fix_modifiers();
            if len(missing_files) > 0:
                print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k:")
                print(missing_files)
    
    def get_all_empties_blueprint():
        # find all objects that are empties and have no children
        empty_hardpoints = [
            obj for obj in bpy.data.objects
            if obj.type == 'EMPTY'
            and len(obj.children)==0
        ]
        # find all objects that are empties and have children
        filled_hardpoints = [
            obj for obj in bpy.data.objects
            if obj.type == 'EMPTY'
            and len(obj.children)>0
        ]
        # find all objects that are empties and have an orig_name key
        original_hardpoints = [
            obj for obj in bpy.data.objects
            if obj.type == 'EMPTY'
            and 'orig_name' in obj.keys()
            and len(obj.children)==0
        ]
        empty_names = [obj.name for obj in empty_hardpoints]
        filled_names = [obj.name for obj in filled_hardpoints]
        for obj in original_hardpoints:
            # add objects to empty_hardpoints unles the orig_name matches the name of an existing hardpoint
            # or the orig_name matches the name of an existing filled hardpoint
            if obj['orig_name'] not in empty_names and obj['orig_name'] not in filled_names:
                empty_hardpoints.append(obj)
        return empty_hardpoints
    
    def get_geometry_path_by_guid(guid):
        dcb = globals_and_threading.dcb

        if not dcb:
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Please load Data.p4k first")
            return None

        # Load item
        record = __class__.get_record(guid)

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return None

        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_path = Path(prefs.extract_dir)
        # Loop through Components
        try:
            if hasattr(record, 'properties'):
                if hasattr(record.properties, 'Components'):
                    for i, comp in enumerate(record.properties.Components):
                        # Get geometry file
                        if comp.name == 'SGeometryResourceParams':
                            try:
                                path = comp.properties.Geometry.properties.Geometry.properties.Geometry.properties.path
                                if path:
                                    path = path.removeprefix("Data/") # Rare objects have this prefix and they shouldn't see b8f6e23e-8a06-47e4-81c9-3f22c34b99e9
                                    dae_path = Path(path).with_suffix('.dae')
                                    print(f'Found geometry: {dae_path}')
                                    return (extract_path / dae_path)
                                print(f"⚠️ Missing geometry path in component {i}")
                                return None
                            except AttributeError as e:
                                print(f"⚠️ Missing attribute accessing geometry path in component {i}: {e}")
                                return None
        except Exception as e:
            print(f"❌ Error in get_geometry_path_by_guid GUID {guid}: {e}")
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
                        if not ports or len(ports) == 0:
                            print(f"⚠️  No Ports defined in SItemPortContainerComponentParams for GUID: {guid}")
                        for port in ports:
                            helper_name = port.properties['AttachmentImplementation'].properties['Helper'].properties['Helper'].properties['Name']
                            port_name = port.properties['Name']
                            if helper_name not in mapping:
                                mapping[helper_name] = []
                            mapping[helper_name].append(port_name)
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
            props = getattr(entry, 'properties', entry)
            item_port_name = props.get('itemPortName')
            guid = props.get('entityClassReference')
            nested_loadout = props.get('loadout')

            entity_class_name = getattr(props, 'entityClassName', None)
            # Always print debug for every entry
            print(f"DEBUG: Entry {i}: item_port_name='{item_port_name}', guid={guid}, entityClassName={entity_class_name}, has_nested_loadout={nested_loadout is not None}")

            if not item_port_name or (not guid and not entity_class_name):
                print("DEBUG: Missing item_port_name or guid and name, skipping")
                continue

            # Apply filter ONLY at top level
            if is_top_level and __class__.INCLUDE_HARDPOINTS and item_port_name not in __class__.INCLUDE_HARDPOINTS:
                print(f"DEBUG: Skipping '{item_port_name}' due to top-level filter")
                continue

            # Use mapping if available (for nested)
        #    if not is_top_level and hardpoint_mapping:
        #        mapped_name = hardpoint_mapping.get(item_port_name, item_port_name)
        #    else:
        #       mapped_name = {item_port_name}

            mapped_name = item_port_name
            for hardpoint_name, item_port_names in hardpoint_mapping.items():
                print(f"DEBUG: Checking hardpoint mapping: {hardpoint_name} -> {item_port_names}")
                if item_port_name in item_port_names:
                    mapped_name = hardpoint_name
                    break
            print(f"DEBUG: Looking for matching empty for item_port_name='{item_port_name}', mapped_name='{mapped_name}'")
            matching_empty = None
            for empty in empties_to_fill:
                orig_name = empty.get('orig_name', '') if hasattr(empty, 'get') else ''
                if __class__.matches_blender_name(orig_name, mapped_name) or __class__.matches_blender_name(empty.name, mapped_name):
                    matching_empty = empty
                    break
            if not matching_empty:
                print(f"WARNING: No matching empty found for hardpoint '{mapped_name}' (original item_port_name: '{item_port_name}'), skipping this entry")
                continue
            else:
                print(f"DEBUG: Found matching empty: {matching_empty.name} for hardpoint '{mapped_name}, item port: {item_port_name}'")

            guid_str = str(guid)
            if not __class__.is_guid(guid_str): # must be 00000000-0000-0000-0000-000000000000 or blank
                if not entity_class_name:
                    print("DEBUG: GUID is all zeros, but no entityClassName found, skipping geometry import")
                    # Still recurse into nested loadout if present
                    if nested_loadout:
                        entries_count = len(nested_loadout.properties.get('entries', []))
                        print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing into GUID {guid_str} (all zeros)...")
                        __class__.import_hardpoint_hierarchy(nested_loadout, empties_to_fill, is_top_level=False, parent_guid=guid_str)
                    else:
                        print("DEBUG: No nested loadout found, recursion ends here")
                    continue
                else:
                    # Get the GUID from the entity_class_name
                    guid_str = __class__.get_guid_by_name(entity_class_name)
                    if not guid_str or not __class__.is_guid(guid_str):
                        print(f"DEBUG: Could not resolve GUID for entityClassName '{entity_class_name}', skipping import")
                        continue

            if not nested_loadout:
                # If no nested loadout, load the record for the GUID and check for a default loadout
                print (f"DEBUG: No nested loadout found, loading record for GUID: {guid_str}")
                child_record = __class__.get_record(guid_str)
                if child_record:
                    nested_loadout = __class__.get_loadout_from_record(child_record)
                    if not nested_loadout:
                       print(f"DEBUG: Could not find a nested loadout for GUID {guid_str}: {nested_loadout}")
                    else:
                        print(f"DEBUG: Found nested loadout for GUID {guid_str}: {nested_loadout}")
                        from pprint import pprint
                        pprint(child_record)
                        pprint(nested_loadout)



            if guid_str in __class__.imported_guid_objects:
                # If the GUID is already imported, duplicate the hierarchy linked
                original_root = __class__.imported_guid_objects[guid_str]
                __class__.duplicate_hierarchy_linked(original_root, matching_empty)
                print(f"Duplicated hierarchy for '{item_port_name}' from GUID {guid_str}")
            else:
                # The item was not imported yet, so we need to import it
                geometry_path = __class__.get_geometry_path_by_guid(guid_str)
                if geometry_path is None:
                    print(f"ERROR: No geometry for GUID {guid_str}: {geometry_path}")
                    continue

                if not geometry_path.exists():
                    misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
                    print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                    if str(geometry_path) not in missing_files:
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
                            value = mapping[key]
                            if isinstance(value, list) and value:
                                empty['orig_name'] = value[0]
                            else:
                                empty['orig_name'] = value
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
        if len(missing_files) > 0:
            print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k if you want a more complete loadout:")
            print(missing_files)

    def run_import():
        
        os.system('cls')
        __class__.imported_guid_objects = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        
        # Access addon preferences via bpy.context
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        __class__.extract_dir = Path(prefs.extract_dir) # Ensure Path object
        
        misc_utils.SCOrg_tools_misc.select_base_collection() # Ensure the base collection is active before importing
        record = misc_utils.SCOrg_tools_misc.get_ship_record()
        
        # Check if record is None before trying to access its properties
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not get ship record. Please ensure a 'base' empty object exists and Data.p4k is loaded correctly.")
            return

        # Safely access Components and loadout
        top_level_loadout = __class__.get_loadout_from_record(record)

        if top_level_loadout is None:
            misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            return

        empties_to_fill = __class__.get_all_empties_blueprint()

        print(f"Total hardpoints to import: {len(empties_to_fill)}")

        __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill)
        blender_utils.SCOrg_tools_blender.fix_modifiers()

    def get_loadout_from_record(record):
        print(f"DEBUG: get_loadout_from_record called with record: {record.name}")
        loadout = None
        try:
            if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
                    print("DEBUG: Record has Components, checking for loadout...")
                    for comp in record.properties.Components:
                        if hasattr(comp, 'name') and comp.name == "SEntityComponentDefaultLoadoutParams":
                            if hasattr(comp.properties, 'loadout'):
                                print("DEBUG: Found loadout")
                                return comp.properties.loadout
        except Exception as e:
            print(f"DEBUG: Error accessing Components in record {record.name}: {e}")
        print("DEBUG: Record has no loadout")
        return None
    
    def matches_blender_name(name, target):
        #print(f"DEBUG: matches_blender_name called with name='{name}', target='{target}'")
        return name == target or re.match(rf"^{re.escape(target)}\.\d+$", name)

    def is_guid(s):
        """
        Returns True if s is a valid GUID and non-zero string.
        """
        if s == "00000000-0000-0000-0000-000000000000":
            return False
        return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", str(s)))