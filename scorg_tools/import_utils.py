from ast import main
import glob
import bpy
from pathlib import Path
import os
import typing
import re
# Import globals
from . import globals_and_threading
from . import misc_utils # For SCOrg_tools_misc.error, get_ship_record, select_base_collection
from . import blender_utils # For SCOrg_tools_blender.fix_modifiers
from . import tint_utils # For SCOrg_tools_tint.get_tint_pallets

class SCOrg_tools_import():
    item_name = None
    item_guid = None
    translation_new_data_preference = None
    prefs = None
    extract_dir = None
    missing_files = None
    item_name = None
    item_guid = None
    tint_palette_node_group_name = None
    default_tint_guid = None
    imported_guid_objects = {}
    skip_imported_files = {}
    INCLUDE_HARDPOINTS = [] # all
    _cached_mtl_files = None  # Cache for p4k.search results

    @staticmethod
    def init():
        """ Initialize the import class. """
        if globals_and_threading.debug: print("SCOrg_tools_import initialized")
        __class__.prefs = bpy.context.preferences.addons["scorg_tools"].preferences
        extract_dir = getattr(__class__.prefs, 'extract_dir', None)
        __class__.extract_dir = Path(extract_dir) if extract_dir else None
        __class__.missing_files = []  # List to track missing files
        __class__.item_name = None
        __class__.item_guid = None
        __class__.tint_palette_node_group_name = None
        __class__.default_tint_guid = None
        __class__._cached_mtl_files = None  # Clear cache on init

    @staticmethod
    def clear_mtl_cache():
        """Clear the cached MTL files search results."""
        __class__._cached_mtl_files = None
        if globals_and_threading.debug: print("DEBUG: Cleared MTL files cache")

    @staticmethod
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

    @staticmethod
    def get_guid_by_name(name):
        record = __class__.get_record(name)
        if record:
            return str(record.id)
        else:
            return None

    @staticmethod
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

    @staticmethod
    def import_by_id(id):
        os.system('cls')
        print("=" * 80)
        print("NEW CODE IS RUNNING - import_by_id() was updated!")
        print("=" * 80)
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
        # DON'T clear missing_files here - it's cleared in run_import() at the top level
        # Clearing here wipes out DAE files collected during recursive hardpoint imports
        __class__.set_translation_new_data_preference()
                
        #Load item by GUID
        record = __class__.get_record(guid)

        globals_and_threading.imported_record = record

        if not record:
            misc_utils.SCOrg_tools_misc.error(f"⚠️ Could not find record for GUID: {guid} - are you using the correct Data.p4k?")
            return False
        
        __class__.item_name = record.name
        __class__.item_guid = guid
        tint_utils.SCOrg_tools_tint.update_tints(record)  # Update tints for the item
        
        geometry_path = __class__.get_geometry_path(guid = guid)
        process_bones_file = False
        # if the geometry path is an array, it means we have a CDF XML file that points to the real geometry
        if isinstance(geometry_path, list):
            if globals_and_threading.debug: print(f"DEBUG: CDF XML file found with references to: {geometry_path}")
            process_bones_file = geometry_path
            geometry_path = process_bones_file.pop(0)  # Get the first file in the array, which is the base armature DAE file (or sometimes the base geometry)

        # load the main .dae
        if geometry_path:
            if globals_and_threading.debug: print(f"Loading geo: {geometry_path}")
            if not geometry_path.exists():
                print(f"Error: .DAE file not found at: {geometry_path}")
                if globals_and_threading.debug:
                    print(f"DEBUG: Attempted DAE import path: {geometry_path}, but file was missing")
                
                # Normalize path and add to missing_files list
                missing_path = str(geometry_path).replace('\\', '/')
                if not missing_path.lower().startswith('data/'):
                    # Ensure it starts with Data/
                    missing_path = 'Data/' + missing_path.split('Data/', 1)[-1] if 'Data/' in missing_path else 'Data/' + missing_path
                
                if missing_path not in __class__.missing_files and not missing_path.startswith('$') and 'ddna.glossmap' not in missing_path.lower():
                    __class__.missing_files.append(missing_path)
                    if globals_and_threading.debug:
                        print(f"Added to missing_files (dae): {missing_path}")

                # Check if we should auto-extract
                prefs = bpy.context.preferences.addons["scorg_tools"].preferences
                if prefs.extract_missing_files:
                    print(f"Attempting to auto-extract missing base file: {missing_path}")
                    success, fail, report = __class__.extract_missing_files(missing_path, prefs)
                    if success > 0 and geometry_path.exists():
                        print(f"Successfully extracted {geometry_path.name}. Retrying import...")
                        # Remove from missing files since we fixed it
                        if missing_path in __class__.missing_files:
                            __class__.missing_files.remove(missing_path)
                    else:
                        print(f"Failed to auto-extract {geometry_path.name}")
                        return None
                else:
                    print(f"⚠️ ERROR: Failed to import DAE for {guid}: {geometry_path} - file missing")
                    # Show popup for missing base file if we didn't try to extract
                    if len(__class__.missing_files) > 0:
                        sorted_missing_files = sorted(__class__.missing_files, key=str.lower)
                        misc_utils.SCOrg_tools_misc.show_text_popup(
                            text_content=sorted_missing_files,
                            header_text="The following files were missing, please extract them with StarFab, under Data -> Data.p4k:",
                            is_extraction_popup=True
                        )
                    return None
            
            # Get a set of all objects before import
            before = set(bpy.data.objects)

            bpy.ops.object.select_all(action='DESELECT')
            result = __class__.import_dae(geometry_path)
            if result != True:
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
                displacement_strength = bpy.context.preferences.addons["scorg_tools"].preferences.decal_displacement_non_ship
                # Delete all meshes to avoid conflicts with CDF imports, the imported .dae objects will be selected
                __class__.replace_selected_mesh_with_empties()
                
                if globals_and_threading.debug: print(f"Converting bones to empties for {guid}: {geometry_path}")
                # Ensure we're in object mode before converting armatures
                if bpy.context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                blender_utils.SCOrg_tools_blender.convert_armatures_to_empties()
                
                if not root_object_name:
                    if globals_and_threading.debug: print(f"WARNING: No root object found for: {geometry_path}")
                
                for file in process_bones_file:
                    if not file.is_file():
                        if globals_and_threading.debug: print(f"⚠️ ERROR: Bones file missing: {file}")
                        if str(file) not in __class__.missing_files:
                            try:
                                rel_path = str(file.relative_to(__class__.extract_dir)).replace("\\", "/")
                            except ValueError:
                                rel_path = str(file).replace("\\", "/")
                            if rel_path not in __class__.missing_files and not rel_path.startswith('$') and 'ddna.glossmap' not in rel_path.lower():
                                if not rel_path.lower().startswith("data/"):
                                    rel_path = "Data/" + rel_path
                                __class__.missing_files.append(rel_path)
                        continue
                    if globals_and_threading.debug: print(f"Processing bones file: {file}")
                    __class__.import_file(file, root_object_name)
                if globals_and_threading.debug: print("DEBUG: Finished processing bones files")

            else:
                # This is likely a ship, use ship displacement strength
                displacement_strength = bpy.context.preferences.addons["scorg_tools"].preferences.decal_displacement_ship

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
            
            # Show missing files popup if there are any left (e.g. from hardpoints)
            if len(__class__.missing_files) > 0:
                print(f"Total missing files: {len(__class__.missing_files)}")
                sorted_missing_files = sorted(__class__.missing_files, key=str.lower)
                misc_utils.SCOrg_tools_misc.show_text_popup(
                    text_content=sorted_missing_files,
                    header_text="The following files were missing, please extract them with StarFab, under Data -> Data.p4k:",
                    is_extraction_popup=True
                )
            
            __class__.set_translation_new_data_preference(reset=True)
    
    @staticmethod
    def get_base_empty():
        """
        Get the base empty object that serves as the root for the ship.
        This is usually the first empty in the scene that has children.
        """
        base_empty = None
        for obj in bpy.data.objects:
            if obj.type == 'EMPTY' and 'container_name' in obj and obj['container_name'] == 'base':
                base_empty = obj
                break
        return base_empty

    @staticmethod
    def get_all_empties_blueprint():
        # First find the base container empty
        base_empty = __class__.get_base_empty()
        
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
            print(f"DEBUG: Found {len(filled_hardpoint_names)} hardpoint types already filled")
        
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
    
    @staticmethod
    def get_geometry_path(guid = None, record = None, original_path = False):
        if __class__.extract_dir is None:
            __class__.init()
        if not guid and not record:
            misc_utils.SCOrg_tools_misc.error("⚠️ GUID or record must be provided to get geometry path")
            return None

        # if there's no record, try to get it by guid
        if record is None:
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
                                    if original_path:
                                        return path  # Return the original path without modification
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

    @staticmethod
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

    @staticmethod
    def duplicate_hierarchy_linked(original_obj, parent_empty):
        new_obj = original_obj.copy()
        new_obj.data = original_obj.data  # share mesh data (linked duplicate)
        new_obj.animation_data_clear()
        bpy.context.collection.objects.link(new_obj)

        new_obj.parent = parent_empty
        new_obj.matrix_parent_inverse.identity()

        for child in original_obj.children:
            __class__.duplicate_hierarchy_linked(child, new_obj)
    
    @staticmethod
    def import_hardpoint_hierarchy(loadout, empties_to_fill, is_top_level=True, parent_guid=None):        
        # Check if loadout is None to prevent AttributeError
        if loadout is None:
            if globals_and_threading.debug: print("DEBUG: Loadout is None, skipping hierarchy import")
            return
            
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
            if globals_and_threading.debug: print(f"DEBUG: Entry {i}: item_port_name='{item_port_name}', guid={guid}, entityClassName={entity_class_name}, has_nested_loadout={nested_loadout is not None}")

            if not item_port_name or (not guid and not entity_class_name):
                if globals_and_threading.debug: print("DEBUG: Missing item_port_name or guid and name, skipping")
                continue

            # Apply filter ONLY at top level
            if is_top_level and __class__.INCLUDE_HARDPOINTS and item_port_name not in __class__.INCLUDE_HARDPOINTS:
                if globals_and_threading.debug: print(f"DEBUG: Skipping '{item_port_name}' due to top-level filter")
                continue

            mapped_name = item_port_name
            for hardpoint_name, item_port_names in hardpoint_mapping.items():
                if globals_and_threading.debug: print(f"DEBUG: Checking hardpoint mapping: {hardpoint_name} -> {item_port_names}")
                if item_port_name in item_port_names:
                    mapped_name = hardpoint_name
                    break
            if globals_and_threading.debug: print(f"DEBUG: Looking for matching empty for item_port_name='{item_port_name}', mapped_name='{mapped_name}'")
            
            # Try to find matching empty in empties_to_fill (empty hardpoints)
            matching_empty = None
            for empty in empties_to_fill:
                orig_name = empty.get('orig_name', '') if hasattr(empty, 'get') else ''
                
                if __class__.matches_blender_name(orig_name, mapped_name) or __class__.matches_blender_name(empty.name, mapped_name):
                    matching_empty = empty
                    break
            
            # If no empty hardpoint found, check if there's a filled hardpoint that we should process for nested loadout
            filled_hardpoint = None
            if not matching_empty:
                # Search all empties (not just empty ones) for a match to handle filled hardpoints with nested loadouts
                for obj in bpy.data.objects:
                    if obj.type == 'EMPTY':
                        orig_name = obj.get('orig_name', '') if hasattr(obj, 'get') else ''
                        if __class__.matches_blender_name(orig_name, mapped_name) or __class__.matches_blender_name(obj.name, mapped_name):
                            # Check if this hardpoint has children (is filled)
                            if len(obj.children) > 0:
                                filled_hardpoint = obj
                                if globals_and_threading.debug: print(f"DEBUG: Found filled hardpoint: {filled_hardpoint.name} for '{mapped_name}'")
                                break
            
            # Determine if we should process nested loadout and whether to import geometry
            should_import_geometry = matching_empty is not None
            should_process_nested = nested_loadout is not None or filled_hardpoint is not None
            target_empty = matching_empty or filled_hardpoint
            
            if not target_empty:
                if globals_and_threading.debug: print(f"WARNING: No matching empty or filled hardpoint found for '{mapped_name}' (original item_port_name: '{item_port_name}'), skipping this entry")
                continue

            if globals_and_threading.debug: 
                status = "empty" if should_import_geometry else "filled"
                print(f"DEBUG: Found {status} hardpoint: {target_empty.name} for '{mapped_name}', will_import_geometry={should_import_geometry}, will_process_nested={should_process_nested}")

            # Handle GUID resolution
            guid_str = str(guid)
            if not __class__.is_guid(guid_str): # must be 00000000-0000-0000-0000-000000000000 or blank
                if not entity_class_name:
                    if globals_and_threading.debug: print("DEBUG: GUID is all zeros, but no entityClassName found, skipping geometry import")
                    # Still recurse into nested loadout if present
                    if should_process_nested and nested_loadout:
                        entries_count = len(nested_loadout.properties.get('entries', [])) if nested_loadout else 0
                        if globals_and_threading.debug: print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing into GUID {guid_str} (all zeros)...")
                        # For filled hardpoints, we need to get empties from within that hardpoint
                        if filled_hardpoint:
                            nested_empties = []
                            def collect_empties(obj):
                                if obj.type == 'EMPTY' and len(obj.children) == 0:
                                    nested_empties.append(obj)
                                for child in obj.children:
                                    collect_empties(child)
                            collect_empties(filled_hardpoint)
                            __class__.import_hardpoint_hierarchy(nested_loadout, nested_empties, is_top_level=False, parent_guid=guid_str)
                        else:
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
                    should_process_nested = nested_loadout is not None
                    if not nested_loadout:
                       if globals_and_threading.debug: print(f"DEBUG: Could not find a nested loadout for GUID {guid_str}: {nested_loadout}")
                    else:
                        if globals_and_threading.debug: print(f"DEBUG: Found nested loadout for GUID {guid_str}")

            # Only import geometry if we have an empty hardpoint
            if should_import_geometry:
                # Check if this specific hardpoint already has children (is already filled)
                if len(matching_empty.children) > 0:
                    if globals_and_threading.debug: print(f"DEBUG: Hardpoint '{matching_empty.name}' already has children, skipping geometry import to avoid duplication")
                    # Still allow nested loadout processing to continue - don't skip the entire section
                elif guid_str in __class__.imported_guid_objects:
                    # If the GUID is already imported, duplicate the hierarchy linked
                    original_root = __class__.imported_guid_objects[guid_str]
                    __class__.duplicate_hierarchy_linked(original_root, matching_empty)
                    if globals_and_threading.debug: print(f"Duplicated hierarchy for '{item_port_name}' from GUID {guid_str}")
                else:
                    # The item was not imported yet, so we need to import it
                    geometry_path = __class__.get_geometry_path(guid = guid_str)
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
                            try:
                                rel_path = str(geometry_path.relative_to(__class__.extract_dir)).replace("\\", "/")
                            except ValueError:
                                rel_path = str(geometry_path).replace("\\", "/")
                            if rel_path not in __class__.missing_files and not rel_path.startswith('$') and 'ddna.glossmap' not in rel_path.lower():
                                if not rel_path.lower().startswith("data/"):
                                    rel_path = "Data/" + rel_path
                                __class__.missing_files.append(rel_path);
                                print(f"Added to missing_files (loc 2): {rel_path}")
                        continue

                    # Get a set of all objects before import
                    before = set(bpy.data.objects)

                    bpy.ops.object.select_all(action='DESELECT')
                    result = __class__.import_dae(geometry_path)
                    if result != True:
                        if globals_and_threading.debug: print(f"ERROR: Failed to import DAE for {guid_str}: {geometry_path}")
                        continue

                    # Get a set of all objects after import
                    after = set(bpy.data.objects)
                    # The difference is the set of newly imported objects
                    imported_objs = list(after - before)

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
                        # Store the root object name before deletion
                        root_obj_name = root_obj.name
                        # Delete all meshes to avoid conflicts with CDF imports, the imported .dae objects will be selected
                        __class__.replace_selected_mesh_with_empties()
                        
                        if globals_and_threading.debug: print(f"Converting bones to empties for {guid_str}: {geometry_path}")
                        # Ensure we're in object mode before converting armatures
                        if bpy.context.mode != 'OBJECT':
                            bpy.ops.object.mode_set(mode='OBJECT')
                        blender_utils.SCOrg_tools_blender.convert_armatures_to_empties()
                        
                        for file in process_bones_file:
                            if not file.is_file():
                                if globals_and_threading.debug: print(f"⚠️ ERROR: Bones file missing: {file}")
                                if str(file) not in __class__.missing_files:
                                    try:
                                        rel_path = str(file.relative_to(__class__.extract_dir))
                                    except ValueError:
                                        rel_path = str(file)
                                    if rel_path not in __class__.missing_files and not rel_path.startswith('$') and 'ddna.glossmap' not in rel_path.lower():
                                        if not rel_path.lower().startswith("data/"):
                                            rel_path = "Data/" + rel_path
                                        __class__.missing_files.append(rel_path)
                                continue
                            if globals_and_threading.debug: print(f"Processing bones file: {file}")
                            __class__.import_file(file, root_obj_name)
                        if globals_and_threading.debug: print("DEBUG: Finished processing bones files")

                    if globals_and_threading.debug: print(f"Imported object for '{item_port_name}' GUID {guid_str} → {geometry_path}")

            # Process nested loadout regardless of whether we imported geometry
            if should_process_nested and nested_loadout:
                entries_count = len(nested_loadout.properties.get('entries', []))
                if globals_and_threading.debug: print(f"DEBUG: Processing nested loadout with {entries_count} entries for GUID {guid_str}...")
                
                # Get empties from the target hardpoint (whether newly imported or existing)
                nested_empties = []
                def collect_empties(obj):
                    if obj.type == 'EMPTY':
                        nested_empties.append(obj)
                    for child in obj.children:
                        collect_empties(child)
                
                collect_empties(target_empty)

                mapping = __class__.get_hardpoint_mapping_from_guid(guid_str) or {}
                if globals_and_threading.debug: print(f"DEBUG: Found empties in target hardpoint: {[e.name for e in nested_empties]}")
                if globals_and_threading.debug: print(f"DEBUG: Mapping for GUID {guid_str}: {mapping}")
                
                for empty in nested_empties:
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

                __class__.import_hardpoint_hierarchy(nested_loadout, nested_empties, is_top_level=False, parent_guid=guid_str)
            else:
                if globals_and_threading.debug: print("DEBUG: No nested loadout to process")

        # Clear progress when done with this level
        if is_top_level:
            try:
                misc_utils.SCOrg_tools_misc.clear_progress()
                if globals_and_threading.debug: print("DEBUG: Cleared progress on top level completion")
            except Exception as e:
                print(f"ERROR: Failed to clear progress: {e}")

    @staticmethod
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
            try:
                rel_path = str(geometry_path.relative_to(__class__.extract_dir)).replace("\\", "/")
            except ValueError:
                rel_path = str(geometry_path).replace("\\", "/")
            if rel_path not in __class__.missing_files and not rel_path.startswith('$') and 'ddna.glossmap' not in rel_path.lower():
                if not rel_path.lower().startswith("data/"):
                    rel_path = "Data/" + rel_path
                __class__.missing_files.append(rel_path)
                print(f"Added to missing_files (loc 3): {rel_path}")
            return

        # Get a set of all objects before import
        before = set(bpy.data.objects)

        bpy.ops.object.select_all(action='DESELECT')
        result = __class__.import_dae(geometry_path)
        if result != True:
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

    @staticmethod
    def run_import():
        os.system('cls')
        __class__.imported_guid_objects = {}
        __class__.INCLUDE_HARDPOINTS = [] # all
        __class__.missing_files = []
        __class__.set_translation_new_data_preference()

        misc_utils.SCOrg_tools_misc.select_base_collection() # Ensure the base collection is active before importing
        record = misc_utils.SCOrg_tools_misc.get_ship_record()
        
        globals_and_threading.imported_record = record

        # Check if record is None before trying to access its properties
        if record is None:
            misc_utils.SCOrg_tools_misc.error("Could not get ship record. Please import a StarFab Blueprint first.")
            return

        # Use ship displacement preference for fix_modifiers later
        displacement_strength = bpy.context.preferences.addons["scorg_tools"].preferences.decal_displacement_ship

        # Safely access Components and loadout
        top_level_loadout = __class__.get_loadout_from_record(record)

        if top_level_loadout is None:
            blender_utils.SCOrg_tools_blender.fix_modifiers(displacement_strength)
            misc_utils.SCOrg_tools_misc.error("Could not find top-level loadout in ship record. Check the structure of the record.")
            return

        empties_to_fill = __class__.get_all_empties_blueprint()

        if globals_and_threading.debug: print(f"Total hardpoints to import: {len(empties_to_fill)}")

        __class__.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill)
        
        blender_utils.SCOrg_tools_blender.fix_modifiers(displacement_strength)
        
        print(f"Total missing files: {len(__class__.missing_files)}")
        if len(__class__.missing_files) > 0:
            sorted_missing_files = sorted(__class__.missing_files, key=str.lower)
            misc_utils.SCOrg_tools_misc.show_text_popup(
                text_content=sorted_missing_files,
                header_text="The following files were missing, please extract them with StarFab, under Data -> Data.p4k:",
                is_extraction_popup=True
            )
        __class__.set_translation_new_data_preference(reset=True)

    @staticmethod
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
    
    @staticmethod
    def matches_blender_name(name, target):
        #print(f"DEBUG: matches_blender_name called with name='{name}', target='{target}'")
        return name == target or re.match(rf"^{re.escape(target)}\.\d+$", name)

    @staticmethod
    def is_guid(s):
        """
        Returns True if s is a valid GUID and non-zero string.
        """
        if s == "00000000-0000-0000-0000-000000000000":
            return False
        return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", str(s)))
    
    @staticmethod
    def extract_missing_textures_from_output(captured_stdout, captured_stderr):
        """
        Extract missing texture paths from captured console output.
        Returns a list of full paths to missing texture files.
        """
        import re
        from pathlib import Path
        
        # Combine captured output
        captured_output = captured_stdout + captured_stderr
        
        # Updated regex pattern to match the actual scdatatools warning format
        missing_texture_pattern = r'missing texture for mat ([^:]+): (.+?)(?:\n|$)'
        missing_textures = re.findall(missing_texture_pattern, captured_output)
                
        # Convert to full paths and add to missing files
        missing_texture_paths = []
        if missing_textures:
            for material_name, texture_path in missing_textures:
                tex_path = Path(texture_path)
                try:
                    rel_tex = str(tex_path.relative_to(__class__.extract_dir)).replace("\\", "/")
                except ValueError:
                    rel_tex = str(tex_path).replace("\\", "/")
                if Path(rel_tex).is_absolute():
                    extract_str = str(__class__.extract_dir)
                    if rel_tex.startswith(extract_str):
                        rel_tex = rel_tex[len(extract_str):].lstrip('/').lstrip('\\')
                        if not rel_tex.lower().startswith("data/"):
                            rel_tex = "Data/" + rel_tex
                missing_texture_paths.append(rel_tex)
            
            # Make unique list and add to missing_files
            unique_missing = list(set(missing_texture_paths))
            for missing_path in unique_missing:
                # Skip ddna.glossmap files
                if 'ddna.glossmap' in missing_path.lower():
                    continue
                if missing_path not in __class__.missing_files and not missing_path.startswith('$'):
                    __class__.missing_files.append(missing_path)
            
            if globals_and_threading.debug:
                print(f"DEBUG: Found {len(unique_missing)} unique missing texture paths")
        
        return missing_texture_paths

    @staticmethod
    def import_missing_materials(tint_number = 0):
        if __class__.extract_dir is None:
            # Only initialize extract_dir, don't call init() which would clear missing_files!
            prefs = bpy.context.preferences.addons["scorg_tools"].preferences
            extract_dir = getattr(prefs, 'extract_dir', None)
            __class__.extract_dir = Path(extract_dir) if extract_dir else None
        if not __class__.extract_dir:
            if globals_and_threading.debug: print("ERROR: extract_dir is not set. Please set it in the addon preferences.")
            return None

        p4k = globals_and_threading.p4k
        if not p4k:
            misc_utils.SCOrg_tools_misc.error("Please load Data.p4k first")
            return None

        # Search for all .mtl files at once to build a lookup dictionary
        if globals_and_threading.debug: print("DEBUG: Building MTL lookup dictionary...")
        try:
            mtl_lookup = __class__.build_mtl_lookup()
        except Exception as e:
            if globals_and_threading.debug: print(f"DEBUG: Error building MTL lookup: {e}")
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
                            paths_to_check = mtl_lookup[filename_lower]
                            
                            # If it's a string, there's only one file with this name, so use it directly
                            if isinstance(paths_to_check, str):
                                clean_path = paths_to_check
                                if globals_and_threading.debug: print(f"DEBUG: Single file found: Data/{clean_path}")
                                filepath = __class__.extract_dir / clean_path
                                if filepath.exists():
                                    file_cache[filename] = filepath
                                    if globals_and_threading.debug: print(f"DEBUG: File exists on disk: {filepath}")
                                    # Check for Material01 or Tintable_01 type materials and remap:
                                    blender_utils.SCOrg_tools_blender.fix_unmapped_materials(str(filepath))
                                else:
                                    if globals_and_threading.debug: print(f"DEBUG: File NOT found on disk: {filepath}")
                                    if str(filepath) not in __class__.missing_files and not str(filepath).startswith('$') and 'ddna.glossmap' not in str(filepath).lower():
                                        __class__.missing_files.append(str(filepath))
                                    missing_checked.append(filename)
                            else:
                                # Multiple files with same name, need to search for the correct material
                                # Extract the material name from the Blender material name
                                # Remove everything before and including "_mtl_"
                                material_name_in_xml = mat.name.split("_mtl_", 1)[1]

                                if globals_and_threading.debug: print(f"DEBUG: Found multiple files with the same name for {mat.name}, looking for material '{material_name_in_xml}' in {len(paths_to_check)} file(s)")
                                
                                found_filepath = None
                                for clean_path in paths_to_check:
                                    if globals_and_threading.debug: print(f"DEBUG: Checking file: Data/{clean_path}")
                                    filepath = __class__.extract_dir / clean_path
                                    if filepath.exists():
                                        # Use get_material_names_from_file to get all materials in this file
                                        try:
                                            # Get the filename from the clean_path
                                            file_name = Path(clean_path).name
                                            material_names_in_file = __class__.get_material_names_from_file(file_name)
                                            
                                            # Check if our target material is in this file
                                            is_primary_material = False
                                            if material_name_in_xml.lower() == "primary":
                                                is_primary_material = True
                                            # if the material name has no underscores it might be a primary material
                                            elif "_" not in material_name_in_xml:
                                                # check to see if the material name is part of the file name, e.g. exterior_medium_frequnecy_panels_wear_mtl_Wear
                                                if f'_{material_name_in_xml.lower()}' in clean_path.lower():
                                                    is_primary_material = True

                                            if is_primary_material:
                                                # For primary materials, check if the file contains only primary materials (filename stem should be in the list)
                                                primary_name = Path(file_name).stem
                                                if primary_name in material_names_in_file and len(material_names_in_file) == 1:
                                                    # This is a primary material file
                                                    found_filepath = filepath
                                                    if globals_and_threading.debug: print(f"DEBUG: Found primary material '{material_name_in_xml}' as '{primary_name}' in {clean_path}")
                                                    break
                                                elif globals_and_threading.debug:
                                                    print(f"DEBUG: File contains named materials, not a primary material file, skipping {clean_path}")
                                                    continue
                                            elif material_name_in_xml in material_names_in_file:
                                                # Found the named material in this file
                                                found_filepath = filepath
                                                if globals_and_threading.debug: print(f"DEBUG: Found material '{material_name_in_xml}' in {clean_path}")
                                                break
                                            elif globals_and_threading.debug:
                                                print(f"DEBUG: Material '{material_name_in_xml}' not found in {clean_path} (contains: {material_names_in_file})")
                                        except Exception as e:
                                            if globals_and_threading.debug: print(f"DEBUG: Error checking materials in {clean_path}: {e}")
                                            continue
                                    else:
                                        if globals_and_threading.debug: print(f"DEBUG: File NOT found on disk: {filepath}")
                                        if str(filepath) not in __class__.missing_files and not str(filepath).startswith('$') and 'ddna.glossmap' not in str(filepath).lower():
                                            __class__.missing_files.append(str(filepath))
                                
                                if not found_filepath:
                                    # If we didn't find the material in any of the files, assume it's the first one
                                    if globals_and_threading.debug: print(f"DEBUG: Material '{material_name_in_xml}' not found in any of the files, using the first one: {paths_to_check[0]}")
                                    found_filepath = __class__.extract_dir / paths_to_check[0]
                                file_cache[filename] = found_filepath
                                if globals_and_threading.debug: print(f"DEBUG: Using file: {found_filepath}")
                                # Check for Material01 or Tintable_01 type materials and remap:
                                blender_utils.SCOrg_tools_blender.fix_unmapped_materials(str(found_filepath))

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
            if globals_and_threading.debug: print(f"DEBUG: Attempting to load tint palette for: {record.name} - tint: {tint_number}")
            tints, tint_materials = tint_utils.SCOrg_tools_tint.get_tint_pallet_list(record)
            # get the nth tint palette GUID from the dict's keys
            if tints and len(tints) > tint_number:
                tint_guid = list(tints.keys())[tint_number]
                if tints:
                    __class__.load_tint_palette(tint_guid, tint_node_group.name)
                    
                    # Apply the tint GUID to the root ship object as a custom property
                    try:
                        # Find the base empty object (root ship object)
                        base_empty = __class__.get_base_empty()
                        
                        if base_empty:
                            base_empty['Applied_Tint'] = tint_guid
                            if globals_and_threading.debug: 
                                print(f"DEBUG: Applied tint GUID {tint_guid} to base object {base_empty.name}")
                        else:
                            if globals_and_threading.debug: 
                                print("DEBUG: Could not find base empty object to apply tint GUID")
                    except Exception as e:
                        if globals_and_threading.debug: 
                            print(f"DEBUG: Error applying tint GUID to base object: {e}")
                    
                    if globals_and_threading.debug:
                        print(f"DEBUG: materials: {tint_materials}")

                    # Check if the tint has a custom material
                    if tint_guid in tint_materials and tint_materials[tint_guid]:
                        # Get the material name
                        material_name = tint_materials[tint_guid]
                        if globals_and_threading.debug: 
                            print(f"DEBUG: Tint {tint_number} ({tint_guid}) has custom material: {material_name}")
                    else:
                        # No custom material for this tint, use the default
                        if globals_and_threading.debug: print(f"DEBUG: Tint {tint_number} ({tint_guid}) has no custom material, using default")
                        material_name = None
                    # import the custom material:
                    __class__.change_paint_material(material_name)
            else:
                if globals_and_threading.debug: 
                    if not tints: print(f"DEBUG: No tints available for record {record.name}")
                    else: print(f"DEBUG: Tint number {tint_number} out of range. Available tints: {len(tints)}")
        
        if len(file_cache) > 0:
            # Import the materials using scdatatools
            from scdatatools.blender import materials
            __class__.tint_palette_node_group_name = tint_node_group.name
            if globals_and_threading.debug: print("Importing materials from files")
            values = list(file_cache.values())
            if globals_and_threading.debug:
                print(f"DEBUG: Importing {len(values)} materials from files:")
                pprint(values)
            
            # Use misc_utils to capture console output
            _, captured_stdout, captured_stderr = misc_utils.SCOrg_tools_misc.capture_console_output(
                materials.load_materials, 
                values, 
                data_dir='', 
                tint_palette_node_group=tint_node_group
            )
            
            # Extract missing texture paths from captured output
            print(f"DEBUG: Before texture extraction, missing_files has {len(__class__.missing_files)} items")
            __class__.extract_missing_textures_from_output(captured_stdout, captured_stderr)
            print(f"DEBUG: After texture extraction, missing_files has {len(__class__.missing_files)} items")
        
        # Clear progress when done
        misc_utils.SCOrg_tools_misc.clear_progress()
        if globals_and_threading.debug: print("DEBUG: Cleared progress after import_missing_materials")
    
    @staticmethod
    def get_material_filename(material_name):
        before, sep, after = material_name.partition('_mtl')
        if sep:
            result = before + '.mtl'
        else:
            result = material_name  # _mtl not found, leave unchanged
        return result
    
    @staticmethod
    def load_tint_palette(palette_guid, tint_palette_node_group_name):
        if globals_and_threading.debug: print("Loading tint palette for GUID:", palette_guid)
        import scdatatools
        if __class__.extract_dir is None:
            __class__.init()
        
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
    
    @staticmethod
    def get_record_name(record):
        """
        Returns the name of the record
        """
        # Check if record is None
        if record is None:
            if globals_and_threading.debug: print("DEBUG: get_record_name called with None record")
            return None
        # Get the localisation index via Components -> VehicleComponentParams -> vehicleName
        locale_id = None
        if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
            for comp in record.properties.Components:
                if comp.name == "VehicleComponentParams":
                    if hasattr(comp.properties, 'vehicleName'):
                        locale_id = comp.properties.vehicleName
                        if locale_id is not None:
                            break;
        if locale_id is None:
            # Check Components -> SCItemPurchasableParams -> displayName
            for comp in record.properties.Components:
                if comp.name == "SCItemPurchasableParams":
                    if hasattr(comp.properties, 'displayName'):
                        locale_id = comp.properties.displayName
                        if locale_id is not None:
                            break;
        if locale_id is None:
            if globals_and_threading.debug: print("DEBUG: No locale id found in record properties")
            return None
        
        # strip the "@" prefix if it exists
        locale_id = locale_id.lstrip('@')

        # Get the localisation string
        try:
            locale_string = globals_and_threading.localizer.gettext(locale_id)
            if locale_string:
                return locale_string
            else:
                if globals_and_threading.debug: print(f"DEBUG: No localisation string found for id {locale_id}")
                return None
        except Exception as e:
            if globals_and_threading.debug: print(f"DEBUG: Error getting localisation string for id {locale_id}: {e}")
            return None
    
    @staticmethod
    def read_file_from_p4k(filename):
        """
        Read any file from the loaded P4K archive.
        
        Args:
            filename: Path to the file within the P4K archive
        
        Returns:
            File content as string (decoded from bytes if necessary) or bytes if decoding fails
        """
        
        if globals_and_threading.p4k is None:
            print("Error: P4K archive not loaded")
            return None
        
        try:
            # Get file info and open it
            file_info = globals_and_threading.p4k.getinfo(filename)
            with globals_and_threading.p4k.open(file_info, mode='r') as file:
                content = file.read()
                
                # If already a string, return as-is
                if isinstance(content, str):
                    return content
                
                # If bytes, check if it's a CryXML binary file first
                if isinstance(content, bytes):
                    # Check if it's a CryXMLB file (binary XML format)
                    if content.startswith(b"CryXmlB"):
                        try:
                            from scdatatools.engine.cryxml import etree_from_cryxml_string, pprint_xml_tree
                            import xml.etree.ElementTree as ET
                            if globals_and_threading.debug: print(f"DEBUG: Detected CryXMLB binary format for {filename}, converting to XML")
                            
                            # Parse the binary CryXML and convert to XML string
                            root_element = etree_from_cryxml_string(content)
                            # Create ElementTree from Element and use pprint_xml_tree
                            tree = ET.ElementTree(root_element)
                            xml_content = pprint_xml_tree(tree)
                            return xml_content
                            
                        except Exception as e:
                            print(f"Warning: Failed to parse CryXMLB file {filename}: {e}")
                            # Fall through to regular decoding
                    
                    # Try common encodings in order of likelihood
                    encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'ascii']
                    
                    for encoding in encodings_to_try:
                        try:
                            decoded_content = content.decode(encoding)
                            if globals_and_threading.debug: print(f"DEBUG: Successfully decoded {filename} using {encoding} encoding")
                            return decoded_content
                        except UnicodeDecodeError:
                            continue
                    
                    # If all encodings fail, return the raw bytes
                    print(f"Warning: Could not decode {filename} as text, returning raw bytes")
                    return content
                
                return content
                
        except KeyError:
            print(f"File {filename} not found in archive")
            return None
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            return None
    
    @staticmethod
    def set_translation_new_data_preference(reset = False):
        """
        If Blender is not in English, set the translation for the New data preference to off
        """
        # Check if the current language is not English
        if bpy.context.preferences.view.language != 'en_US':
            if not reset:
                # Get the current preference and save it to be restored later
                __class__.translation_new_data_preference = bpy.context.preferences.view.use_translate_new_dataname
                # Set the Blender global preference for translate new dataname to False
                bpy.context.preferences.view.use_translate_new_dataname = False
                if globals_and_threading.debug: print("DEBUG: Set translation for New data preference to on due to non-English language")
            else:
                # Reset the preference to the original value
                if __class__.translation_new_data_preference is not None:
                    bpy.context.preferences.view.use_translate_new_dataname = __class__.translation_new_data_preference
                    if globals_and_threading.debug: print("DEBUG: Reset translation for New data preference to original value")
    
    @staticmethod
    def import_dae(geometry_path: typing.Union[str, Path]):
        """Import a .dae file using Blender's built-in Collada importer."""
        file = geometry_path.with_suffix(".dae")
        if not file.is_file():
            if globals_and_threading.debug: print(f"Skipping file {geometry_path.stem}: dae does not exist {geometry_path}")
            return False

        result = bpy.ops.wm.collada_import(filepath=str(geometry_path), auto_connect=False)
        if 'FINISHED' not in result:
            if globals_and_threading.debug: print(f"❌ ERROR: Failed to import DAE for: {geometry_path}")
            return False
        return True

    @staticmethod
    def get_main_material_file():
        """
        Find an object with 'body' in the name and specific source_file custom property,
        then return the name of the material in slot 1 (index 0).
        """
        # Iterate through objects in the scene from the top level downwards
        if globals_and_threading.debug: print("DEBUG: Searching for main material file...")

        # get the getometry path for the current ship
        geometry_path = __class__.get_geometry_path(record = globals_and_threading.imported_record, original_path = True)
        geometry_path = geometry_path.lower()

        if not geometry_path:
            if globals_and_threading.debug: print("DEBUG: No geometry path found for the current ship")
            return None
        if globals_and_threading.debug: print(f"DEBUG: Geometry path for current ship: {geometry_path}")
        
        for obj in bpy.data.objects:
            # Check if object has 'body' in the name (case-insensitive), and if it has the custom property 'source_file' with the geometry path set
            if 'body' in obj.name.lower() and 'source_file' in obj:
                # Check if object has the custom property 'source_file'
                if 'source_file' in obj and globals_and_threading.debug: print(f"DEBUG: Found object with 'body' in name: {obj.name}, source_file: {obj['source_file']}")
                if 'source_file' in obj and obj['source_file'].lower() == str(geometry_path).lower():
                    # Check if object has material slots
                    if obj.material_slots and len(obj.material_slots) > 0:
                        # Get the first material slot (slot 1)
                        material = obj.material_slots[0].material
                        if material:
                            print(f"Found object: {obj.name}")
                            print(f"Material in slot 1: {material.name}")
                            if 'original_filename' in material:
                                # return just the filenaame, as the original_filename is the full path
                                return Path(material['original_filename']).name
                            else:
                                if 'filename' in material:
                                    # Store the original filename as a custom property if not already present
                                    material['original_filename'] = material['filename']
                                    return Path(material['filename']).name
                                else:
                                    # last resort, use the material name to get the filename
                                    return __class__.get_material_filename(material.name)
                        else:
                            print(f"Found object: {obj.name} but slot 1 has no material")
                            return None
                    else:
                        print(f"Found object: {obj.name} but it has no material slots")
                        return None
        
        print("No matching object found")
        return None
    
    @staticmethod
    def change_paint_material(paint_material_file = None):
        if globals_and_threading.debug: print("DEBUG: change_paint_material called with paint_material_file:", paint_material_file)
        if __class__.extract_dir is None:
            __class__.init()
        # Get material file from paint
        if paint_material_file is None:
            if globals_and_threading.debug: print("DEBUG: No paint material file provided, using default material")
            main_material_file = __class__.get_main_material_file()
            if not main_material_file:
                if globals_and_threading.debug: print("DEBUG: No main material file found, cannot change paint material")
                return None
            main_material_name = main_material_file.replace('.', '_').lower()
            # Search through materials to find any starting with the main material name
            paint_material_file = None
            for mat in bpy.data.materials:
                if mat.name.lower().startswith(main_material_name):
                    if 'original_filename' in mat:
                        paint_material_file = mat['original_filename']
                        break
                    if 'filename' in mat:
                        paint_material_file = mat['filename']
                        break
            if not paint_material_file:
                if globals_and_threading.debug: print("DEBUG: No paint material file found, cannot change paint material")
                return None
            if globals_and_threading.debug: print(f"DEBUG: Using paint material file from main material: {paint_material_file}")
   
        # add the extract_dir to path
        paint_material_file = __class__.extract_dir / paint_material_file

        # Check the node group name is set
        if not __class__.tint_palette_node_group_name:
            if globals_and_threading.debug: print("DEBUG: No tint palette node group name set, cannot change paint material")
            return None
        # check if the paint material file exists
        if not paint_material_file.is_file():
            if globals_and_threading.debug: print(f"Error: Paint material file {paint_material_file} does not exist, please extract the file from the P4K archive")
            return None
        
        # Get main material file
        main_material_file = __class__.get_main_material_file()
        if not main_material_file:
            if globals_and_threading.debug: print("DEBUG: No main material file found, cannot change paint material")
            return None
        # replace the . with an _ in the file name
        main_material_name = main_material_file.replace('.', '_').lower()

        # Get the list of materials indexed by the position of the main material file
        original_materials = __class__.get_material_names_from_file(main_material_file)
        # Get the list of materials indexed by the position of the paint material file
        paint_materials = __class__.get_material_names_from_file(paint_material_file.name)
        if globals_and_threading.debug: print(f"DEBUG: original_materials: {original_materials}")
        if globals_and_threading.debug: print(f"DEBUG: paint_materials: {paint_materials}")
        
        # Loop through all materials with the main material file name and get the index
        for i, original_matname in enumerate(original_materials):
            matname = main_material_name + '_' + original_matname
            # Get the material object by name
            mat = bpy.data.materials.get(matname)
            if not mat:
                if globals_and_threading.debug: print(f"DEBUG: Material {matname} not found in Blender data, searching...")
                for m in bpy.data.materials:
                    if m.name.lower().startswith(main_material_name.lower()) and 'original_name' in m and m['original_name'] == matname:
                        mat = m
                        if globals_and_threading.debug: print(f"DEBUG: Search found material {mat.name} matching main material file {main_material_file}, renaming to {matname}")
                        mat.name = matname
                        break                
                # If we still don't have a material after searching, skip this iteration
                if not mat:
                    if globals_and_threading.debug: print(f"DEBUG: Material {matname} not found even after search, skipping")
                    continue
            
            if globals_and_threading.debug: print(f"DEBUG: Found material {mat.name} matching main material file {main_material_file}")
            if 'filename' in mat:
                if 'original_filename' not in mat:
                    # Store the original filename as a custom property if not already present
                    mat['original_filename'] = mat['filename']
                # remove the filename custom property to allow it to be re-imported
                del mat['filename']
            if 'original_name' not in mat:
                # Store the original name as a custom property if not already present
                mat['original_name'] = mat.name
            if original_materials[i] != paint_materials[i]:
                # If the material name in the paint material file is different, change it so it matches the paint material file
                mat.name = main_material_name + '_' + paint_materials[i]
                if globals_and_threading.debug: print(f"DEBUG: Changed material name from {original_matname} to {paint_materials[i]}")
        # Create a tmp directory if it doesn't exist, return an error if it fails
        tmp_dir = Path(__class__.extract_dir).parent / "material_tmp"
        if not tmp_dir.exists():
            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                if globals_and_threading.debug: print(f"Error creating tmp directory: {e}")
                return None
        # Copy the paint material file to the tmp directory with the main material file name
        tmp_paint_material_file = tmp_dir / main_material_file
        try:
            # Copy the paint material file to the tmp directory
            import shutil
            shutil.copy(paint_material_file, tmp_paint_material_file)
            if globals_and_threading.debug: print(f"DEBUG: Copied paint material file to {tmp_paint_material_file}")
        except Exception as e:
            if globals_and_threading.debug: print(f"Error copying paint material file: {e}")
            return None
        
        # Ensure translation for new data preference is set to off
        __class__.set_translation_new_data_preference()
        # import the new material
        if globals_and_threading.debug: print(f"DEBUG: Importing new material ({paint_material_file}), tint_palette_node_group: {__class__.tint_palette_node_group_name}")
        from scdatatools.blender import materials
        # get the tint palette node group from the name
        node_group = bpy.data.node_groups.get(__class__.tint_palette_node_group_name)
        if not node_group:
            # Report an error if the node group is not found
            if globals_and_threading.debug: print(f"ERROR: Tint palette node group '{__class__.tint_palette_node_group_name}' not found")
            return None
        # Use misc_utils to capture console output
        _, captured_stdout, captured_stderr = misc_utils.SCOrg_tools_misc.capture_console_output(
            materials.load_materials, 
            [tmp_paint_material_file], 
            data_dir=__class__.extract_dir, 
            tint_palette_node_group=node_group
        )
        # Reset the translation preference to its original state
        __class__.set_translation_new_data_preference(reset=True)
        # Extract missing texture paths from captured output
        __class__.extract_missing_textures_from_output(captured_stdout, captured_stderr)
        # Removed popup here - will show at end of import process
        # remove the temporary material file
        if tmp_paint_material_file.exists():
            try:
                tmp_paint_material_file.unlink()
                if globals_and_threading.debug: print(f"DEBUG: Removed temporary material file {tmp_paint_material_file}")
            except Exception as e:
                if globals_and_threading.debug: print(f"Error removing temporary material file: {e}")

    @staticmethod
    def get_material_names_from_file(filename):
        """
        Get a list of material names from a material file (.mtl).
        
        Args:
            filename: Name of the material file (without path), e.g. "some_material.mtl"
        
        Returns:
            List of material names found in the file, or empty list if file not found/error
        """
        if __class__.extract_dir is None:
            __class__.init()
        if not __class__.extract_dir:
            if globals_and_threading.debug: print("ERROR: extract_dir is not set. Please set it in the addon preferences.")
            return []

        p4k = globals_and_threading.p4k
        if not p4k:
            if globals_and_threading.debug: print("ERROR: Please load Data.p4k first")
            return []

        # Search for the specific .mtl file
        filename_lower = filename.lower()
        if globals_and_threading.debug: print(f"DEBUG: Looking for material file: {filename}")
        
        try:
            # Use the MTL lookup helper to find matching files
            mtl_lookup = __class__.build_mtl_lookup()
            
            # Find files that match our filename
            matching_files = []
            if filename_lower in mtl_lookup:
                paths_to_check = mtl_lookup[filename_lower]
                
                # Handle both single string and list of paths
                if isinstance(paths_to_check, str):
                    matching_files.append(paths_to_check)
                else:
                    matching_files.extend(paths_to_check)
            
            if not matching_files:
                if globals_and_threading.debug: print(f"DEBUG: No files found matching {filename}")
                return []
            
            if globals_and_threading.debug: print(f"DEBUG: Found {len(matching_files)} file(s) matching {filename}")
            
            # Process each matching file to extract material names
            all_material_names = []
            
            for clean_path in matching_files:
                if globals_and_threading.debug: print(f"DEBUG: Processing file: Data/{clean_path}")
                filepath = __class__.extract_dir / clean_path
                
                if not filepath.exists():
                    if globals_and_threading.debug: print(f"DEBUG: File NOT found on disk: {filepath}")
                    continue
                
                try:
                    # Read and parse the MTL file
                    xml_content = __class__.read_file_from_p4k(f"Data/{clean_path}")
                    if not xml_content:
                        if globals_and_threading.debug: print(f"DEBUG: Could not read content from {clean_path}")
                        continue
                    
                    # Convert to string if it's bytes
                    if isinstance(xml_content, bytes):
                        try:
                            xml_content = xml_content.decode('utf-8')
                        except UnicodeDecodeError:
                            if globals_and_threading.debug: print(f"DEBUG: Could not decode content from {clean_path}")
                            continue
                    
                    # Ensure we have a string
                    if not isinstance(xml_content, str):
                        if globals_and_threading.debug: print(f"DEBUG: Content is not a string for {clean_path}")
                        continue
                    
                    # Extract material names from the XML content
                    material_names = []
                    
                    # Check if this is a primary material (no Name attributes)
                    if 'Name=' not in xml_content:
                        # Primary material - use filename without extension as material name
                        primary_name = Path(filename).stem
                        material_names.append(primary_name)
                        if globals_and_threading.debug: print(f"DEBUG: Found primary material: {primary_name}")
                    else:
                        # Named materials - extract all Name="..." patterns
                        import re
                        name_pattern = r'Name="([^"]+)"'
                        matches = re.findall(name_pattern, xml_content)
                        
                        for match in matches:
                            if match not in material_names:  # Avoid duplicates
                                material_names.append(match)
                                if globals_and_threading.debug: print(f"DEBUG: Found named material: {match}")
                    
                    # Add materials from this file to the overall list
                    for mat_name in material_names:
                        if mat_name not in all_material_names:
                            all_material_names.append(mat_name)
                            
                except Exception as e:
                    if globals_and_threading.debug: print(f"DEBUG: Error reading {clean_path}: {e}")
                    continue
            
            if globals_and_threading.debug: print(f"DEBUG: Total unique materials found: {len(all_material_names)}")
            return all_material_names
            
        except Exception as e:
            if globals_and_threading.debug: print(f"DEBUG: Error searching for .mtl files: {e}")
            return []
    
    @staticmethod
    def build_mtl_lookup():
        """
        Build a lookup dictionary for MTL files using cached search results.
        Returns a dictionary: lowercase filename -> full_path or list of paths
        """
        p4k = globals_and_threading.p4k
        if not p4k:
            return {}
            
        # Use cached MTL files if available
        if __class__._cached_mtl_files is None:
            if globals_and_threading.debug: print("DEBUG: No cached MTL files found, performing search...")
            __class__._cached_mtl_files = p4k.search(file_filters=".mtl", ignore_case=True, mode='endswith')  # type: ignore
            if globals_and_threading.debug: print(f"DEBUG: Cached {len(__class__._cached_mtl_files) if __class__._cached_mtl_files else 0} MTL files")
        else:
            if globals_and_threading.debug: print("DEBUG: Using cached MTL files search results for lookup")
        
        mtl_files = __class__._cached_mtl_files
        if globals_and_threading.debug: print(f"DEBUG: Building lookup from {len(mtl_files) if mtl_files else 0} .mtl files")
        
        # Build lookup dictionary: lowercase filename -> full_path or list of paths
        mtl_lookup = {}
        if mtl_files:  # Check if mtl_files is not None
            for match in mtl_files:  # type: ignore
                if hasattr(match, 'filename'):
                    full_path = match.filename
                else:
                    continue
                
                filename = Path(full_path).name.lower()
                clean_path = full_path.removeprefix("Data/")
                
                # Handle multiple files with same filename
                if filename in mtl_lookup:
                    # Convert to list if not already
                    if isinstance(mtl_lookup[filename], str):
                        mtl_lookup[filename] = [mtl_lookup[filename]]
                    # Add new path to list
                    mtl_lookup[filename].append(clean_path)
                else:
                    # First occurrence, store as string
                    mtl_lookup[filename] = clean_path
        
        if globals_and_threading.debug: print(f"DEBUG: Built lookup for {len(mtl_lookup)} unique .mtl filenames")
        return mtl_lookup

    @staticmethod
    def extract_missing_files(file_list_text, prefs):
        """
        Extract missing files from Data.p4k archive.
        
        Args:
            file_list_text (str): Newline-separated list of files to extract
            prefs: Addon preferences object
            
        Returns:
            tuple: (success_count, fail_count, report_lines)
        """
        import os
        import shutil
        import subprocess
        from pathlib import Path
        
        cgf_converter = prefs.cgf_converter_path
        extract_dir = Path(prefs.extract_dir)
        
        if not cgf_converter or not os.path.exists(cgf_converter):
            raise ValueError("cgf-converter.exe path not set or invalid in preferences.")

        if not extract_dir or not extract_dir.exists():
            raise ValueError("Extract directory not set or invalid.")

        # Get sc instance
        sc = globals_and_threading.sc
        if not sc or not sc.p4k:
            raise ValueError("Data.p4k not loaded. Please load it first.")

        
        # Get files from the list passed by the popup
        files_to_process = [f.strip() for f in file_list_text.split('\n') if f.strip()]
            
        if not files_to_process:
            return 0, 0, []

        # Filter out comments or empty lines
        files_to_process = [f for f in files_to_process if not f.startswith('#')]
        
        # Skip .ddna.glossmap* files
        files_to_process = [f for f in files_to_process if '.ddna.glossmap' not in f.lower()]
        
        conversion_exts = ['.cga', '.cgf', '.chr', '.skin']
        texture_exts = ['.tif', '.png', '.jpg', '.jpeg', '.tga', '.bmp']
        supported_exts = conversion_exts + ['.mtl'] + texture_exts
        
        success_count = 0
        fail_count = 0
        extracted_files = []
        report_lines = []
        
        # Start progress using the same system as other functions
        misc_utils.SCOrg_tools_misc.update_progress("Starting extraction...", 0, len(files_to_process), force_update=True, spinner_type="arc")
        
        try:
            for i, file_path_str in enumerate(files_to_process):
                misc_utils.SCOrg_tools_misc.update_progress(f"Extracting {Path(file_path_str).name}", i, len(files_to_process), spinner_type="arc")
                
                # Normalize path for P4K search
                search_path = file_path_str.replace("\\", "/")
                # Ensure it starts with Data/
                if not search_path.lower().startswith("data/"):
                    search_path = "Data/" + search_path
                
                # Fix for absolute paths that got prefixed incorrectly
                if search_path.startswith("Data/") and ":" in search_path:
                    path_part = search_path[5:]
                    extract_str = str(extract_dir).replace("\\", "/")
                    if path_part.startswith(extract_str):
                        relative_part = path_part[len(extract_str):].lstrip('/').lstrip('\\')
                        if not relative_part.lower().startswith("data/"):
                            relative_part = "Data/" + relative_part
                        search_path = relative_part
                
                # Determine candidate paths to search
                candidate_paths = []
                path_obj = Path(search_path)
                suffix = path_obj.suffix.lower()
                
                if suffix == '.dae':
                    # Try to find the source file by replacing extension
                    # Only map to geometry formats, not .mtl
                    for ext in conversion_exts:
                        candidate_paths.append(path_obj.with_suffix(ext).as_posix())
                elif suffix in texture_exts:
                    # Map texture request to .dds source
                    candidate_paths.append(path_obj.with_suffix('.dds').as_posix())
                elif suffix in supported_exts:
                    candidate_paths.append(search_path)
                
                matches = []
                found_source_path = None
                
                for candidate in candidate_paths:
                    try:
                        # Check if file exists in P4K
                        results = sc.p4k.search(candidate)
                        if results:
                            matches = results
                            found_source_path = candidate
                            break # Found a match, stop searching extensions
                    except Exception as e:
                        print(f"Error searching P4K for {candidate}: {e}")
                        continue

                if not matches:
                    msg = f"File not found in P4K: {search_path}"
                    print(msg)
                    report_lines.append(f"❌ {msg}")
                    fail_count += 1
                    continue
                
                # Use the first match
                p4k_file = matches[0]
                
                try:
                    # Extract file manually to control the path
                    # p4k_file is a P4KInfo object
                    
                    # Get the internal filename (e.g. Data/Objects/...)
                    internal_path = p4k_file.filename
                    
                    # Strip "Data/" prefix if present to avoid Data/Data/ structure
                    # The extract_dir usually points to the game-data/Data folder
                    relative_path = internal_path
                    if relative_path.lower().startswith("data/"):
                        relative_path = relative_path[5:] # Remove "Data/"
                    elif relative_path.lower().startswith("data\\"):
                         relative_path = relative_path[5:]
                    
                    # Construct the full destination path
                    final_path = extract_dir / relative_path
                    
                    # Ensure parent directory exists
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file content
                    with sc.p4k.open(p4k_file) as src, open(final_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    
                    extracted_path = final_path
                    
                    if not extracted_path.exists():
                        msg = f"Warning: Extracted file not found at expected path: {extracted_path}"
                        print(msg)
                        report_lines.append(f"⚠️ {msg}")
                        fail_count += 1
                        continue
                        
                    extracted_files.append(extracted_path)
                    
                    # Convert if it's a geometry file
                    if extracted_path.suffix.lower() in conversion_exts:
                        # Extract companion files needed for conversion
                        companion_exts = ['.cgam', '.chrparams', '.meshsetup']
                        companion_files = []
                        
                        for comp_ext in companion_exts:
                            companion_path_in_p4k = Path(internal_path).with_suffix(comp_ext).as_posix()
                            
                            try:
                                comp_matches = sc.p4k.search(companion_path_in_p4k)
                                if comp_matches:
                                    comp_p4k_file = comp_matches[0]
                                    comp_internal_path = comp_p4k_file.filename
                                    
                                    # Strip "Data/" prefix
                                    comp_relative_path = comp_internal_path
                                    if comp_relative_path.lower().startswith("data/"):
                                        comp_relative_path = comp_relative_path[5:]
                                    elif comp_relative_path.lower().startswith("data\\"):
                                        comp_relative_path = comp_relative_path[5:]
                                    
                                    # Extract companion file
                                    comp_final_path = extract_dir / comp_relative_path
                                    comp_final_path.parent.mkdir(parents=True, exist_ok=True)
                                    
                                    with sc.p4k.open(comp_p4k_file) as src, open(comp_final_path, 'wb') as dst:
                                        shutil.copyfileobj(src, dst)
                                    
                                    if comp_final_path.exists():
                                        companion_files.append(comp_final_path)
                            except Exception as e:
                                # Companion file not found or error - this is OK, not all files have all companions
                                pass
                        
                         # Run cgf-converter
                        if not cgf_converter or not os.path.exists(cgf_converter):
                            msg = f"Extracted {extracted_path.name} but cgf-converter not found."
                            print(msg)
                            report_lines.append(f"⚠️ {msg}")
                        else:
                            # Run converter
                            # cgf-converter.exe "path/to/file"
                            # It usually outputs .dae in the same folder
                            try:
                                # Suppress window on Windows
                                startupinfo = None
                                if os.name == 'nt':
                                    startupinfo = subprocess.STARTUPINFO()
                                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                                
                                result = subprocess.run(
                                    [cgf_converter, str(extracted_path)],
                                    capture_output=True,
                                    text=True,
                                    startupinfo=startupinfo
                                )
                                
                                if result.returncode == 0:
                                    # Delete the original file and all companion files
                                    files_to_delete = [extracted_path] + companion_files
                                    deleted_count = 0
                                    
                                    for file_to_del in files_to_delete:
                                        try:
                                            file_to_del.unlink()
                                            deleted_count += 1
                                        except Exception as e:
                                            print(f"Failed to delete {file_to_del.name}: {e}")
                                    
                                    msg = f"Extracted, Converted & Cleaned: {extracted_path.name}"
                                    print(msg)
                                    report_lines.append(f"✅ {msg}")
                                    success_count += 1
                                else:
                                    msg = f"Extracted {extracted_path.name} but conversion failed: {result.stderr}"
                                    print(msg)
                                    report_lines.append(f"⚠️ {msg}")
                                    # Still count as success for extraction? Maybe.
                                    success_count += 1 
                            except Exception as e:
                                msg = f"Extracted {extracted_path.name} but converter error: {e}"
                                print(msg)
                                report_lines.append(f"⚠️ {msg}")
                                success_count += 1
                    elif extracted_path.suffix.lower() == '.dds':
                        # This is a texture file - extract split parts and convert with texconv
                        texconv_path = prefs.texconv_path
                        
                        if not texconv_path or not os.path.exists(texconv_path):
                            msg = f"Extracted {extracted_path.name} but texconv not found."
                            print(msg)
                            report_lines.append(f"⚠️ {msg}")
                            success_count += 1
                        else:
                            # Extract all split parts (.dds.1, .dds.2, etc.)
                            split_parts = []
                            part_num = 1
                            
                            while True:
                                split_part_path_in_p4k = f"{internal_path}.{part_num}"
                                
                                try:
                                    split_matches = sc.p4k.search(split_part_path_in_p4k)
                                    if split_matches:
                                        split_p4k_file = split_matches[0]
                                        split_internal_path = split_p4k_file.filename
                                        
                                        # Strip "Data/" prefix
                                        split_relative_path = split_internal_path
                                        if split_relative_path.lower().startswith("data/"):
                                            split_relative_path = split_relative_path[5:]
                                        elif split_relative_path.lower().startswith("data\\"):
                                            split_relative_path = split_relative_path[5:]
                                        
                                        # Extract split part
                                        split_final_path = extract_dir / split_relative_path
                                        split_final_path.parent.mkdir(parents=True, exist_ok=True)
                                        
                                        with sc.p4k.open(split_p4k_file) as src, open(split_final_path, 'wb') as dst:
                                            shutil.copyfileobj(src, dst)
                                        
                                        if split_final_path.exists():
                                            split_parts.append(split_final_path)
                                        
                                        part_num += 1
                                    else:
                                        # No more parts found
                                        break
                                except Exception:
                                    # Part not found or error - stop looking
                                    break
                            
                            # Combine split parts into the base file if any
                            if split_parts:
                                split_parts.sort(key=lambda p: int(p.suffix[1:]))  # Sort by .1, .2, etc.
                                with open(extracted_path, 'ab') as base_file:
                                    for part in split_parts:
                                        with open(part, 'rb') as part_file:
                                            shutil.copyfileobj(part_file, base_file)
                                        part.unlink()  # Delete the part after appending
                                split_parts = []  # Clear the list since deleted
                            
                            # Determine output format from original request
                            original_suffix = Path(file_path_str).suffix.lower()
                            if original_suffix in texture_exts:
                                output_format = original_suffix[1:]  # Remove the dot
                            else:
                                output_format = 'tif'  # Default to tif
                            
                            # Check if the DDS is BC5_SNORM, and if so, skip conversion to match StarFab behavior
                            is_bc5 = False
                            try:
                                info_result = subprocess.run([texconv_path, '-nologo', '-fileinfo', str(extracted_path)], capture_output=True, text=True, timeout=10)
                                if 'BC5_SNORM' in info_result.stdout:
                                    is_bc5 = True
                            except Exception:
                                pass  # If info fails, proceed with conversion
                            
                            if is_bc5:
                                # Convert BC5_SNORM with R8G8B8A8_UNORM format to allow conversion to requested format
                                extra_args = ['-f', 'R8G8B8A8_UNORM']
                            else:
                                extra_args = []
                            
                            # Run texconv
                            try:
                                startupinfo = None
                                if os.name == 'nt':
                                    startupinfo = subprocess.STARTUPINFO()
                                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                                
                                # texconv [extra_args] -ft <format> <input.dds> -o <output_dir>
                                cmd = [texconv_path, '-y'] + extra_args + ['-ft', output_format, str(extracted_path), '-o', str(extracted_path.parent)]
                                result = subprocess.run(
                                    cmd,
                                    capture_output=True,
                                    text=True,
                                    startupinfo=startupinfo
                                )
                                
                                if result.returncode == 0:
                                        # Delete all DDS files (base + split parts)
                                        files_to_delete = [extracted_path] + split_parts
                                        deleted_count = 0
                                        
                                        for file_to_del in files_to_delete:
                                            try:
                                                file_to_del.unlink()
                                                deleted_count += 1
                                            except Exception as e:
                                                print(f"Failed to delete {file_to_del.name}: {e}")
                                        
                                        msg = f"Extracted, Converted & Cleaned: {extracted_path.name}"
                                        print(msg)
                                        report_lines.append(f"✅ {msg}")
                                        success_count += 1
                                else:
                                    msg = f"Extracted {extracted_path.name} but conversion failed: stdout={result.stdout}, stderr={result.stderr}"
                                    print(msg)
                                    report_lines.append(f"⚠️ {msg}")
                                    success_count += 1
                            except Exception as e:
                                msg = f"Extracted {extracted_path.name} but texconv error: {e}"
                                print(msg)
                                report_lines.append(f"⚠️ {msg}")
                                success_count += 1
                    else:
                        #Non-convertible file (e.g. .mtl)
                        msg = f"Extracted: {extracted_path.name}"
                        print(msg)
                        report_lines.append(f"✅ {msg}")
                        success_count += 1
                        
                except Exception as e:
                    msg = f"Error processing {file_path_str}: {e}"
                    print(msg)
                    report_lines.append(f"❌ {msg}")
                    fail_count += 1
                    continue
        finally:
            # Clear progress
            misc_utils.SCOrg_tools_misc.update_progress(hide_message=True, hide_progress=True, force_update=True)
        
        return success_count, fail_count, report_lines