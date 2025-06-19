import bpy
from pathlib import Path
import os
import re
# Import globals
from . import globals_and_threading
from . import misc_utils # For SCOrg_tools_misc.error, get_ship_record, select_base_collection
from . import blender_utils # For SCOrg_tools_blender.fix_modifiers
from . import tint_utils # For SCOrg_tools_tint.get_tint_pallets

class SCOrg_tools_import():
    item_name = None
    item_guid = None
    
    def init():
        if globals_and_threading.debug: print("SCOrg_tools_import initialized")
        __class__.prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        __class__.extract_dir = Path(__class__.prefs.extract_dir) # Ensure Path object
        __class__.missing_files = []  # List to track missing files
        __class__.item_name = None
        __class__.item_guid = None
        __class__.tint_palette_node_group_name = None
        __class__.default_tint_guid = None

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
                if not __class__.item_name:
                    __class__.item_name = record.name
                    __class__.item_guid = id
                return record
            else:
                misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {id} - are you using the correct Data.p4k?")
                return None
        else:
            # Otherwise, try to get by name
            for record in dcb.records:
                if hasattr(record, 'name') and record.name.lower() == id.lower():
                    if not __class__.item_name:
                        __class__.item_name = record.name
                        __class__.item_guid = id
                    return record
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record with name: {id}")
            return None

    def get_guid_by_name(name):
        record = __class__.get_record(name)
        if record:
            return str(record.id)
        else:
            return None

    def replace_selected_mesh_with_empties():
        for obj in list(bpy.context.selected_objects):
            if obj.type == 'MESH':
                # Store transform and parent info
                obj_name = obj.name
                obj_loc = obj.location.copy()
                obj_rot = obj.rotation_euler.copy()
                obj_scale = obj.scale.copy()
                obj_parent = obj.parent
                obj_matrix_parent_inverse = obj.matrix_parent_inverse.copy()
                children = list(obj.children)

                # Delete the mesh object first
                bpy.data.objects.remove(obj, do_unlink=True)

                # Create the empty with the original name
                empty = bpy.data.objects.new(obj_name, None)
                empty.location = obj_loc
                empty.rotation_euler = obj_rot
                empty.scale = obj_scale
                bpy.context.collection.objects.link(empty)
                empty.parent = obj_parent
                if obj_parent:
                    empty.matrix_parent_inverse = obj_matrix_parent_inverse

                # Re-parent all children to the new empty and preserve transforms
                for child in children:
                    child.parent = empty
                    child.matrix_parent_inverse.identity()

    def import_by_id(id):
        os.system('cls')
        if globals_and_threading.debug: print(f"Received ID: {id}")
        if __class__.is_guid(id):
            guid = str(id)
        else:
            guid = __class__.get_guid_by_name(id)
        if globals_and_threading.debug: print(f"Resolved GUID: {guid}")
        if not __class__.is_guid(guid):
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Invalid: {guid}")
            return False

        __class__.imported_guid_objects = {}
        __class__.skip_imported_files = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        __class__.missing_files = []
                
        #Load item by GUID
        record = __class__.get_record(guid)

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return False
        
        __class__.item_name = record.name
        __class__.item_guid = guid
        tint_utils.SCOrg_tools_tint.update_tints(record)  # Update tints for the item
        
        geometry_path = __class__.get_geometry_path_by_guid(guid)
        process_bones_file = False
        # if the geometry path is an array, it means we have a CDF XML file that points to the real geometry
        if isinstance(geometry_path, list):
            if globals_and_threading.debug: print(f"DEBUG: CDF XML file found with references to: {geometry_path}")
            process_bones_file = geometry_path
            geometry_path = process_bones_file.pop(0)  # Get the first file in the array, which is the base armature DAE file (or sometimes the base geometry)

        # load the main .dae
        if geometry_path:
            if globals_and_threading.debug: print(f"Loading geo: {geometry_path}")
            if not geometry_path.is_file():
                print(f"Error: .DAE file not found at: {geometry_path}")
                if globals_and_threading.debug: print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                if str(geometry_path) not in __class__.missing_files:
                    __class__.missing_files.append(str(geometry_path))
                print(f"⚠️ ERROR: Failed to import DAE for {guid}: {geometry_path} - file missing")
                misc_utils.SCOrg_tools_misc.show_text_popup(
                    text_content=__class__.missing_files,
                    header_text="The following files were missing, please extract them with StarFab, under Data -> Data.p4k:"
                )
                return None
            
            # Get a set of all objects before import
            before = set(bpy.data.objects)

            bpy.ops.object.select_all(action='DESELECT')
            result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
            if 'FINISHED' not in result:
                print(f"⚠️ ERROR: Failed to import DAE for {guid}: {geometry_path}")
                return None

            # Get a set of all objects after import
            after = set(bpy.data.objects)

            # The difference is the set of newly imported objects
            imported_objs = list(after - before)

            # Find root objects (those without a parent)
            root_objs = [obj for obj in imported_objs if obj.parent is None]
            root_object_name = None
            if root_objs:
                root_object_name = geometry_path.stem
                root_objs[0].name = root_object_name  # Set the name to the file name (without extension)
                # set GUID as custom property on object
                root_objs[0]['guid'] = guid
                root_objs[0]['orig_name'] = root_object_name
                root_objs[0]['geometry_path'] = str(geometry_path)
            if globals_and_threading.debug: print(f"DEBUG: post-import root object: {root_object_name}")

            top_level_loadout = __class__.get_loadout_from_record(record)
            displacement_strength = 0.001
            if process_bones_file:
                if globals_and_threading.debug: print("Deleting meshes for initial CDF base import")
                # Usually used for smaller items like weapons, so change the POM/Decal displacement strength to 0.5mm
                displacement_strength = 0.0005
                # Delete all meshes to avoid conflicts with CDF imports, the imported .dae objects will be selected
                __class__.replace_selected_mesh_with_empties()
                
                if globals_and_threading.debug: print(f"Converting bones to empties for {guid}: {geometry_path}")
                blender_utils.SCOrg_tools_blender.convert_armatures_to_empties()
                
                if not root_object_name:
                    if globals_and_threading.debug: print(f"WARNING: No root object found for: {geometry_path}")
                
                for file in process_bones_file:
                    if not file.is_file():
                        if globals_and_threading.debug: print(f"⚠️ ERROR: Bones file missing: {file}")
                        if str(file) not in __class__.missing_files:
                            __class__.missing_files.append(str(file))
                        continue
                    if globals_and_threading.debug: print(f"Processing bones file: {file}")
                    __class__.import_file(file, root_object_name)
                if globals_and_threading.debug: print("DEBUG: Finished processing bones files")

            if top_level_loadout is None:
                misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            else:
                empties_to_fill = __class__.get_all_empties_blueprint()
                if globals_and_threading.debug: print(empties_to_fill)
                if globals_and_threading.debug: print(f"Total hardpoints to import: {len(empties_to_fill)}")

                # Pretend that it's not the top level, so we can import the hierarchy without needing the orig_name custom property on the empties
                __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill, is_top_level=False, parent_guid=guid)

            # add modifiers
            blender_utils.SCOrg_tools_blender.fix_modifiers(displacement_strength);
            globals_and_threading.item_loaded = True
            if len(__class__.missing_files) > 0:
                misc_utils.SCOrg_tools_misc.show_text_popup(
                    text_content=__class__.missing_files,
                    header_text="The following files were missing, please extract them with StarFab, under Data -> Data.p4k:"
                )
    
    def get_all_empties_blueprint():
        # First find the base container empty
        base_empty = None
        for obj in bpy.data.objects:
            if obj.type == 'EMPTY' and 'container_name' in obj and obj['container_name'] == 'base':
                base_empty = obj
                break
        
        if not base_empty:
            if globals_and_threading.debug: print("WARNING: No base container empty found, using all empties")
            # Fallback to original behavior if no base found
            return [
                obj for obj in bpy.data.objects
                if obj.type == 'EMPTY' and len(obj.children) == 0
            ]
        
        if globals_and_threading.debug: print(f"DEBUG: Found base container: {base_empty.name}")
        
        def is_descendant_of(obj, ancestor):
            """Check if obj is a descendant (child, grandchild, etc.) of ancestor"""
            current = obj.parent
            while current:
                if current == ancestor:
                    return True
                current = current.parent
            return False
        
        def normalize_hardpoint_name(name):
            """Strip GUID prefixes and .001 suffixes to get base name"""
            if not name:
                return ""
            
            # Remove GUID prefix (6-char hex + underscore)
            guid_pattern = r"^[a-f0-9]{6}_(.+)$"
            match = re.match(guid_pattern, name, re.IGNORECASE)
            if match:
                name = match.group(1)
            
            # Remove .001 suffixes
            name = re.sub(r'\.\d+$', '', name)
            return name.lower()  # Convert to lowercase for consistent comparison
        
        def has_mesh_children(obj):
            """Check if object has any mesh children (recursively)"""
            for child in obj.children:
                if child.type == 'MESH':
                    return True
                if has_mesh_children(child): # Check recursively
                    return True
            return False
        
        # Get all empties that are descendants of the base container
        base_descendants = [
            obj for obj in bpy.data.objects
            if obj.type == 'EMPTY' and (obj == base_empty or is_descendant_of(obj, base_empty))
        ]
        
        if globals_and_threading.debug: print(f"DEBUG: Found {len(base_descendants)} total empties under base container")
        
        # Build a map of normalized names to empties with geometry
        filled_hardpoint_names = {}
        for obj in base_descendants:
            if has_mesh_children(obj):
                # This empty has geometry - check both name and orig_name
                names_to_check = [obj.name]
                if 'orig_name' in obj:
                    names_to_check.append(obj['orig_name'])
                
                for name_to_check in names_to_check:
                    normalized_name = normalize_hardpoint_name(name_to_check)
                    if normalized_name:
                        if normalized_name not in filled_hardpoint_names:
                            filled_hardpoint_names[normalized_name] = []
                        filled_hardpoint_names[normalized_name].append(obj)
        
        if globals_and_threading.debug: 
            print(f"DEBUG: Found {len(filled_hardpoint_names)} hardpoint types already filled:")
            for name, objs in filled_hardpoint_names.items():
                print(f"  '{name}': {len(objs)} objects - {[obj.name for obj in objs[:3]]}{'...' if len(objs) > 3 else ''}")
        
        # Find empty hardpoints, excluding those that have variants with geometry
        empty_hardpoints = []
        skipped_count = 0
        
        for obj in base_descendants:
            if len(obj.children) == 0:  # Empty hardpoint
                # Check both name and orig_name
                names_to_check = [obj.name]
                if 'orig_name' in obj:
                    names_to_check.append(obj['orig_name'])
                
                is_already_filled = False
                for name in names_to_check:
                    normalized = normalize_hardpoint_name(name)
                    if normalized and normalized in filled_hardpoint_names:
                        is_already_filled = True
                        if globals_and_threading.debug:
                            filled_examples = [filled_obj.name for filled_obj in filled_hardpoint_names[normalized][:2]]
                            print(f"DEBUG: Skipping empty '{obj.name}' (orig_name: '{obj.get('orig_name', 'None')}') - normalized name '{normalized}' already filled by: {filled_examples}")
                        break
                
                if not is_already_filled:
                    empty_hardpoints.append(obj)
                else:
                    skipped_count += 1
        
        if globals_and_threading.debug: 
            print(f"DEBUG: Filtered to {len(empty_hardpoints)} empty hardpoints (skipped {skipped_count} already filled)")
        
        return empty_hardpoints
    
    def get_geometry_path_by_guid(guid):
        hasattr(__class__, 'extract_dir') or __class__.init()
        dcb = globals_and_threading.dcb

        if not dcb:
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Please load Data.p4k first")
            return None

        # Load item
        record = __class__.get_record(guid)

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return None

        # Loop through Components to get geometry path
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
                                    file_path = __class__.extract_dir / Path(path)
                                    if file_path.suffix.lower() == '.cdf':
                                        file_array = [__class__.extract_dir / file_path.with_suffix('.dae')] # add the base armature dae file to the array
                                        if file_path.is_file():
                                            # This is likely a weapon or similar, this is an XML file that points to the real base geometry
                                            if globals_and_threading.debug: print(f"Found CDF XML: {file_path}")
                                            # Read the CDF XML file to find the DAE path
                                            from scdatatools.engine import cryxml
                                            tree = cryxml.etree_from_cryxml_file(file_path)
                                            root = tree.getroot()
                                            geo_path = None
                                            for attachment_list in root.findall("AttachmentList"):
                                                for attachment in attachment_list.findall("Attachment"):
                                                    binding = attachment.attrib.get("Binding")
                                                    if not binding:
                                                        continue
                                                    geo_path = (__class__.extract_dir / Path(binding)).with_suffix('.dae')
                                                    if globals_and_threading.debug: print(f"Found geometry path in CDF XML: {geo_path}")
                                                    file_array.append(geo_path)
                                            if globals_and_threading.debug: print(f"Returning geometry file array: {file_array}")
                                            return file_array
                                        else:
                                            print(f"⚠️ CDF XML file not found: {file_path}. Please extract it with StarFab, under Data -> Data.p4k")
                                            return None
                                    dae_path = file_path.with_suffix('.dae')
                                    if globals_and_threading.debug: print(f'Found geometry: {dae_path}')
                                    return (__class__.extract_dir / dae_path)
                                if globals_and_threading.debug: print(f"⚠️ Missing geometry path in component {i}")
                                return None
                            except AttributeError as e:
                                if globals_and_threading.debug: print(f"⚠️ Missing attribute accessing geometry path in component {i}: {e}")
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
                            if globals_and_threading.debug: print(f"⚠️  No Ports defined in SItemPortContainerComponentParams for GUID: {guid}")
                        for port in ports:
                            helper_name = port.properties['AttachmentImplementation'].properties['Helper'].properties['Helper'].properties['Name']
                            port_name = port.properties['Name']
                            if helper_name not in mapping:
                                mapping[helper_name] = []
                            mapping[helper_name].append(port_name)
                        return mapping
                    except AttributeError as e:
                        if globals_and_threading.debug: print(f"⚠️ Error accessing ports in component {comp.name}: {e}")
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

        # Initialize timer on first call (top level)
        if is_top_level:
            blender_utils.SCOrg_tools_blender.update_viewport_with_timer(force_reset=True)

        # For nested calls, get the mapping for the parent_guid
        hardpoint_mapping = {}
        if not is_top_level and parent_guid:
            hardpoint_mapping = __class__.get_hardpoint_mapping_from_guid(parent_guid) or {}
        
        # Only show progress at the top level
        if is_top_level:
            misc_utils.SCOrg_tools_misc.update_progress("Importing hardpoints", 0, len(entries), force_update=True, spinner_type="arc")
        
        for i, entry in enumerate(entries):
            # Only update progress at the top level
            if is_top_level:
                misc_utils.SCOrg_tools_misc.update_progress(f"Importing hardpoint {i+1}/{len(entries)}", i+1, len(entries), spinner_type="arc", update_interval=1)
            
            blender_utils.SCOrg_tools_blender.update_viewport_with_timer(interval_seconds=1.0)

            props = getattr(entry, 'properties', entry)
            item_port_name = props.get('itemPortName')
            guid = props.get('entityClassReference')
            nested_loadout = props.get('loadout')

            entity_class_name = getattr(props, 'entityClassName', None)
            # Always print debug for every entry
            if globals_and_threading.debug: print(f"DEBUG: Entry {i}: item_port_name='{item_port_name}', guid={guid}, entityClassName={entity_class_name}, has_nested_loadout={nested_loadout is not None}")

            if not item_port_name or (not guid and not entity_class_name):
                if globals_and_threading.debug: print("DEBUG: Missing item_port_name or guid and name, skipping")
                continue

            # Apply filter ONLY at top level
            if is_top_level and __class__.INCLUDE_HARDPOINTS and item_port_name not in __class__.INCLUDE_HARDPOINTS:
                if globals_and_threading.debug: print(f"DEBUG: Skipping '{item_port_name}' due to top-level filter")
                continue

            # Use mapping if available (for nested)
        #    if not is_top_level and hardpoint_mapping:
        #        mapped_name = hardpoint_mapping.get(item_port_name, item_port_name)
        #    else:
        #       mapped_name = {item_port_name}

            mapped_name = item_port_name
            for hardpoint_name, item_port_names in hardpoint_mapping.items():
                if globals_and_threading.debug: print(f"DEBUG: Checking hardpoint mapping: {hardpoint_name} -> {item_port_names}")
                if item_port_name in item_port_names:
                    mapped_name = hardpoint_name
                    break
            if globals_and_threading.debug: print(f"DEBUG: Looking for matching empty for item_port_name='{item_port_name}', mapped_name='{mapped_name}'")
            matching_empty = None
            for empty in empties_to_fill:
                orig_name = empty.get('orig_name', '') if hasattr(empty, 'get') else ''
                if __class__.matches_blender_name(orig_name, mapped_name) or __class__.matches_blender_name(empty.name, mapped_name):
                    matching_empty = empty
                    break
            if not matching_empty:
                if globals_and_threading.debug: print(f"WARNING: No matching empty found for hardpoint '{mapped_name}' (original item_port_name: '{item_port_name}'), skipping this entry")
                continue
            else:
                if globals_and_threading.debug: print(f"DEBUG: Found matching empty: {matching_empty.name} for hardpoint '{mapped_name}, item port: {item_port_name}'")

            guid_str = str(guid)
            if not __class__.is_guid(guid_str): # must be 00000000-0000-0000-0000-000000000000 or blank
                if not entity_class_name:
                    if globals_and_threading.debug: print("DEBUG: GUID is all zeros, but no entityClassName found, skipping geometry import")
                    # Still recurse into nested loadout if present
                    if nested_loadout:
                        entries_count = len(nested_loadout.properties.get('entries', []))
                        if globals_and_threading.debug: print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing into GUID {guid_str} (all zeros)...")
                        __class__.import_hardpoint_hierarchy(nested_loadout, empties_to_fill, is_top_level=False, parent_guid=guid_str)
                    else:
                        if globals_and_threading.debug: print("DEBUG: No nested loadout found, recursion ends here")
                    continue
                else:
                    # Get the GUID from the entity_class_name
                    guid_str = __class__.get_guid_by_name(entity_class_name)
                    if not guid_str or not __class__.is_guid(guid_str):
                        if globals_and_threading.debug: print(f"DEBUG: Could not resolve GUID for entityClassName '{entity_class_name}', skipping import")
                        continue

            if not nested_loadout:
                # If no nested loadout, load the record for the GUID and check for a default loadout
                if globals_and_threading.debug: print (f"DEBUG: No nested loadout found, loading record for GUID: {guid_str}")
                child_record = __class__.get_record(guid_str)
                if child_record:
                    nested_loadout = __class__.get_loadout_from_record(child_record)
                    if not nested_loadout:
                       if globals_and_threading.debug: print(f"DEBUG: Could not find a nested loadout for GUID {guid_str}: {nested_loadout}")
                    else:
                        if globals_and_threading.debug: print(f"DEBUG: Found nested loadout for GUID {guid_str}: {nested_loadout}")
                        from pprint import pprint
                        pprint(child_record)
                        pprint(nested_loadout)



            if guid_str in __class__.imported_guid_objects:
                # If the GUID is already imported, duplicate the hierarchy linked
                original_root = __class__.imported_guid_objects[guid_str]
                __class__.duplicate_hierarchy_linked(original_root, matching_empty)
                if globals_and_threading.debug: print(f"Duplicated hierarchy for '{item_port_name}' from GUID {guid_str}")
            else:
                # The item was not imported yet, so we need to import it
                geometry_path = __class__.get_geometry_path_by_guid(guid_str)
                if geometry_path is None:
                    if globals_and_threading.debug: print(f"ERROR: No geometry for GUID {guid_str}: {geometry_path}")
                    continue

                process_bones_file = False
                # if the geometry path is an array, it means we have a CDF XML file that points to the real geometry
                if isinstance(geometry_path, list):
                    if globals_and_threading.debug: print(f"DEBUG: CDF XML file found with references to: {geometry_path}")
                    process_bones_file = geometry_path
                    geometry_path = process_bones_file.pop(0)  # Get the first file in the array, which is the base armature DAE file

                if not geometry_path.exists():
                    print(f"Error: .DAE file not found at: {geometry_path}")
                    if globals_and_threading.debug: print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                    if str(geometry_path) not in __class__.missing_files:
                        __class__.missing_files.append(str(geometry_path));
                    continue

                bpy.ops.object.select_all(action='DESELECT')
                result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
                if 'FINISHED' not in result:
                    if globals_and_threading.debug: print(f"ERROR: Failed to import DAE for {guid_str}: {geometry_path}")
                    continue

                imported_objs = [obj for obj in bpy.context.selected_objects]
                root_objs = [obj for obj in imported_objs if obj.parent is None]
                if not root_objs:
                    if globals_and_threading.debug: print(f"WARNING: No root object found for: {geometry_path}")
                    continue

                root_obj = root_objs[0]
                root_obj.parent = matching_empty
                root_obj.matrix_parent_inverse.identity()
                __class__.imported_guid_objects[guid_str] = root_obj

                if process_bones_file:
                    if globals_and_threading.debug: print("Deleting meshes for CDF import")
                    # Delete all meshes to avoid conflicts with CDF imports, the imported .dae objects will be selected
                    __class__.replace_selected_mesh_with_empties()
                    
                    if globals_and_threading.debug: print(f"Converting bones to empties for {guid_str}: {geometry_path}")
                    blender_utils.SCOrg_tools_blender.convert_armatures_to_empties()
                    
                    for file in process_bones_file:
                        if not file.is_file():
                            if globals_and_threading.debug: print(f"⚠️ ERROR: Bones file missing: {file}")
                            if str(file) not in __class__.missing_files:
                                __class__.missing_files.append(str(file))
                            continue
                        if globals_and_threading.debug: print(f"Processing bones file: {file}")
                        __class__.import_file(file, root_obj.name)
                    if globals_and_threading.debug: print("DEBUG: Finished processing bones files")

                imported_empties = [
                    obj for obj in imported_objs
                    if obj.type == 'EMPTY'
                ]

                mapping = __class__.get_hardpoint_mapping_from_guid(guid_str) or {}
                if globals_and_threading.debug: print(f"DEBUG: Imported empties: {[e.name for e in imported_empties]}")
                if globals_and_threading.debug: print(f"DEBUG: Mapping for imported GUID {guid_str}: {mapping}")
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

                if globals_and_threading.debug: print(f"Imported object for '{item_port_name}' GUID {guid_str} → {geometry_path}")

                # Recurse into nested loadout with is_top_level=False and pass guid_str as parent_guid
                if nested_loadout:
                    entries_count = len(nested_loadout.properties.get('entries', []))
                    if globals_and_threading.debug: print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing into GUID {guid_str}...")
                    __class__.import_hardpoint_hierarchy(nested_loadout, imported_empties, is_top_level=False, parent_guid=guid_str)
                else:
                    if globals_and_threading.debug: print("DEBUG: No nested loadout found, recursion ends here")

        # Clear progress when done with this level
        if is_top_level:
            try:
                misc_utils.SCOrg_tools_misc.clear_progress()
                if globals_and_threading.debug: print("DEBUG: Cleared progress on top level completion")
            except Exception as e:
                print(f"ERROR: Failed to clear progress: {e}")

    def import_file(geometry_path, parent_empty_name):
        """
        Import a single file without recursion.
        """
        if globals_and_threading.debug: print(f"DEBUG: import_file called with geometry_path: {geometry_path}, parent_empty_name: {parent_empty_name}")
        if geometry_path is None:
            if globals_and_threading.debug: print(f"❌ ERROR: import_file called with no geometry_path")
            return

        if not geometry_path.exists():
            print(f"Error: .DAE file not found at: {geometry_path}")
            if globals_and_threading.debug: print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
            if str(geometry_path) not in __class__.missing_files:
                __class__.missing_files.append(str(geometry_path));
            return

        # Get a set of all objects before import
        before = set(bpy.data.objects)

        bpy.ops.object.select_all(action='DESELECT')
        result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
        if 'FINISHED' not in result:
            if globals_and_threading.debug: print(f"❌ ERROR: Failed to import DAE for: {geometry_path}")
            return
        
        # Get a set of all objects after import
        after = set(bpy.data.objects)

        # The difference is the set of newly imported objects
        imported_objs = list(after - before)

        # Find root objects (those without a parent)
        root_objs = [obj for obj in imported_objs if obj.parent is None]

        if not root_objs:
            if globals_and_threading.debug: print(f"WARNING: No root object found for: {geometry_path}")
            return
        if parent_empty_name:
            if globals_and_threading.debug: print(f"DEBUG: Parenting to: {parent_empty_name}, and setting name to {geometry_path.stem}")
            # Parent the root object to the provided parent_empty
            root_obj = root_objs[0]
            root_obj.name = geometry_path.stem  # Set the name to the file name (without extension)
            root_obj.parent = bpy.data.objects.get(parent_empty_name)
            root_obj.matrix_parent_inverse.identity()

    def run_import():
        
        os.system('cls')
        __class__.imported_guid_objects = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        __class__.missing_files = []
        
        misc_utils.SCOrg_tools_misc.select_base_collection() # Ensure the base collection is active before importing
        record = misc_utils.SCOrg_tools_misc.get_ship_record()
        
        # Check if record is None before trying to access its properties
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not get ship record. Please import a StarFab Blueprint first.")
            return

        # Safely access Components and loadout
        top_level_loadout = __class__.get_loadout_from_record(record)

        if top_level_loadout is None:
            blender_utils.SCOrg_tools_blender.fix_modifiers()
            misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            return

        empties_to_fill = __class__.get_all_empties_blueprint()

        if globals_and_threading.debug: print(f"Total hardpoints to import: {len(empties_to_fill)}")

        __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill)
        blender_utils.SCOrg_tools_blender.fix_modifiers()
        if len(__class__.missing_files) > 0:
            misc_utils.SCOrg_tools_misc.show_text_popup(
                text_content=__class__.missing_files,
                header_text="The following files were missing, please extract them with StarFab, under Data -> Data.p4k:"
            )

    def get_loadout_from_record(record):
        if globals_and_threading.debug: print(f"DEBUG: get_loadout_from_record called with record: {record.name}")
        try:
            if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
                if globals_and_threading.debug: print("DEBUG: Record has Components, checking for loadout...")
                for comp in record.properties.Components:
                    if hasattr(comp, 'name') and comp.name == "SEntityComponentDefaultLoadoutParams":
                        if hasattr(comp.properties, 'loadout'):
                            if globals_and_threading.debug: print("DEBUG: Found loadout")
                            return comp.properties.loadout
        except Exception as e:
            if globals_and_threading.debug: print(f"DEBUG: Error accessing Components in record {record.name}: {e}")
        if globals_and_threading.debug: print("DEBUG: Record has no loadout")
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
    
    def import_missing_materials(tint_number = 0):
        hasattr(__class__, 'extract_dir') or __class__.init()
        if not __class__.extract_dir:
            if globals_and_threading.debug: print("ERROR: extract_dir is not set. Please set it in the addon preferences.")
            return None

        p4k = globals_and_threading.p4k
        if not p4k:
            misc_utils.SCOrg_tools_misc.error("Please load Data.p4k first")
            return None

        # Search for all .mtl files at once to build a lookup dictionary
        if globals_and_threading.debug: print("DEBUG: Searching p4k for all .mtl files...")
        try:
            mtl_files = p4k.search(file_filters=".mtl", ignore_case=True, mode='endswith')
            if globals_and_threading.debug: print(f"DEBUG: Found {len(mtl_files)} .mtl files in p4k")
            
            # Build lookup dictionary: lowercase filename -> full_path
            mtl_lookup = {}
            for match in mtl_files:
                if hasattr(match, 'filename'):
                    full_path = match.filename
                else:
                    continue
                
                filename = Path(full_path).name.lower()
                clean_path = full_path.removeprefix("Data/")
                
                # Only add if not already in dictionary (preserve first occurrence)
                if filename not in mtl_lookup:
                    mtl_lookup[filename] = clean_path
            if globals_and_threading.debug: print(f"DEBUG: Built lookup for {len(mtl_lookup)} .mtl files")
        except Exception as e:
            if globals_and_threading.debug: print(f"DEBUG: Error searching for .mtl files: {e}")
            mtl_lookup = {}

        file_cache = {}
        missing_checked = []

        # Get a list of material names instead of material objects
        material_names = list(bpy.data.materials.keys())
        from pprint import pprint
        for i, mat_name in enumerate(material_names):
            misc_utils.SCOrg_tools_misc.update_progress("Importing missing materials", i, len(material_names), spinner_type="arc")
            
            # Get fresh reference to the material
            mat = bpy.data.materials.get(mat_name)
            if mat is None:
                continue
            
            # Check if the material name contains '_mtl_' and if it is a vanilla material (with only Principled BSDF)
            try:
                if "_mtl_" in mat.name and blender_utils.SCOrg_tools_blender.is_material_vanilla(mat):
                    # Get the filename by removing '_mtl' and adding '.mtl'
                    filename = __class__.get_material_filename(mat.name)
                    if not filename in file_cache and filename not in missing_checked:
                        # Use the pre-built mtl_lookup dictionary instead of individual p4k.search
                        filename_lower = filename.lower()
                        if globals_and_threading.debug: print(f"DEBUG: Looking for material file: {filename} (lookup key: {filename_lower})")
                        
                        if filename_lower in mtl_lookup:
                            clean_path = mtl_lookup[filename_lower]
                            if globals_and_threading.debug: print(f"DEBUG: Found in mtl_lookup: Data/{clean_path}")
                            filepath = __class__.extract_dir / clean_path
                            if filepath.exists():
                                file_cache[filename] = filepath
                                if globals_and_threading.debug: print(f"DEBUG: File exists on disk: {filepath}")
                                # Check for Material01 or Tintable_01 type materials and remap:
                                blender_utils.SCOrg_tools_blender.fix_unmapped_materials(str(filepath))
                            else:
                                if globals_and_threading.debug: print(f"DEBUG: File NOT found on disk: {filepath}")
                                if str(filepath) not in __class__.missing_files:
                                    __class__.missing_files.append(str(filepath))
                                missing_checked.append(filename)
                        else:
                            if globals_and_threading.debug: print(f"DEBUG: NOT found in mtl_lookup: {filename_lower}")
                            missing_checked.append(filename)
            except ReferenceError:
                # Material was removed during iteration, skip it
                if globals_and_threading.debug: print(f"DEBUG: Material {mat_name} was removed during processing, skipping")
                continue
            
        # Make sure the tint group is initialised, pass the item_name
        record = misc_utils.SCOrg_tools_misc.get_ship_record(skip_error=True)
        if not record and __class__.item_guid:
            record = __class__.get_record(__class__.item_guid)
        if record:
            item_name = record.name
        else:
            item_name = __class__.item_name
        tint_node_group = blender_utils.SCOrg_tools_blender.init_tint_group(item_name)
        # import the tint palette
        
        if not record and __class__.item_guid:
            record = __class__.get_record(__class__.item_guid)
            
        if record:
            if globals_and_threading.debug: print(f"DEBUG: Attempting to load tint palette for: {record.name}")
            tints = tint_utils.SCOrg_tools_tint.get_tint_pallet_list(record)
            if tints:
                __class__.load_tint_palette(tints[tint_number], tint_node_group.name)

        if len(file_cache) > 0:
            # Import the materials using scdatatools
            from scdatatools.blender import materials
            __class__.tint_palette_node_group_name = tint_node_group.name
            if globals_and_threading.debug: print("Importing materials from files")
            values = list(file_cache.values())
            if globals_and_threading.debug:
                print(f"DEBUG: Importing {len(values)} materials from files:")
                pprint(values)
            materials.load_materials(values, data_dir='', tint_palette_node_group = tint_node_group)
            
    def get_material_filename(material_name):
        before, sep, after = material_name.partition('_mtl')
        if sep:
            result = before + '.mtl'
        else:
            result = material_name  # _mtl not found, leave unchanged
        return result
    
    def load_tint_palette(palette_guid, tint_palette_node_group_name):
        if globals_and_threading.debug: print("Loading tint palette for GUID:", palette_guid)
        import scdatatools
        hasattr(__class__, 'extract_dir') or __class__.init()
        
        record = globals_and_threading.dcb.records_by_guid[palette_guid]
        if not record:
            if globals_and_threading.debug: print("Palette not found: ", palette_guid)
            return
        
        if record.type != "TintPaletteTree": 
            if globals_and_threading.debug: print(f"ERROR: record {palette_guid} is not a tint pallet")
            return
        
        t = bpy.data.node_groups[tint_palette_node_group_name]
        name_map = {
            "entryA": "Primary",
            "entryB": "Secondary",
            "entryC": "Tertiary",
        }

        for entry in ["entryA", "entryB", "entryC"]:
            e = record.properties['root'].properties[entry].properties['tintColor'].properties
            t.nodes["Outputs"].inputs[name_map[entry]].default_value = scdatatools.blender.materials.a_to_c(e)
            e = record.properties['root'].properties[entry].properties['specColor'].properties
            t.nodes["Outputs"].inputs[f"{name_map[entry]} SpecColor"].default_value = scdatatools.blender.materials.a_to_c(e)
            glossiness = float(record.properties['root'].properties[entry].properties['glossiness'])
            t.nodes["Outputs"].inputs[f"{name_map[entry]} Glossiness"].default_value = (glossiness / 255)

        e = record.properties['root'].properties['glassColor'].properties
        t.nodes["Outputs"].inputs["Glass Color"].default_value = scdatatools.blender.materials.a_to_c(e)

        if "DecalConverter" not in t.nodes:
            return  # Decals handling not loaded

        decal_texture = record.properties['root'].properties['decalTexture']
        # apply path to decal_texture
        decal_texture = __class__.extract_dir / decal_texture.removeprefix("Data/")
        # try different extensions
        found_texture = False
        if decal_texture:
            for ext in ['.png', '.tif', '.tga']:
                decal_texture = decal_texture.with_suffix(ext)
                if decal_texture.is_file():
                    found_texture = True
                    break
            
        if found_texture:
            try:
                # Load the image into Blender if not already loaded
                img_path = str(decal_texture)
                image = bpy.data.images.get(decal_texture.name)
                if image is None:
                    image = bpy.data.images.load(img_path)
                t.nodes["Decal"].image = image
                t.nodes["Decal"].image.colorspace_settings.name = "Non-Color"
            except Exception as e:
                if globals_and_threading.debug: print(f"Unable to load decal {decal_texture.name}: {e}")
        else:
            # No decal texture found, set to transparent
            t.nodes["Decal"].image = blender_utils.SCOrg_tools_blender.create_transparent_image()

        for decalColour in ["decalColorR", "decalColorG", "decalColorB"]:
            d = record.properties['root'].properties[decalColour].properties
            t.nodes["DecalConverter"].inputs[decalColour].default_value = scdatatools.blender.materials.a_to_c(d)