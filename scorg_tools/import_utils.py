import bpy
from pathlib import Path
import os
import re

# Import globals
from . import globals_and_threading
from . import misc_utils # For SCOrg_tools_misc.error, get_ship_record, select_base_collection
from . import blender_utils # For SCOrg_tools_blender.fix_modifiers

class SCOrg_tools_import():
    item_name = None
    def init():
        print("SCOrg_tools_import initialized")
        __class__.prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        __class__.extract_dir = Path(__class__.prefs.extract_dir) # Ensure Path object
        __class__.missing_files = []  # List to track missing files
        __class__.item_name = None

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
                return record
            else:
                misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
                return None
        else:
            # Otherwise, try to get by name
            for record in dcb.records:
                if hasattr(record, 'name') and record.name.lower() == id.lower():
                    if not __class__.item_name:
                        __class__.item_name = record.name
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
        __class__.skip_imported_files = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        __class__.missing_files = []
                
        #Load item by GUID
        record = __class__.get_record(guid)

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return False
        
        geometry_path = __class__.get_geometry_path_by_guid(guid)
        process_bones_file = False
        # if the geometry path is an array, it means we have a CDF XML file that points to the real geometry
        if isinstance(geometry_path, list):
            print(f"DEBUG: CDF XML file found with references to: {geometry_path}")
            process_bones_file = geometry_path
            geometry_path = process_bones_file.pop(0)  # Get the first file in the array, which is the base armature DAE file (or sometimes the base geometry)

        # load the main .dae
        if geometry_path:
            print(f"Loading geo: {geometry_path}")
            if not geometry_path.is_file():
                misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
                print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                if str(geometry_path) not in __class__.missing_files:
                    __class__.missing_files.append(str(geometry_path))
                print(f"⚠️ ERROR: Failed to import DAE for {guid}: {geometry_path} - file missing")
                print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k:")
                print(__class__.missing_files)
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
            print(f"DEBUG: post-import root object: {root_object_name}")

            top_level_loadout = __class__.get_loadout_from_record(record)
            displacement_strength = 0.005
            if process_bones_file:
                print("Deleting meshes for initial CDF base import")
                # Usually used for smaller items like weapons, so change the POM/Decal displacement strength to 0.5mm
                displacement_strength = 0.0005
                # Delete all meshes to avoid conflicts with CDF imports, the imported .dae objects will be selected
                __class__.replace_selected_mesh_with_empties()
                
                print(f"Converting bones to empties for {guid}: {geometry_path}")
                blender_utils.SCOrg_tools_blender.convert_armatures_to_empties()
                
                if not root_object_name:
                    print(f"WARNING: No root object found for: {geometry_path}")
                
                for file in process_bones_file:
                    if not file.is_file():
                        print(f"⚠️ ERROR: Bones file missing: {file}")
                        if str(file) not in __class__.missing_files:
                            __class__.missing_files.append(str(file))
                        continue
                    print(f"Processing bones file: {file}")
                    __class__.import_file(file, root_object_name)
                print("DEBUG: Finished processing bones files")

            if top_level_loadout is None:
                misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            else:
                empties_to_fill = __class__.get_all_empties_blueprint()
                print(empties_to_fill)
                print(f"Total hardpoints to import: {len(empties_to_fill)}")

                # Pretend that it's not the top level, so we can import the hierarchy without needing the orig_name custom property on the empties
                __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill, is_top_level=False, parent_guid=guid)

            # add modifiers
            blender_utils.SCOrg_tools_blender.fix_modifiers(displacement_strength);
            if len(__class__.missing_files) > 0:
                print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k:")
                print(__class__.missing_files)
    
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
                                            print(f"Found CDF XML: {file_path}")
                                            # Read the CDF XML file to find the DAE path
                                            from scdatatools.engine import cryxml
                                            tree = cryxml.etree_from_cryxml_file(file_path)
                                            root = tree.getroot()
                                            geo_path = None
                                            for attachment_list in root.findall("AttachmentList"):
                                                for attachment in attachment_list.findall("Attachment"):
                                                    binding = attachment.attrib.get("Binding")
                                                    geo_path = (__class__.extract_dir / Path(binding)).with_suffix('.dae')
                                                    print(f"Found geometry path in CDF XML: {geo_path}")
                                                    file_array.append(geo_path)
                                            print(f"Returning geometry file array: {file_array}")
                                            return file_array
                                        else:
                                            print(f"⚠️ CDF XML file not found: {file_path}. Please extract it with StarFab, under Data -> Data.p4k")
                                            return None
                                    dae_path = file_path.with_suffix('.dae')
                                    print(f'Found geometry: {dae_path}')
                                    return (__class__.extract_dir / dae_path)
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
                    if str(geometry_path) not in __class__.missing_files:
                        __class__.missing_files.append(str(geometry_path));
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
        if len(__class__.missing_files) > 0:
            print("The following files were missing, please extract them with StarFab, under Data -> Data.p4k if you want a more complete loadout:")
            print(__class__.missing_files)

    def import_file(geometry_path, parent_empty_name):
        """
        Import a single file without recursion.
        """
        print(f"DEBUG: import_file called with geometry_path: {geometry_path}, parent_empty_name: {parent_empty_name}")
        if geometry_path is None:
            print(f"❌ ERROR: import_file called with no geometry_path")
            return

        if not geometry_path.exists():
            misc_utils.SCOrg_tools_misc.error(f"Error: .DAE file not found at: {geometry_path}")
            print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
            if str(geometry_path) not in __class__.missing_files:
                __class__.missing_files.append(str(geometry_path));
            return

        # Get a set of all objects before import
        before = set(bpy.data.objects)

        bpy.ops.object.select_all(action='DESELECT')
        result = bpy.ops.wm.collada_import(filepath=str(geometry_path))
        if 'FINISHED' not in result:
            print(f"❌ ERROR: Failed to import DAE for {guid_str}: {geometry_path}")
            return
        
        # Get a set of all objects after import
        after = set(bpy.data.objects)

        # The difference is the set of newly imported objects
        imported_objs = list(after - before)

        # Find root objects (those without a parent)
        root_objs = [obj for obj in imported_objs if obj.parent is None]

        if not root_objs:
            print(f"WARNING: No root object found for: {geometry_path}")
            return
        if parent_empty_name:
            print(f"DEBUG: Parenting to: {parent_empty_name}, and setting name to {geometry_path.stem}")
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
            misc_utils.SCOrg_tools_misc.error("Could not get ship record. Please ensure a 'base' empty object exists and Data.p4k is loaded correctly.")
            return

        # Safely access Components and loadout
        top_level_loadout = __class__.get_loadout_from_record(record)

        if top_level_loadout is None:
            blender_utils.SCOrg_tools_blender.fix_modifiers()
            misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            return

        empties_to_fill = __class__.get_all_empties_blueprint()

        print(f"Total hardpoints to import: {len(empties_to_fill)}")

        __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill)
        blender_utils.SCOrg_tools_blender.fix_modifiers()

    def get_loadout_from_record(record):
        print(f"DEBUG: get_loadout_from_record called with record: {record.name}")
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
    
    def import_missing_materials(path = None, ship_name = None):
        hasattr(__class__, 'extract_dir') or __class__.init()
        if not __class__.extract_dir:
            print("ERROR: extract_dir is not set. Please set it in the addon preferences.")
            return None

        p4k = globals_and_threading.p4k
        file_cache = {}
        missing_checked = []
        if not p4k:
            misc_utils.SCOrg_tools_misc.error("Please load Data.p4k first")
            return None

        # Loop through all materials in the scene
        for mat in bpy.data.materials:
            # Check if the material name contains '_mtl_' and if it is a vanilla material (with only Principled BSDF)
            if "_mtl_" in mat.name and blender_utils.SCOrg_tools_blender.is_material_vanilla(mat):
                # Get the filename by removing '_mtl' and adding '.mtl'
                file_found = False
                filename = __class__.get_material_filename(mat.name)
                if not filename in file_cache and filename not in missing_checked:
                    # if a path is provided, check it fist
                    if path:
                        filepath = Path(path) / filename
                        if filepath.exists():
                            file_found = True

                    if not file_found:
                        # If not found in the provided path, search in the p4k for the file
                        print("searching p4k for material file:", filename)
                        matches = p4k.search(file_filters=[filename], ignore_case = True, mode='endswith')
                        if matches:
                            print("Found material file in p4k:", matches[0].filename.removeprefix("Data/"))
                            filepath = __class__.extract_dir / matches[0].filename.removeprefix("Data/")
                            if filepath.exists():
                                file_found = True
                                file_cache[filename] = filepath
                                print(f"DEBUG: Extracted Material file found: {filepath}")
                            else:
                                print(f"⚠️ ERROR: Extracted material file expected: {filepath} not found, please extract it with StarFab, under Data -> Data.p4k")
                                if str(filepath) not in __class__.missing_files:
                                    __class__.missing_files.append(str(filepath))
                                missing_checked.append(filename)
        print(f"DEBUG: Material file search completed, found {len(file_cache)} files")
        print(file_cache)
        if len(file_cache) > 0:
            # Import the materials using scdatatools
            from scdatatools.blender import materials
            # Make sure the tint group is initialised, pass the item_name
            tint_node_group = blender_utils.SCOrg_tools_blender.init_tint_group(__class__.item_name)
            print("Importing materials from files")

            materials.load_materials(list(file_cache.values()), data_dir='', tint_palette_node_group = tint_node_group)

    def get_material_filename(material_name):
        before, sep, after = material_name.partition('_mtl')
        if sep:
            result = before + '.mtl'
        else:
            result = material_name  # _mtl not found, leave unchanged
        return result