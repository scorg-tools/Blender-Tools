import bpy
import tqdm
import re
from mathutils import Matrix
from . import import_utils # For import_utils.SCOrg_tools_import.import_missing_materials
import xml.etree.ElementTree as ET

class SCOrg_tools_blender():
    def add_weld_and_weighted_normal_modifiers():
        for obj in bpy.data.objects:
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


    def material_matches(name):
        name = name.lower()
        return "_pom" in name or "_decal" in name

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

    def add_displace_modifiers_for_pom_and_decal(displacement_strength = 0.005):
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            mesh = obj.data

            # Skip if no materials
            if not mesh.materials:
                continue

            for mat_index, mat in enumerate(mesh.materials):
                if mat and __class__.material_matches(mat.name):
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
        for obj in bpy.data.objects:
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
                    #print(f"Removed duplicate Displace modifier '{mod_name}' from '{obj.name}'.")
                    
    def fix_modifiers(displacement_strength=0.005):
        __class__.add_weld_and_weighted_normal_modifiers()
        __class__.add_displace_modifiers_for_pom_and_decal(displacement_strength)
        __class__.remove_duplicate_displace_modifiers()
        __class__.remove_proxy_material_geometry()
        __class__.remap_material_users()
        import_utils.SCOrg_tools_import.import_missing_materials()

    def select_children(obj):
        if hasattr(obj, 'objects'):
            children = obj.objects
        else:
            children = obj.children
        for child in children:
            child.select_set(True)
            __class__.select_children(child)

    def make_instances_real(collection_name):
        print('Collection:'+collection_name)
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

        for inst in tqdm.tqdm( instances, desc="Making instances real", total=len(instances) ):
            for obj in bpy.context.selected_objects:
               obj.select_set(False)
            inst.select_set(True)
            bpy.ops.object.duplicates_make_real(
                use_base_parent=True, use_hierarchy=True
            )
        return {"FINISHED"}
        
    def get_main_collection():
        found_base_empty = None
        # Search for the base empty object in the scene
        for obj in bpy.context.scene.objects:
            if obj.type == 'EMPTY' and "container_name" in obj and obj["container_name"] == "base":
                found_base_empty = obj
                print(f"Found base empty: '{found_base_empty.name}'")
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
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            # Find all slots with a _mtl_proxy material
            slots_to_remove = []
            for i, slot in enumerate(obj.material_slots):
                mat = slot.material
                if mat and (mat.name.endswith('_mtl_proxy') or mat.name.endswith('_NoDraw')):
                    # Enter edit mode to delete geometry assigned to this material
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.object.mode_set(mode='OBJECT')
                    # Select faces with this material index
                    for poly in obj.data.polygons:
                        if poly.material_index == i:
                            poly.select = True
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.delete(type='FACE')
                    bpy.ops.object.mode_set(mode='OBJECT')
                    slots_to_remove.append(i)
            # Remove material slots (do in reverse order to avoid index shift)
            for i in sorted(slots_to_remove, reverse=True):
                obj.active_material_index = i
                bpy.ops.object.material_slot_remove()
    
    def convert_bones_to_empties(armature_obj):
        print(f"DEBUG: Converting bones to empties for armature: {armature_obj.name}")
        bpy.ops.object.mode_set(mode='OBJECT')
        armature = armature_obj.data
        empties = {}
        root_name = armature_obj.name
        if hasattr(armature_obj, 'parent') and armature_obj.parent:
            # If the armature has a parent, use its name as the root name
            root_name = armature_obj.parent.name
        print(f"DEBUG: Root name set to: {root_name} (parent found)")

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
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE':
                # convert the bones to empties
                empty_name =__class__.convert_bones_to_empties(obj)

                # Delete the armature
                name = obj.name
                bpy.data.objects.remove(obj, do_unlink=True)
                # Rename the empty to match the original armature name
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
        # Regex pattern to detect material names like "Material.001"
        suffix_pattern = re.compile(r"(.*)\.(\d{3})$")

        for mat in bpy.data.materials:
            match = suffix_pattern.match(mat.name)
            if not match:
                continue

            original = __class__.get_original_material(mat.name)
            if original is None:
                continue

            # Reassign users
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    for i, slot in enumerate(obj.material_slots):
                        if slot.material == mat:
                            slot.material = original
                            print(f"Reassigned material on {obj.name} slot {i} from {mat.name} to {original.name}")

            # Remove the duplicate material if no users left
            if mat.users == 0:
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
        print("Initializing tint group for ship: ", entity_name)
        from scdatatools import blender
        node_group = blender.materials.utils.tint_palette_node_group_for_entity(entity_name)
        return node_group
    
    def parse_unmapped_material_string(input_string):
        """
        Parses a string in the format 'something_mtl_material123' and extracts the parts.

        Args:
            input_string: The string to parse.

        Returns:
            A tuple containing the 'something_mtl' part, the material name (or 'Tintable'), and the number,
            or None if the string does not match the expected format.
        """
        pattern = r"^(.*_mtl)_(material|Tintable(?:_))(\d+)$"
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
            file_path (str): The path to the .mtl file.

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
                print(f"Warning: No 'SubMaterials' element found in {file_path}")
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
            print("Error: Could not parse .mtl file or file is empty.")
            return

        for mat in bpy.data.materials:
            prefix, material_type, number = __class__.parse_unmapped_material_string(mat.name)

            if prefix and material_type and number:
                # Material name matches the pattern
                if number in mtl_names:
                    correct_name = f"{prefix}_{mtl_names[number]}"

                    # Check if a material with the correct name already exists
                    existing_material = bpy.data.materials.get(correct_name)

                    if existing_material:
                        # Remap material users to the existing material
                        print(f"Remapping material '{mat.name}' to existing material '{correct_name}'")
                        for obj in bpy.data.objects:
                            if obj.type == 'MESH':
                                for i, slot in enumerate(obj.material_slots):
                                    if slot.material == mat:
                                        slot.material = existing_material
                                        print(f"Reassigned material on {obj.name} slot {i} from {mat.name} to {correct_name}")

                        # Remove the old material if no users left
                        if mat.users == 0:
                            print(f"Removing unused material: {mat.name}")
                            bpy.data.materials.remove(mat)

                    else:
                        # No material with the same name exists, rename the material
                        print(f"Renaming material '{mat.name}' to '{correct_name}'")
                        mat.name = correct_name