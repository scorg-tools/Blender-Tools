import bpy
import tqdm

# Import globals
from . import globals_and_threading
from . import misc_utils # For SCOrg_tools_misc.select_children, get_main_collection

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
                print(f"Added Weld modifier to {obj.name}")

            # Check if Weighted Normal modifier already exists
            has_weighted_normal = any(mod.type == 'WEIGHTED_NORMAL' for mod in obj.modifiers)
            if not has_weighted_normal:
                wn = obj.modifiers.new(name="WeightedNormal", type='WEIGHTED_NORMAL')
                wn.mode = 'FACE_AREA'
                wn.weight = 50
                wn.keep_sharp = True
                wn.thresh = 0.01  # Corrected attribute name
                print(f"Added Weighted Normal modifier to {obj.name}")


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

    def add_displace_modifiers_for_pom_and_decal():
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            mesh = obj.data

            # Skip if no materials
            if not mesh.materials:
                continue

            for mat_index, mat in enumerate(mesh.materials):
                if mat and SCOrg_tools_blender.material_matches(mat.name):
                    group_name = mat.name
                    vg = SCOrg_tools_blender.ensure_vertex_group(obj, mat_index, group_name)

                    # 1) Check if a Displace modifier for this vertex group already exists
                    modifier_exists = False
                    for mod in obj.modifiers:
                        if mod.type == 'DISPLACE' and mod.vertex_group == vg.name:
                            print(f"Displace modifier for {obj.name} using group '{vg.name}' already exists. Skipping.")
                            modifier_exists = True
                            break

                    if not modifier_exists:
                        # Create displace modifier
                        mod = obj.modifiers.new(name=f"Displace_{group_name}", type='DISPLACE')
                        mod.strength = 0.005
                        mod.mid_level = 0
                        mod.vertex_group = vg.name
                        print(f"Added Displace modifier for {obj.name} using group '{vg.name}'")

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
                        print(f"Marked duplicate Displace modifier '{mod.name}' from '{obj.name}' for vertex group '{mod.vertex_group}' for removal.")
            
            # Now, remove the marked modifiers by name.
            # Iterate in reverse when removing, to ensure indices don't shift unexpectedly
            # as we remove items from the object's modifiers collection.
            for mod_name in reversed(modifier_names_to_remove):
                if mod_name in obj.modifiers: # Check if it still exists (e.g., not manually removed)
                    obj.modifiers.remove(obj.modifiers[mod_name])
                    print(f"Removed duplicate Displace modifier '{mod_name}' from '{obj.name}'.")
                    
    def fix_modifiers():
        SCOrg_tools_blender.add_weld_and_weighted_normal_modifiers()
        SCOrg_tools_blender.add_displace_modifiers_for_pom_and_decal()
        SCOrg_tools_blender.remove_duplicate_displace_modifiers()

    def select_children(obj):
        if hasattr(obj, 'objects'):
            children = obj.objects
        else:
            children = obj.children
        for child in children:
            child.select_set(True)
            SCOrg_tools_blender.select_children(child)

    def make_instances_real(collection_name):
        print('Collection:'+collection_name)
        SCOrg_tools_blender.select_children(bpy.data.collections[collection_name])
        roots = [ _ for _ in bpy.context.selected_objects if _.instance_collection is not None ]
        instances = set()
        for root in roots:
            if root.instance_collection is None:
                continue  # we may have already made it real from another root
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            SCOrg_tools_blender.select_children(root)
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
        collection = SCOrg_tools_blender.get_main_collection()
        collection_name = collection.name
        bpy.ops.object.select_all(action='DESELECT') # Deselect all objects for a clean slate
        # Make instance real so we can remove the StarFab collection and save data
        SCOrg_tools_blender.make_instances_real(collection_name)
        # Remove the StarFab collection
        if bpy.data.scenes.find('StarFab') >= 0:
            bpy.data.scenes.remove(bpy.data.scenes['StarFab'])
        
        # Tidy up orphan data to save space
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        
        # Move the collection
        # unlink from the scene collection
        bpy.data.scenes['Scene'].collection.children.unlink(bpy.data.collections[collection_name])
        # link to the Collection collection
        bpy.data.collections['Collection'].children.link(bpy.data.collections[collection_name])

    def fix_bright_lights():
        for obj in bpy.data.objects:
            if obj.type == "LIGHT" and obj.data.energy > 30000:
                obj.data.energy /= 1000