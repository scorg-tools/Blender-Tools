import bpy
import re
import time  # Add time import
import os
from mathutils import Matrix
from . import import_utils # For import_utils.SCOrg_tools_import.import_missing_materials
from . import misc_utils # Add this import for progress updates
import xml.etree.ElementTree as ET
from . import globals_and_threading
import glob

class SCOrg_tools_blender():
    _last_redraw_time = 0  # Class variable to track last redraw time
    
    @staticmethod
    def update_viewport_with_timer(interval_seconds=2.0, force_reset=False, redraw_now=False):
        """
        Periodically force Blender to redraw the viewport based on a timer.
        Restored functionality while keeping it efficient.
        """
        current_time = time.time()
        
        # Reset timer if requested (for starting new operations)
        if force_reset or redraw_now:
            SCOrg_tools_blender._last_redraw_time = current_time
            if not redraw_now:
                return False
        
        # Check if enough time has passed
        if redraw_now or current_time - SCOrg_tools_blender._last_redraw_time >= interval_seconds:
            if globals_and_threading.debug: 
                print(f"DEBUG: {interval_seconds} seconds elapsed, forcing screen redraw")
            
            try:
                # Suppress console output during redraw operations to avoid warnings
                import sys
                import os
                from contextlib import redirect_stdout, redirect_stderr
                
                # Temporarily redirect both stdout and stderr to suppress warnings
                with open(os.devnull, 'w') as devnull:
                    with redirect_stdout(devnull), redirect_stderr(devnull):
                        # Force Blender to update the viewport
                        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                        
                        # Also tag areas for redraw
                        for window in bpy.context.window_manager.windows:
                            for area in window.screen.areas:
                                if area.type == 'VIEW_3D':
                                    area.tag_redraw()
                
            except Exception as e:
                if globals_and_threading.debug:
                    print(f"Error in viewport redraw: {e}")
            
            # Update the last redraw time
            SCOrg_tools_blender._last_redraw_time = current_time
            
            # Process any pending events to allow UI updates
            bpy.app.handlers.depsgraph_update_post.clear()
            bpy.context.view_layer.update()
            
            return True
        
        return False

    def add_weld_and_weighted_normal_modifiers():
        for i, obj in enumerate(bpy.data.objects):
            misc_utils.SCOrg_tools_misc.update_progress("Adding weld modifiers", i, len(bpy.data.objects), spinner_type="arc")
            if obj.type != 'MESH':
                continue

            # Check if Weld modifier already exists
            has_weld = any(mod.type == 'WELD' for mod in obj.modifiers)
            if not has_weld:
                weld = obj.modifiers.new(name="Weld", type='WELD')
                weld.merge_threshold = 0.000001
                #print(f"Added Weld modifier to {obj.name}")

            # Check if Weighted Normal modifier already exists
            has_weighted_normal = any(mod.type == 'WEIGHTED_NORMAL' for mod in obj.modifiers)
            if not has_weighted_normal:
                wn = obj.modifiers.new(name="WeightedNormal", type='WEIGHTED_NORMAL')
                wn.mode = 'FACE_AREA'
                wn.weight = 50
                wn.keep_sharp = True
                wn.thresh = 0.01  # Corrected attribute name
                #print(f"Added Weighted Normal modifier to {obj.name}")


    def material_matches_decals(name):
        """
        Check if the material name matches the pattern for decals, POM, or stencils.
        Args:
            name (str): The material name to check.
        Returns:
            bool: True if the material name matches the pattern, False otherwise.
        """
        name = name.lower()
        return "_pom" in name or "_decal" in name or "_stencil" in name

    def ensure_vertex_group(obj, mat_index, group_name):
        # Check if vertex group already exists (case-insensitive)
        for vg in obj.vertex_groups:
            if vg.name.lower() == group_name.lower():
                return vg

        # Create the vertex group
        vg = obj.vertex_groups.new(name=group_name)

        # Collect all vertices from faces that use this material
        vertices = set()
        mesh = obj.data
        if not mesh.polygons:
            return vg

        for poly in mesh.polygons:
            if poly.material_index == mat_index:
                for vid in poly.vertices:
                    vertices.add(vid)

        # Assign those vertices with weight = 1.0
        if vertices:
            vg.add(list(vertices), 1.0, 'REPLACE')

        return vg

    def add_displace_modifiers_for_decal(displacement_strength = 0.005):
        objects_list = list(bpy.data.objects)
        for i, obj in enumerate(objects_list):
            misc_utils.SCOrg_tools_misc.update_progress("Adding Displace modifiers for POM and Decal", i, len(objects_list), spinner_type="arc")
            if obj.type != 'MESH':
                continue

            mesh = obj.data

            # Skip if no materials
            if not mesh.materials:
                continue

            for mat_index, mat in enumerate(mesh.materials):
                if mat and __class__.material_matches_decals(mat.name):
                    group_name = mat.name
                    vg = __class__.ensure_vertex_group(obj, mat_index, group_name)

                    # 1) Check if a Displace modifier for this vertex group already exists
                    modifier_exists = False
                    for mod in obj.modifiers:
                        if mod.type == 'DISPLACE' and mod.vertex_group == vg.name:
                            #print(f"Displace modifier for {obj.name} using group '{vg.name}' already exists. Skipping.")
                            modifier_exists = True
                            break

                    if not modifier_exists:
                        # Create displace modifier
                        mod = obj.modifiers.new(name=f"Displace_{group_name}", type='DISPLACE')
                        mod.strength = displacement_strength
                        mod.mid_level = 0
                        mod.vertex_group = vg.name
                        #print(f"Added Displace modifier for {obj.name} using group '{vg.name}'")

    def remove_duplicate_displace_modifiers():
        objects_list = list(bpy.data.objects)
        for i, obj in enumerate(objects_list):
            misc_utils.SCOrg_tools_misc.update_progress("Removing duplicate Displace modifiers", i, len(objects_list), spinner_type="arc")
            if obj.type != 'MESH':
                continue

            seen_vertex_groups = set()
            # This list will store the NAMES of modifiers to be removed.
            modifier_names_to_remove = []

            # It's important to iterate over a COPY of the modifiers list
            # if you plan to modify the original list during iteration.
            # However, since we're just collecting names here, a direct iteration is fine
            # as long as the removal happens afterwards.
            for mod in obj.modifiers:
                if mod.type == 'DISPLACE' and mod.vertex_group:
                    vg_name_lower = mod.vertex_group.lower()

                    if vg_name_lower not in seen_vertex_groups:
                        # This is the first time we've seen a DISPLACE modifier for this vertex group.
                        # Keep this one.
                        seen_vertex_groups.add(vg_name_lower)
                    else:
                        # We've already seen a DISPLACE modifier for this vertex group.
                        # This one is a duplicate, so mark its name for removal.
                        modifier_names_to_remove.append(mod.name)
                        #print(f"Marked duplicate Displace modifier '{mod.name}' from '{obj.name}' for vertex group '{mod.vertex_group}' for removal.")
            
            # Now, remove the marked modifiers by name.
            # Iterate in reverse when removing, to ensure indices don't shift unexpectedly
            # as we remove items from the object's modifiers collection.
            for mod_name in reversed(modifier_names_to_remove):
                if mod_name in obj.modifiers: # Check if it still exists (e.g., not manually removed)
                    obj.modifiers.remove(obj.modifiers[mod_name])
                    #print(f"Removed duplicate Displace modifier '{mod_name}' from '{obj.name'.")
                    
    def fix_modifiers(displacement_strength=0.005):
        # Get addon preferences
        prefs = bpy.context.preferences.addons["scorg_tools"].preferences

        # Ensure we're in object mode (only if there's an active object)
        if bpy.context.active_object is not None:
            bpy.ops.object.mode_set(mode='OBJECT')
        elif bpy.context.mode != 'OBJECT':
            # If no active object but we're not in object mode, try to find any object to make active
            scene_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
            if scene_objects:
                bpy.context.view_layer.objects.active = scene_objects[0]
                bpy.ops.object.mode_set(mode='OBJECT')
            # If still no objects available, we'll proceed without setting mode
        
        if prefs.enable_weld_weighted_normal:
            __class__.add_weld_and_weighted_normal_modifiers()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_displace_decals:
            __class__.add_displace_modifiers_for_decal(displacement_strength)
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_remove_duplicate_displace:
            __class__.remove_duplicate_displace_modifiers()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_remove_proxy_geometry:
            __class__.remove_proxy_material_geometry()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_remap_material_users:
            __class__.remap_material_users()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_import_missing_materials:
            import_utils.SCOrg_tools_import.import_missing_materials()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_fix_materials_case:
            __class__.fix_materials_case_sensitivity()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_set_glass_transparent:
            __class__.set_glass_materials_transparent()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_fix_stencil_materials:
            __class__.fix_stencil_materials()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_3d_pom:
            __class__.replace_pom_materials()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_remove_engine_flame_materials:
            __class__.set_engine_flame_mat_transparent()
            __class__.update_viewport_with_timer(redraw_now=True)
        
        if prefs.enable_tidyup:
            __class__.tidyup()
        
        # Clear progress when done
        misc_utils.SCOrg_tools_misc.clear_progress()

    def select_children(obj):
        if hasattr(obj, 'objects'):
            children = obj.objects
        else:
            children = obj.children
        for child in children:
            child.select_set(True)
            __class__.select_children(child)

    def make_instances_real(collection_name):
        if globals_and_threading.debug: print('Collection:'+collection_name)
        __class__.select_children(bpy.data.collections[collection_name])
        roots = [ _ for _ in bpy.context.selected_objects if _.instance_collection is not None ]
        instances = set()
        for root in roots:
            if root.instance_collection is None:
                continue  # we may have already made it real from another root
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            __class__.select_children(root)
            instances.add(root)
            for obj in bpy.context.selected_objects:
                if obj.instance_type == "COLLECTION":
                    instances.add(obj)

        instances_list = list(instances)
        for i, inst in enumerate(instances_list):
            misc_utils.SCOrg_tools_misc.update_progress("Making instances real", i, len(instances_list), spinner_type="arc")
            for obj in bpy.context.selected_objects:
               obj.select_set(False)
            inst.select_set(True)
            bpy.ops.object.duplicates_make_real(
                use_base_parent=True, use_hierarchy=True
            )
        # Clear progress when done
        misc_utils.SCOrg_tools_misc.clear_progress()
        return {"FINISHED"}
        
    def get_main_collection():
        found_base_empty = None
        # Search for the base empty object in the scene
        for obj in bpy.context.scene.objects:
            if obj.type == 'EMPTY' and "container_name" in obj and obj["container_name"] == "base":
                found_base_empty = obj
                if globals_and_threading.debug: print(f"Found base empty: '{found_base_empty.name}'")
                break

        if not found_base_empty:
            print("ERROR: Base empty object with 'container_name' == 'base' not found.")
            return None

        # Determine the target bpy.data.Collection (the actual collection data block)
        target_collection = None
        # Prioritize a non-Scene Collection as the 'direct parent'
        for coll_data in found_base_empty.users_collection:
            if coll_data != bpy.context.scene.collection:
                target_collection = coll_data
                break
        # If only linked to the Scene Collection, use that
        if not target_collection:
            target_collection = bpy.context.scene.collection

        if not target_collection:
            print("ERROR: No suitable parent collection determined for the base empty.")
            return None
        return target_collection

    def run_make_instances_real():
        collection = __class__.get_main_collection()
        collection_name = collection.name
        bpy.ops.object.select_all(action='DESELECT') # Deselect all objects for a clean slate
        # Make instance real so we can remove the StarFab collection and save data
        __class__.make_instances_real(collection_name)
        # Remove the StarFab collection
        if bpy.data.scenes.find('StarFab') >= 0:
            bpy.data.scenes.remove(bpy.data.scenes['StarFab'])
        
        # Tidy up orphan data to save space
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        
        # Move the collection
        if 'Collection' in bpy.data.collections:
            # unlink from the scene collection
            bpy.data.scenes['Scene'].collection.children.unlink(bpy.data.collections[collection_name])
            # link to the Collection collection
            bpy.data.collections['Collection'].children.link(bpy.data.collections[collection_name])

    def fix_bright_lights():
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and obj.data.energy > 30000:
                obj.data.energy /= 1000

    def remove_proxy_material_geometry():
        objects_list = list(bpy.data.objects)
        for i, obj in enumerate(objects_list):
            misc_utils.SCOrg_tools_misc.update_progress("Removing proxy material geometry", i, len(objects_list), spinner_type="arc")
            if obj.type != 'MESH':
                continue
            
            # Find all slots with proxy materials
            slots_to_remove = []
            for slot_idx, slot in enumerate(obj.material_slots):
                mat = slot.material
                if mat:
                    mat_name_lower = mat.name.lower()
                    if (mat_name_lower.endswith('_mtl_proxy') or 
                        mat_name_lower.endswith('_nodraw') or 
                        mat_name_lower.endswith('_physics_proxy')):
                        
                        # Set this object as active and enter edit mode
                        bpy.context.view_layer.objects.active = obj
                        bpy.ops.object.mode_set(mode='OBJECT')
                        
                        # Deselect all faces first
                        for poly in obj.data.polygons:
                            poly.select = False
                        
                        # Select faces that use this material
                        faces_selected = 0
                        for poly in obj.data.polygons:
                            if poly.material_index == slot_idx:
                                poly.select = True
                                faces_selected += 1
                        
                        if faces_selected > 0:
                            if globals_and_threading.debug: 
                                print(f"DEBUG: Removing {faces_selected} faces with material '{mat.name}' from object '{obj.name}'")
                            
                            # Enter edit mode and delete selected faces
                            bpy.ops.object.mode_set(mode='EDIT')
                            bpy.ops.mesh.delete(type='FACE')
                            bpy.ops.object.mode_set(mode='OBJECT')
                            
                            # Mark this slot for removal
                            slots_to_remove.append(slot_idx)
                        else:
                            if globals_and_threading.debug:
                                print(f"DEBUG: No faces found for material '{mat.name}' in object '{obj.name}'")
            
            # Remove material slots (in reverse order to avoid index shifting)
            for slot_idx in sorted(slots_to_remove, reverse=True):
                if slot_idx < len(obj.material_slots):  # Safety check
                    obj.active_material_index = slot_idx
                    bpy.ops.object.material_slot_remove()
                    if globals_and_threading.debug:
                        print(f"DEBUG: Removed material slot {slot_idx} from object '{obj.name}'")

    def convert_bones_to_empties(armature_obj):
        if globals_and_threading.debug: print(f"DEBUG: Converting bones to empties for armature: {armature_obj.name}")
        
        # Ensure the armature object is set as active and selected before changing mode
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.select_all(action='DESELECT')
        armature_obj.select_set(True)
        
        # Only set mode if we're not already in OBJECT mode
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        armature = armature_obj.data
        empties = {}
        root_name = armature_obj.name
        if hasattr(armature_obj, 'parent') and armature_obj.parent:
            # If the armature has a parent, use its name as the root name
            root_name = armature_obj.parent.name
        if globals_and_threading.debug: print(f"DEBUG: Root name set to: {root_name} (parent found)")

        # Create empties for each bone
        for i, bone in enumerate(armature.bones):
            # if the root_name is not set and the armature object has a parent attribute
            if i==0:
                # the first bone will be the root, so save the name
                name = root_name
                empty = bpy.data.objects.new(name, None)
                return_name = empty.name # The name will add .001 etc as the armature currently exists, so remember the name to rename it 
            else:
                name = bone.name
                empty = bpy.data.objects.new(name, None)
            empty['orig_name'] = name

            # Set empty's location in world space
            empty.matrix_world = armature_obj.matrix_world @ bone.matrix_local
            empty['orig_name'] = bone.name  # Store original bone name
            bpy.context.collection.objects.link(empty)
            empties[bone.name] = empty

        # Parent empties to match bone hierarchy
        for bone in armature.bones:
            if bone.parent:
                empties[bone.name].parent = empties[bone.parent.name]

        return return_name

    def convert_armatures_to_empties():
        # Process all armatures in the scene
        empties = []
        armature_objects = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        
        for obj in armature_objects:
            if obj.name not in bpy.data.objects:
                # Object was already deleted, skip it
                continue
                
            # convert the bones to empties
            empty_name = __class__.convert_bones_to_empties(obj)

            # Delete the armature
            name = obj.name
            bpy.data.objects.remove(obj, do_unlink=True)
            # Rename the empty to match the original armature name
            if empty_name and empty_name in bpy.data.objects:
                bpy.data.objects[empty_name].name = name
        return True
    
    def get_original_material(name):
        # Regex pattern to detect material names like "Material.001"
        suffix_pattern = re.compile(r"(.*)\.(\d{3})$")
        match = suffix_pattern.match(name)
        if match:
            base_name = match.group(1)
            if base_name in bpy.data.materials:
                return bpy.data.materials[base_name]
        return None

    def remap_material_users():
        # Regex pattern to detect material names with numeric suffixes
        suffix_pattern = re.compile(r"^(.+)\.(\d{3})$")
        
        # Pre-build mapping of duplicate materials to their base versions
        material_mapping = {}
        materials_to_remove = []
        
        for mat in bpy.data.materials:
            match = suffix_pattern.match(mat.name)
            if match:
                base_name = match.group(1)
                base_material = bpy.data.materials.get(base_name)
                if base_material:
                    material_mapping[mat] = base_material
                    materials_to_remove.append(mat)
        
        # Early exit if no duplicates found
        if not material_mapping:
            return
        
        # Pre-filter to only mesh objects with materials and create material usage map
        object_material_map = {}
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.material_slots:
                materials_used = set()
                for slot in obj.material_slots:
                    if slot.material and slot.material in material_mapping:
                        materials_used.add(slot.material)
                if materials_used:  # Only include objects that actually use duplicate materials
                    object_material_map[obj] = materials_used
        
        # Early exit if no objects use duplicate materials
        if not object_material_map:
            # Clean up unused duplicate materials
            for mat in materials_to_remove:
                if mat.users == 0:
                    bpy.data.materials.remove(mat)
            return
        
        # Batch process material reassignments
        mapping_items = list(material_mapping.items())
        for i, (duplicate_mat, original_mat) in enumerate(mapping_items):
            misc_utils.SCOrg_tools_misc.update_progress("Remapping .001 materials", i, len(mapping_items), spinner_type="arc")
            
            # Only process if the duplicate material still exists
            if duplicate_mat.name not in bpy.data.materials:
                continue
            
            # Only process objects that use this specific duplicate material
            for obj, used_materials in object_material_map.items():
                if duplicate_mat in used_materials:
                    for slot in obj.material_slots:
                        if slot.material == duplicate_mat:
                            slot.material = original_mat
                            if globals_and_threading.debug: 
                                print(f"Reassigned material on {obj.name} from {duplicate_mat.name} to {original_mat.name}")
        
        # Batch remove all duplicate materials
        for mat in materials_to_remove:
            if mat.name in bpy.data.materials and mat.users == 0:
                if globals_and_threading.debug: 
                    print(f"Removing unused material: {mat.name}")
                bpy.data.materials.remove(mat)

    def is_material_vanilla(mat):
        """
        Check if the material is a vanilla material.
        """
        if mat.use_nodes:
            nodes = mat.node_tree.nodes
            node_types = {node.type for node in nodes}
            if len(nodes) == 2 and 'BSDF_PRINCIPLED' in node_types and 'OUTPUT_MATERIAL' in node_types:
                # Material has only a Principled BSDF and Material Output node
                return True
            else:
                return False
        else:
            return True  # Non-node materials are considered vanilla
        
    def init_tint_group(entity_name):
        if globals_and_threading.debug: print("Initializing tint group for ship: ", entity_name)
        
        # Check if tint group already exists to prevent duplicates
        from scdatatools.blender.utils import hashed_path_key
        expected_group_name = hashed_path_key(f"{entity_name}_tint")
        double_hashed_group_name = hashed_path_key(f"{expected_group_name}")
        existing_group = bpy.data.node_groups.get(expected_group_name)
        
        if existing_group:
            if globals_and_threading.debug: print(f"Tint group '{expected_group_name}' already exists, reusing")
            return existing_group
        else :
            existing_group = bpy.data.node_groups.get(double_hashed_group_name)
            if existing_group:
                if globals_and_threading.debug: print(f"Tint group '{double_hashed_group_name}' already exists, renaming to '{expected_group_name}'")
                existing_group.name = expected_group_name
                return existing_group
            else:
                if globals_and_threading.debug: print(f"Could not find tint group '{expected_group_name}'")
        
        from scdatatools import blender
        node_group = blender.materials.utils.tint_palette_node_group_for_entity(entity_name)
        return node_group
    
    def parse_unmapped_material_string(input_string):
        """
        Parses a string in the format 'something_mtl_material123' and extracts the parts.

        Args:
            input_string: The string to parse.

        Returns:
            A tuple containing the 'something_mtl' part, the material name, and the number,
            or None if the string does not match the expected format.
        """
        pattern = r"^(.*_mtl)_(material)(\d+)$"
        match = re.match(pattern, input_string, re.IGNORECASE)

        if match:
            prefix = match.group(1)
            material = match.group(2)
            number = int(match.group(3))
            return prefix, material, number
        else:
            return None, None, None
    
    def parse_mtl_names(file_path):
        """
        Parses an .mtl file (XML format) and extracts the 'Name' attributes
        of the 'Material' elements within 'SubMaterials'.

        Args:
            file_path (str): The local path to the .mtl file. (not the P4K path)

        Returns:
            dict: A dictionary where the keys are the line numbers (starting from 1)
                and the values are the corresponding 'Name' attribute values.
                Returns an empty dictionary if the file is not found or parsing fails.
        """
        material_names = {}
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            sub_materials = root.find('SubMaterials')
            if sub_materials is not None:
                for index, material in enumerate(sub_materials, start=0):
                    name = material.get('Name')
                    if name:
                        material_names[index] = name
            else:
                if globals_and_threading.debug: print(f"Warning: No 'SubMaterials' element found in {file_path}")
                return {}
        except FileNotFoundError:
            print(f"Error: File not found at {file_path}")
            return {}
        except ET.ParseError:
            print(f"Error: Could not parse XML file at {file_path}")
            return {}
        return material_names
    
    def fix_unmapped_materials(mtl_file_path):
        """
        Loops through all materials in the scene, checks if they match a specific pattern.
        If they match, it attempts to remap them to an existing material with the same name
        from the .mtl file. If no such material exists, it renames the material.

        Args:
            mtl_file_path (str): The path to the .mtl file containing the correct material names.
        """

        mtl_names = __class__.parse_mtl_names(mtl_file_path)
        if not mtl_names:
            if globals_and_threading.debug: print("Error: Could not parse .mtl file or file is empty.")
            return

        # Get a list of material names instead of material objects
        material_names = list(bpy.data.materials.keys())
        
        for i, mat_name in enumerate(material_names):
            #misc_utils.SCOrg_tools_misc.update_progress("Fixing unmapped materials", i, len(material_names), spinner_type="arc")
            # Get fresh reference to the material
            mat = bpy.data.materials.get(mat_name)
            if mat is None:
                continue
                
            prefix, material_type, number = __class__.parse_unmapped_material_string(mat.name)

            if prefix and material_type and number:
                # Material name matches the pattern
                if number in mtl_names:
                    correct_name = f"{prefix}_{mtl_names[number]}"

                    # Check if a material with the correct name already exists
                    existing_material = bpy.data.materials.get(correct_name)

                    if existing_material:
                        # Remap material users to the existing material
                        __class__.remap_material(mat.name, correct_name, delete_old=True)

                    else:
                        # No material with the same name exists, rename the material
                        if globals_and_threading.debug: print(f"Renaming material '{mat.name}' to '{correct_name}'")
                        mat.name = correct_name

    def remap_material(from_mat_name, to_mat_name, delete_old=False):
        """
        Remaps all users of a material from one name to another.
        
        Args:
            from_mat_name (str): The name of the material to remap from.
            to_mat_name (str): The name of the material to remap to.
        """
        from_mat = bpy.data.materials.get(from_mat_name)
        to_mat = bpy.data.materials.get(to_mat_name)

        if not from_mat or not to_mat:
            print(f"Error: remapping materials, '{from_mat_name}' or '{to_mat_name}' does not exist.")
            return

        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                for i, slot in enumerate(obj.material_slots):
                    if slot.material == from_mat:
                        slot.material = to_mat
                        if globals_and_threading.debug: print(f"Reassigned material on {obj.name} slot {i} from {from_mat.name} to {to_mat.name}")
        
        if delete_old:
            # Remove the old material if it has no users left
            if from_mat.users == 0:
                if globals_and_threading.debug: print(f"Removing unused material: {from_mat.name}")
                bpy.data.materials.remove(from_mat)
    
    def fix_materials_case_sensitivity():
        """
        Fixes materials that have been imported due to different case in names.
        """
        # Get a list of material names instead of material objects
        material_names = list(bpy.data.materials.keys())
        
        for i, mat_name in enumerate(material_names):
            misc_utils.SCOrg_tools_misc.update_progress("Fixing mat case sensitivity", i, len(material_names), spinner_type="arc")
            
            # Get fresh reference to the material
            mat = bpy.data.materials.get(mat_name)
            if mat is None:
                continue
                
            # Check if the material name contains '_mtl_' and if it is a vanilla material (with only Principled BSDF)
            if __class__.is_material_vanilla(mat):
                name = mat.name
                if globals_and_threading.debug: print(f"found broken shader {name}")
                # check if there is another material with the same name but difference case
                for other_mat in bpy.data.materials:
                    if other_mat.name.lower() == name.lower() and other_mat != mat:
                        if globals_and_threading.debug: print(f"found duplicate material {other_mat.name} with different case")
                        # remap the broken material to the other one
                        remap = __class__.remap_material(mat.name, other_mat.name, delete_old=True)
                        break

    @staticmethod
    def set_glass_materials_transparent():
        """
        Find all materials containing '_glass' (case insensitive) and set their 
        viewport display alpha to 0.3 for partial transparency in the viewport.
        """        
        # Get a list of material names instead of material objects
        material_names = list(bpy.data.materials.keys())
        
        for i, mat_name in enumerate(material_names):
            misc_utils.SCOrg_tools_misc.update_progress("Setting glass to transparent", i, len(material_names), spinner_type="arc")
            
            # Get fresh reference to the material
            material = bpy.data.materials.get(mat_name)
            if material is None:
                continue
                
            if '_glass' in material.name.lower():
                # Set the viewport display alpha to 0.1 (10% opacity)
                material.diffuse_color = (*material.diffuse_color[:3], 0.1)
                if globals_and_threading.debug: print(f"Setting viewport transparency for glass material: {material.name}")
    
    def fix_stencil_materials():
        """
        Fix materials that use stencil textures by ensuring they are set up correctly.
        """
        if globals_and_threading.debug: print("Fixing stencil materials.")
        # Iterate through all materials in the scene
        for mat in bpy.data.materials:
            # Check if material uses nodes
            if not mat.use_nodes or not mat.node_tree:
                continue

            # Check if the material has the custom property 'STENCIL_MAP'
            if 'StringGenMask' in mat and "STENCIL_MAP" in str(mat['StringGenMask']):
                # Find the _Illum node group
                illum_node = None
                stencil_image_node = None
                for node in mat.node_tree.nodes:
                    if node.type == 'GROUP' and node.node_tree and '_illum' in node.node_tree.name.lower():
                        if globals_and_threading.debug: print(f"Updating alpha and shadow settings for stencil material: {mat.name}")
                        illum_node = node
                        mat.blend_method = "HASHED"
                        mat.shadow_method = "NONE"
                        mat.show_transparent_back = True
                        mat.cycles.use_transparent_shadow = True
                        mat.use_screen_refraction = True
                        mat.refraction_depth = 0.01
                        # Set the UseAlpha input to 1
                        if 'UseAlpha' in node.inputs:
                            node.inputs['UseAlpha'].default_value = 1.0
                        else:
                            if globals_and_threading.debug: print(f"Warning: _Illum node group in material {mat.name} does not have UseAlpha input")
                    elif node.type == 'TEX_IMAGE':
                        # Check if the image texture is a stencil map
                        if globals_and_threading.debug: print(f"Checking image node {node.name} in material {mat.name}")
                        if "_stencil" in node.image.filepath.lower():
                            stencil_image_node = node
                if illum_node and stencil_image_node:
                    # check the stencil image is connected
                    if not stencil_image_node.outputs['Color'].is_linked:
                        if globals_and_threading.debug: print(f"Stencil image node {stencil_image_node.name} in material {mat.name} is not linked, adding _TintDecalConverter node")
                        # If not linked, add a _TintDecalConverter group node
                        tint_decal_converter_node = mat.node_tree.nodes.new('ShaderNodeGroup')
                        tint_decal_converter_node.node_tree = bpy.data.node_groups.get('_TintDecalConverter')
                        tint_decal_converter_node.location = stencil_image_node.location
                        stencil_image_node.location.x -= 300  # Move the stencil image node to the left
                        # Connect the stencil image node to the _TintDecalConverter node
                        mat.node_tree.links.new(stencil_image_node.outputs['Color'], tint_decal_converter_node.inputs['Image'])
                        mat.node_tree.links.new(stencil_image_node.outputs['Alpha'], tint_decal_converter_node.inputs['Alpha'])
                        # Connect the _TintDecalConverter node to the _Illum node
                        mat.node_tree.links.new(tint_decal_converter_node.outputs['Color'], illum_node.inputs['diff Color'])
                        mat.node_tree.links.new(tint_decal_converter_node.outputs['Alpha'], illum_node.inputs['diff Alpha'])

    def create_transparent_image(name="transparent", width=1, height=1):
        """
        Creates a new 1x1 image with 0% alpha (fully transparent).

        Args:
            name (str): The name for the new image.
            width (int): The width of the image (default 1).
            height (int): The height of the image (default 1).
        """
        # Check if an image with this name already exists
        if name in bpy.data.images:
            existing_image = bpy.data.images[name]
            return existing_image

        image = bpy.data.images.new(name=name, width=width, height=height, alpha=True)

        # Create a transparent pixel (R, G, B, A)
        # Alpha value is 0.0 for fully transparent
        transparent_pixel = [0.0, 0.0, 0.0, 0.0]

        # Set all pixels to transparent
        # For a 1x1 image, this sets the single pixel
        # For larger images, you'd multiply the pixel list to fill all pixels
        image.pixels = transparent_pixel * (width * height)

        print(f"Created transparent image: '{image.name}' ({image.size[0]}x{image.size[1]})")
        return image
    
    def separate_decal_materials():
        """
        Separates materials that match the pattern for decals, POM, or stencils
        into their own mesh object, parented to the original mesh.
        Only processes original objects (not linked duplicates) and creates corresponding
        decal objects for all linked duplicates.
        """
        # Pre-filter objects to only process those with decal materials
        objects_to_process = []
        # Group objects by their mesh data to identify originals vs linked duplicates
        mesh_to_objects = {}
        
        # get a list of all mesh objects in the scene that don't have "_scorg_decals" in their name
        objects_list = [obj for obj in bpy.data.objects if obj.type == 'MESH' and "_scorg_decals" not in obj.name]
        
        for obj in objects_list:
            if not obj.data.materials:
                continue
                
            # Group objects by their mesh data
            if obj.data not in mesh_to_objects:
                mesh_to_objects[obj.data] = []
            mesh_to_objects[obj.data].append(obj)
        
        # Only process the first object for each unique mesh data (the "original")
        for mesh_data, objects_with_mesh in mesh_to_objects.items():
            # Take the first object as the "original" to process
            original_obj = objects_with_mesh[0]
            
            # Quick check: does this object have any decal materials?
            has_decal_materials = any(
                mat and __class__.material_matches_decals(mat.name) 
                for mat in original_obj.data.materials
            )
            
            if has_decal_materials:
                # Check if any faces actually use these materials
                decal_material_indices = [
                    i for i, mat in enumerate(original_obj.data.materials)
                    if mat and __class__.material_matches_decals(mat.name)
                ]
                
                has_decal_faces = any(
                    poly.material_index in decal_material_indices 
                    for poly in original_obj.data.polygons
                )
                
                if has_decal_faces:
                    # Store the original object and all its linked duplicates
                    objects_to_process.append((original_obj, objects_with_mesh, decal_material_indices))
        
        objects_list = None  # Clear the list to free memory
        
        # Batch apply displacement modifiers first (much faster than doing it per object)
        if objects_to_process:
            if globals_and_threading.debug:
                print(f"Applying displacement modifiers to {len(objects_to_process)} objects...")
            
            for original_obj, all_objects_with_mesh, decal_material_indices in objects_to_process:
                modifiers_to_apply = [mod for mod in original_obj.modifiers if mod.type == 'DISPLACE']
                if modifiers_to_apply:
                    # Ensure the object exists and can be made active
                    if original_obj.name in bpy.data.objects:
                        bpy.context.view_layer.objects.active = original_obj
                        # Only set mode if we have a valid active object
                        if bpy.context.active_object == original_obj:
                            if bpy.context.mode != 'OBJECT':
                                bpy.ops.object.mode_set(mode='OBJECT')
                    
                    for mod in modifiers_to_apply:
                        try:
                            bpy.ops.object.modifier_apply(modifier=mod.name)
                        except Exception as e:
                            if globals_and_threading.debug:
                                print(f"Failed to apply modifier to {original_obj.name}: {e}")
        
        # Process separations
        for i, (original_obj, all_objects_with_mesh, decal_material_indices) in enumerate(objects_to_process):
            misc_utils.SCOrg_tools_misc.update_progress("Separating decal materials", i, len(objects_to_process), spinner_type="arc")
            
            if globals_and_threading.debug:
                face_count = sum(1 for poly in original_obj.data.polygons if poly.material_index in decal_material_indices)
                linked_count = len(all_objects_with_mesh) - 1
                print(f"Processing {original_obj.name} with {face_count} decal faces ({linked_count} linked duplicates)")

            # Ensure we're in object mode
            # First check if the object exists and can be made active
            if original_obj.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = original_obj
                # Only set mode if we have a valid active object
                if bpy.context.active_object == original_obj and bpy.context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')

            # Deselect all and select only our target object
            bpy.ops.object.select_all(action='DESELECT')
            original_obj.select_set(True)

            # Pre-select faces using bmesh for better performance
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(original_obj.data)
            
            # Clear existing selection
            for face in bm.faces:
                face.select = False
            
            # Select faces with decal materials
            decal_face_count = 0
            for face in bm.faces:
                if face.material_index in decal_material_indices:
                    face.select = True
                    decal_face_count += 1
            
            if decal_face_count == 0:
                bm.free()
                continue
            
            # Update mesh with selection
            bm.to_mesh(original_obj.data)
            bm.free()
            original_obj.data.update()

            # Enter edit mode and separate
            bpy.ops.object.mode_set(mode='EDIT')
            
            try:
                bpy.ops.mesh.separate(type='SELECTED')
                if globals_and_threading.debug:
                    print(f"Successfully separated {decal_face_count} decal faces from {original_obj.name}")
            except Exception as e:
                if globals_and_threading.debug:
                    print(f"Failed to separate faces from {original_obj.name}: {e}")
                bpy.ops.object.mode_set(mode='OBJECT')
                continue

            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')

            # Find the newly created object (it should be selected)
            new_objects = [o for o in bpy.context.selected_objects if o != original_obj]
            
            if new_objects:
                original_decal_obj = new_objects[0]  # Take the first new object
                
                # Rename the original decal object
                original_decal_obj.name = f"{original_obj.name}_scorg_decals"
                
                # Set decal object to not cast shadows
                original_decal_obj.visible_shadow = False
                
                # Store the current world matrix before any parenting changes
                world_matrix = original_decal_obj.matrix_world.copy()
                
                # Parent the decal object to the original mesh
                original_decal_obj.parent = original_obj
                original_decal_obj.parent_type = 'OBJECT'
                
                # Restore the world matrix to maintain position
                original_decal_obj.matrix_world = world_matrix
                
                if globals_and_threading.debug:
                    print(f"Created decal object: {original_decal_obj.name}, parented to: {original_obj.name}")

                # Create linked duplicate decal objects for all linked duplicates
                for linked_obj in all_objects_with_mesh[1:]:  # Skip the first (original) object
                    # Create linked duplicate of the decal object
                    linked_decal_obj = original_decal_obj.copy()
                    linked_decal_obj.data = original_decal_obj.data  # Share mesh data (linked duplicate)
                    bpy.context.collection.objects.link(linked_decal_obj)
                    
                    # Rename and parent to the corresponding linked object
                    linked_decal_obj.name = f"{linked_obj.name}_scorg_decals"
                    
                    # Parent to the linked object first
                    linked_decal_obj.parent = linked_obj
                    linked_decal_obj.parent_type = 'OBJECT'
                    
                    # Set the same local transform relative to parent as the original decal
                    # This ensures it follows the linked object's transform
                    linked_decal_obj.matrix_parent_inverse = original_decal_obj.matrix_parent_inverse.copy()
                    
                    if globals_and_threading.debug:
                        print(f"Created linked decal object: {linked_decal_obj.name}, parented to: {linked_obj.name}")

            # Batch remove empty material slots from the original object
            # Check which slots are now empty after separation
            slots_to_remove = []
            for slot_idx in decal_material_indices:
                has_faces = any(poly.material_index == slot_idx for poly in original_obj.data.polygons)
                if not has_faces:
                    slots_to_remove.append(slot_idx)

            # Remove empty material slots (in reverse order to avoid index shifting)
            if slots_to_remove:
                for slot_idx in sorted(slots_to_remove, reverse=True):
                    if slot_idx < len(original_obj.material_slots):
                        original_obj.active_material_index = slot_idx
                        bpy.ops.object.material_slot_remove()
                        if globals_and_threading.debug:
                            print(f"Removed empty material slot {slot_idx} from {original_obj.name}")

        # Clear progress when done
        misc_utils.SCOrg_tools_misc.clear_progress()
    
    def append_pom_material():
        """
        Append the 'scorg_pom' material from pom.blend to the current Blender file.
        If the material already exists, delete it first.
        """
        material_name = "scorg_pom"
        pom_blend_file = "pom.blend"
        
        # Check if material already exists and delete it
        if material_name in bpy.data.materials:
            if globals_and_threading.debug: print(f"Material '{material_name}' already exists. Deleting it...")
            bpy.data.materials.remove(bpy.data.materials[material_name])
            if globals_and_threading.debug: print(f"Material '{material_name}' deleted.")
        
        # Get the directory of this addon file
        addon_dir = os.path.dirname(os.path.abspath(__file__))
        pom_blend_path = os.path.join(addon_dir, pom_blend_file)
        
        # Check if pom.blend exists
        if not os.path.exists(pom_blend_path):
            if globals_and_threading.debug: print(f"Error: {pom_blend_file} not found in {addon_dir}")
            return None
        
        # Append the material from pom.blend
        try:
            with bpy.data.libraries.load(pom_blend_path) as (data_from, data_to):
                if material_name in data_from.materials:
                    data_to.materials = [material_name]
                    if globals_and_threading.debug: print(f"Appending material '{material_name}' from {pom_blend_file}...")
                else:
                    if globals_and_threading.debug: print(f"Error: Material '{material_name}' not found in {pom_blend_file}")
                    return None
            
            if globals_and_threading.debug: print(f"Successfully appended material '{material_name}' from {pom_blend_file}")
            return bpy.data.materials.get("scorg_pom")
            
        except Exception as e:
            if globals_and_threading.debug: print(f"Error appending material: {str(e)}")
            return None
    
    def make_node_groups_unique_recursive(node_tree, material_name, processed_groups=None, unique_mapping=None):
        """
        Recursively make all node groups unique within a node tree and its nested groups.
        Reuses the same unique instance for multiple occurrences of the same node group.
        """
        if processed_groups is None:
            processed_groups = set()
        if unique_mapping is None:
            unique_mapping = {}  # Maps original node group to its unique copy
        
        if not node_tree or id(node_tree) in processed_groups:
            return unique_mapping
        
        processed_groups.add(id(node_tree))
        
        for node in node_tree.nodes:
            if node.type == 'GROUP' and node.node_tree:
                original_group = node.node_tree
                
                # Check if we've already made this node group unique for this material
                if original_group in unique_mapping:
                    # Reuse the existing unique copy
                    node.node_tree = unique_mapping[original_group]
                    if globals_and_threading.debug: 
                        print(f"Reusing unique node group '{node.node_tree.name}' for material {material_name}")
                else:
                    # Make this node group unique if it has multiple users
                    if original_group.users > 1:
                        unique_copy = original_group.copy()
                        unique_mapping[original_group] = unique_copy
                        node.node_tree = unique_copy
                        if globals_and_threading.debug: 
                            print(f"Made node group '{unique_copy.name}' unique for material {material_name}")
                    else:
                        # Already unique, just map it to itself
                        unique_mapping[original_group] = original_group
                
                # Recursively process nested node groups with the same mapping
                __class__.make_node_groups_unique_recursive(node.node_tree, material_name, processed_groups, unique_mapping)
        
        return unique_mapping
    
    def find_and_set_displacement_image(material, image_path):
        """
        Find the POM_disp node group in the material and set its displacement image.
        Also sets the bias value on POM_vector based on the top-left pixel brightness.
        Only needs to be done once since all instances in the material share the same node group.
        """
        image_obj = None
        
        # Search through all node groups in the material to find POM_disp
        for node_group_data in bpy.data.node_groups:
            if 'pom_disp' in node_group_data.name.lower():
                # Check if this node group is used in our material
                group_used_in_material = False
                for node in material.node_tree.nodes:
                    if node.type == 'GROUP' and node.node_tree == node_group_data:
                        group_used_in_material = True
                        break
                    # Also check nested groups (like in POM_vector or POM_parallax)
                    elif node.type == 'GROUP' and node.node_tree:
                        for nested_node in node.node_tree.nodes:
                            if nested_node.type == 'GROUP' and nested_node.node_tree == node_group_data:
                                group_used_in_material = True
                                break
                        if group_used_in_material:
                            break
                
                if group_used_in_material:
                    # Found the POM_disp node group used in this material
                    # Find the displacement texture node inside it
                    for node in node_group_data.nodes:
                        if node.type == 'TEX_IMAGE' and 'pom_displ' in node.label.lower():
                            # Found the displacement texture node
                            if image_path.startswith('//') or '/' in image_path or '\\' in image_path:
                                try:
                                    image_obj = bpy.data.images.load(image_path)
                                    node.image = image_obj
                                    if globals_and_threading.debug: 
                                        print(f"Assigned displacement image {image_path} to POM_disp node group {node_group_data.name}")
                                except:
                                    if globals_and_threading.debug: 
                                        print(f"Failed to load displacement image {image_path}")
                            else:
                                existing_image = bpy.data.images.get(image_path)
                                if existing_image:
                                    node.image = existing_image
                                    image_obj = existing_image
                                    if globals_and_threading.debug: 
                                        print(f"Assigned existing displacement image {image_path} to POM_disp node group {node_group_data.name}")
                            
                            # Set colorspace for displacement image
                            if image_obj:
                                image_obj.colorspace_settings.name = 'Non-Color'
                                if globals_and_threading.debug: 
                                    print(f"Set colorspace to Non-Color for displacement image")
                            break
                    break
        
        # If we successfully loaded/found the displacement image, sample the top-left pixel
        if image_obj:
            try:
                # Ensure the image has pixels loaded
                if not image_obj.pixels:
                    image_obj.pixels.foreach_get([])  # Force pixel data loading
                
                # Get the top-left pixel (0,0) - note that Blender stores pixels as RGBA
                # For a displacement map, we typically use the red channel or average RGB
                width = image_obj.size[0]
                height = image_obj.size[1]
                
                if width > 0 and height > 0:
                    # Blender stores pixels in a flat array: [R,G,B,A, R,G,B,A, ...]
                    # Top-left pixel is at index 0
                    pixel_data = image_obj.pixels[0:4]  # Get first 4 values (RGBA)
                    
                    # Calculate brightness (luminance) from RGB values
                    # Using standard luminance formula: 0.299*R + 0.587*G + 0.114*B
                    brightness = 0.299 * pixel_data[0] + 0.587 * pixel_data[1] + 0.114 * pixel_data[2]
                    
                    if globals_and_threading.debug:
                        print(f"Top-left pixel RGB: ({pixel_data[0]:.3f}, {pixel_data[1]:.3f}, {pixel_data[2]:.3f})")
                        print(f"Calculated brightness: {brightness:.3f}")
                    
                    # Now find POM_vector node groups and set the Bias value
                    # Only look for POM_vector that's used in this specific material
                    for node in material.node_tree.nodes:
                        if node.type == 'GROUP' and node.node_tree and 'pom_vector' in node.node_tree.name.lower():
                            # This is the POM_vector node group used in this material
                            if 'Bias' in node.inputs:
                                node.inputs['Bias'].default_value = brightness
                                if globals_and_threading.debug:
                                    print(f"Set Bias to {brightness:.3f} on POM_vector node {node.name} for material {material.name}")
                                break
                    
                    return True
                else:
                    if globals_and_threading.debug:
                        print(f"Warning: Displacement image has invalid dimensions: {width}x{height}")
                        
            except Exception as e:
                if globals_and_threading.debug:
                    print(f"Error sampling displacement image pixel: {e}")
        
        if globals_and_threading.debug: 
            print(f"Could not find POM_disp node group for material {material.name}")
        return False

    def replace_pom_materials():
        """
        Replace all _pom_decal materials in the scene with the 'scorg_pom' material.
        """       
        pom_material = bpy.data.materials.get("scorg_pom")
        if not pom_material:
            pom_material = __class__.append_pom_material()
        
        if not pom_material:
            if globals_and_threading.debug: print("Error: 'scorg_pom' material not found. Please append it first.")
            return False
        
        suffix_list = ['_diff', '_ddna.glossmap', '_ddna', '_ddn', '_spec', '_displ', '_pom_height', '_disp']
        mapped_suffixes = {
            '_ddn': '_ddna',
            '_pom_height': '_displ'
        }
        
        # Iterate through all materials in the scene
        for mat in bpy.data.materials:
            # Check if material uses nodes
            if not mat.use_nodes or not mat.node_tree:
                if globals_and_threading.debug: print(f"Material {mat.name} doesn't use nodes, skipping")
                continue

            # Check if the material has the custom property 'StringGenMask' and is a POM
            if 'StringGenMask' in mat and ("%PARALLAX_OCCLUSION_MAPPING" in str(mat['StringGenMask']) or "_tire" in mat.name.lower() or "_tyre" in mat.name.lower()):
                custom_properties = {}
                for key in mat.keys():
                    if key != "cycles":
                        print(f"{key} = {mat.get(key)}")
                        custom_properties[key] = mat.get(key)
            else:
                # skip this material as it's not a POM material
                continue
            
            # Extract images used by the material with specific suffixes
            images = {}
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    if globals_and_threading.debug: print(f"Checking image node '{node.name}' with image '{node.image.name}' in material {mat.name}")
                    
                    # Check if the image name contains any of our suffixes
                    for suffix in suffix_list:
                        if suffix in node.image.name.lower():
                            # Map alternative suffixes to the main ones
                            if suffix in mapped_suffixes:
                                suffix = mapped_suffixes[suffix]
                            images[suffix] = node.image.filepath if node.image.filepath else node.image.name
                            if globals_and_threading.debug: print(f"Found {suffix} image: {images[suffix]}")
                            break
            
            if globals_and_threading.debug: print(f"Images used by {mat.name}: {images}")
            # Exit early if _displ or _pom_height is not found
            if not images.get('_displ') and not images.get('_pom_height') and not images.get('_disp'):
                if globals_and_threading.debug: print(f"Material {mat.name} does not have required displacement or height map images, skipping")
                continue

            # Check to see if we are missing any of the required images
            missing_images = [suffix for suffix in suffix_list if suffix not in images]
            # Remove the alternative suffixes as they will be remapped to the main ones
            missing_images = [suffix for suffix in missing_images if suffix not in ['_ddn', '_pom_height']]
            
            if missing_images:
                if globals_and_threading.debug: 
                    print(f"Material {mat.name} is missing images: {', '.join(missing_images)}. Attempting to find them")
                # Get the filepath of the displacement image (images dict contains strings, not image objects)
                displacement_image_path = images.get('_displ') or images.get('_pom_height') or images.get('_disp')
                # strip the file extension from the displacement image path
                displacement_image_path = os.path.splitext(displacement_image_path)[0]
                # strip the displacement suffix (_displ, _pom_height, or _disp)
                displacement_suffixes = ['_pom_height', '_displ', '_disp']  # Order by length (longest first) to avoid partial matches
                for disp_suffix in displacement_suffixes:
                    if displacement_image_path.lower().endswith(disp_suffix):
                        displacement_image_path = displacement_image_path[:-len(disp_suffix)]
                        break
                # Now try to find the missing images based on the displacement image path
                for suffix in missing_images:
                    # Try multiple extensions
                    found_images = []
                    for ext in ['.tif', '.png', '.tga']:
                        expected_image_path = f"{displacement_image_path}{suffix}{ext}"
                        if globals_and_threading.debug: 
                            print(f"Looking for missing image for {suffix}: {expected_image_path}")
                        if os.path.exists(expected_image_path):
                            found_images.append(expected_image_path)
                            break
                    
                    if found_images:
                        # If we found an image, use the first one
                        images[suffix] = found_images[0]
                        if globals_and_threading.debug: 
                            print(f"Found missing image for {suffix}: {images[suffix]}")

            # If we found any images, replace the material nodes with scorg_pom nodes
            if images:
                if globals_and_threading.debug: print(f"Replacing material {mat.name} with scorg_pom material")
                
                # Store the old material name for reference
                old_mat_name = mat.name
                
                # Duplicate the scorg_pom material
                new_material = pom_material.copy()
                new_material.name = f"{old_mat_name}_temp"
                
                # Make all node groups unique for this material (including nested ones)
                __class__.make_node_groups_unique_recursive(new_material.node_tree, new_material.name)
                
                # Remap all users of the old material to the new material
                for obj in bpy.data.objects:
                    if obj.type == 'MESH':
                        for slot in obj.material_slots:
                            if slot.material == mat:
                                slot.material = new_material
                
                # Delete the old material
                bpy.data.materials.remove(mat)
                
                # Rename the new material to the old name
                new_material.name = old_mat_name

                # Copy the custom properties from the old material to the new one
                for key, value in custom_properties.items():
                    new_material[key] = value
                
                # Now assign the detected images to the appropriate texture nodes
                for suffix, image_path in images.items():
                    if suffix == '_displ' or suffix == '_pom_height' or suffix == '_disp':
                        # Handle displacement image - find and set it once in the POM_disp node group
                        if not __class__.find_and_set_displacement_image(new_material, image_path):
                            if globals_and_threading.debug: 
                                print(f"Could not find displacement texture node for {image_path} in material {new_material.name}")
                    else:
                        # Find texture nodes that might correspond to this suffix
                        for node in new_material.node_tree.nodes:
                            if node.type == 'TEX_IMAGE':
                                node_label_lower = node.label.lower()
                                # Match texture nodes by their labels containing the suffix
                                # Map suffixes to expected labels
                                suffix_to_label = {
                                    '_diff': 'pom_diff',
                                    '_ddna.glossmap': 'pom_glossmap',
                                    '_ddna': 'pom_ddna', 
                                    '_ddn': 'pom_ddna',  # Alternative normal map suffix
                                    '_spec': 'pom_spec'
                                }
                                
                                expected_label = suffix_to_label.get(suffix, '')
                                if expected_label and expected_label in node_label_lower:
                                    image_obj = None
                                    
                                    # Load the image if it's a filepath, otherwise find existing image
                                    if image_path.startswith('//') or '/' in image_path or '\\' in image_path:
                                        # It's a filepath, try to load it
                                        try:
                                            image_obj = bpy.data.images.load(image_path)
                                            node.image = image_obj
                                            if globals_and_threading.debug: print(f"Assigned image {image_path} to node {node.label}")
                                        except:
                                            if globals_and_threading.debug: print(f"Failed to load image {image_path}")
                                    else:
                                        # It's an image name, find existing image
                                        existing_image = bpy.data.images.get(image_path)
                                        if existing_image:
                                            node.image = existing_image
                                            image_obj = existing_image
                                            if globals_and_threading.debug: print(f"Assigned existing image {image_path} to node {node.label}")
                                    
                                    # Set colorspace based on image type
                                    if image_obj:
                                        if suffix == '_diff' or suffix == '_ddna.glossmap':
                                            image_obj.colorspace_settings.name = 'sRGB'
                                            if globals_and_threading.debug: print(f"Set colorspace to sRGB for {suffix} image")
                                        else:
                                            image_obj.colorspace_settings.name = 'Non-Color'
                                            if globals_and_threading.debug: print(f"Set colorspace to Non-Color for {suffix} image")
                                    
                                    break
                
                # Check if _spec image was not found and handle accordingly
                if '_spec' not in images:
                    if globals_and_threading.debug:
                        print(f"No _spec image found for material {new_material.name}, removing spec nodes and setting base color")
                    
                    # Find and remove pom_spec image node
                    spec_node_to_remove = None
                    for node in new_material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and 'pom_spec' in node.label.lower():
                            spec_node_to_remove = node
                            break
                    
                    if spec_node_to_remove:
                        new_material.node_tree.nodes.remove(spec_node_to_remove)
                        if globals_and_threading.debug:
                            print(f"Removed pom_spec image node from material {new_material.name}")
                    
                    # Find and remove Brightness/Contrast node
                    brightness_node_to_remove = None
                    for node in new_material.node_tree.nodes:
                        if node.type == 'BRIGHTCONTRAST':
                            brightness_node_to_remove = node
                            break
                    
                    if brightness_node_to_remove:
                        new_material.node_tree.nodes.remove(brightness_node_to_remove)
                        if globals_and_threading.debug:
                            print(f"Removed Brightness/Contrast node from material {new_material.name}")
                    
                    # Find Principled BSDF and set Base Color to dark gray
                    for node in new_material.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            node.inputs['Base Color'].default_value = [0.06, 0.06, 0.06, 1.0]
                            if globals_and_threading.debug:
                                print(f"Set Principled BSDF Base Color to dark gray for material {new_material.name}")
                            break
                
                # metal_thin materials should use alpha transparency (yeah, it's strange)
                for node in new_material.node_tree.nodes:
                    if node.type == 'VALUE' and node.label == 'Alpha mid-level control':
                        if "SurfaceType" in new_material and new_material["SurfaceType"] == "metal_thin":
                            node.outputs['Value'].default_value = 0.0
                        else:
                            node.outputs['Value'].default_value = -1.0
                        break
                if "_tire" in new_material.name.lower() or "_tyre" in new_material.name.lower():
                    # Update various settings for tyre materials
                    for node in new_material.node_tree.nodes:
                        if node.type == 'GROUP' and node.node_tree and 'pom_vector' in node.node_tree.name.lower():
                            # Set the Bias and Scale for POM_vector
                            node.inputs['Bias'].default_value = 0.5
                            node.inputs['Scale'].default_value = 2.0
                        elif node.label.lower() == 'n_strength':
                            # Set the normal strength for tyre materials
                            node.outputs['Value'].default_value = 5.0
                        elif node.type == 'BSDF_PRINCIPLED':
                            # Set the Base Color to black for tyre materials
                            node.inputs['Base Color'].default_value = [0.0, 0.0, 0.0, 1.0]

                if globals_and_threading.debug: print(f"Successfully replaced material {old_mat_name} with scorg_pom material")

    def deduplicate_images():
        images = {}
        for img in bpy.data.images:
            if not img.filepath in images.keys():
                images[img.filepath] = img
            else:
                if globals_and_threading.debug:
                    print(f"Removing duplicate image: {img.name} with filepath {img.filepath}")
                # remap all users of this image to the first instance
                img.user_remap(images[img.filepath])
                # Remove the duplicate image
                bpy.data.images.remove(img)
    
    def tidyup():
        """        Perform a cleanup of the Blender scene:
        - De-duplicate images
        - Remove orphaned data blocks (images, materials, meshes, etc.)
        """
        __class__.deduplicate_images()
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    
    def set_engine_flame_mat_transparent():
        """
        Set all engine flame materials to be transparent in the viewport.
        This is useful for engine flames that need to be rendered with transparency.
        """
        if globals_and_threading.debug: print("Setting engine flame materials to transparent.")
        for mat in bpy.data.materials:
            if 'engine_flame' in mat.name.lower() and mat.use_nodes:
                # Find material output node
                for node in mat.node_tree.nodes:
                    if node.type == 'OUTPUT_MATERIAL':
                        # Create a transparent shader node
                        transparent_node = mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
                        # connect it to the material output
                        mat.node_tree.links.new(node.inputs['Surface'], transparent_node.outputs['BSDF'])

    def boost_normal_strength_tyre_mats():
        """
        Boost the normal strength of all tyre materials
        """
        if globals_and_threading.debug: print("Boosting normal strength for tyre materials.")
        for mat in bpy.data.materials:
            if 'trim_tyre' in mat.name.lower() and mat.use_nodes:
                # Find the _Illum node group
                for node in mat.node_tree.nodes:
                    if node.type == 'GROUP' and node.node_tree and '_illum' in node.node_tree.name.lower():
                        if globals_and_threading.debug: print(f"Updating normal strength for tyre material: {mat.name}")
                        node.inputs['n Strength'].default_value = 10