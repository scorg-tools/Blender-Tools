bl_info = {
    "name": "SCOrg.tools",
    "author": "Star-Destroyer@scorg.tools",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > SCOrg.tools",
    "description": "Tools to supplement StarFab",
    "category": "3D View"
}
bl_idname = "scorg_tools"


import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty
import os
from pathlib import Path
import tqdm
from scdatatools.sc import StarCitizen
from scdatatools.sc.localization import SCLocalization

''' ================================ TODO ================================
 - Fix paint name lookups for ships with multiple words, e.g. guardian_mx
   or do it the proper way and use the databacore to lookup the paint to 
   get the key for the localisation
 - Import the paints (tint pallets node group needs to work for this)
 - Attempt to fix hardpoints that have different names that cause some
   objects not to import, e.g. Asgard manned turret weapons
 '''

class SCOrg_tools_misc():
    bl_idname = __name__
    def get_ship_record(dcb):
        global ship_loaded
        empty_name = SCOrg_tools_misc.find_base_name()
        if empty_name:
            print(f"Found Empty object: {empty_name}")
            
            records = dcb.search_filename(f'libs/foundry/records/entities/spaceships/*{empty_name}.xml')
            if records == []:
                records = dcb.search_filename(f'libs/foundry/records/entities/groundvehicles/*{empty_name}.xml')
            if records == []:
                print("❌ Error, could not match ship or vehicle for {empty_name}")
                return None
            ship_name = localizer.gettext("vehicle_name"+empty_name.lower())
            ship_loaded = ship_name
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
        
class SCOrg_tools_tint():
    bl_idname = __name__
    def get_tint_pallet_list(record):
        tints = []
        for i, comp in enumerate(record.properties.Components):
            if comp.name == 'SGeometryResourceParams':
                try:
                    # Default tint first
                    guid = str(comp.properties.Geometry.properties.Geometry.properties.Palette.properties.RootRecord)
                    tints.append(guid)
                    for subgeo in comp.properties.Geometry.properties.SubGeometry:
                        guid = str(subgeo.properties.Geometry.properties.Palette.properties.RootRecord)
                        tints.append(guid)
                except AttributeError as e:
                    print(f"⚠️ Missing attribute accessing geometry tint pallet in component {i}: {e}")
        return tints

    def convert_paint_name(s):
        parts = s.split('_')
        if len(parts) < 2:
            return s  # or raise an error if input is invalid
        name = parts[1].capitalize()
        rest = '_'.join(parts[2:])
        return f"item_Name{name}_Paint_{rest}"

    # Function to call when a button is pressed
    def on_button_pressed(index):
        print(f"Button {index} pressed: {button_labels[index]}")
        # Add your custom logic here

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


class SCOrg_tools_import_missing_loadout():
    INCLUDE_HARDPOINTS = []
    imported_guid_objects = {}
    extract_dir = None
    
    def get_geometry_path_from_guid(dcb, guid):
        try:
            record = dcb.records_by_guid.get(str(guid))
            if not record:
                print(f"⚠️  No record found for GUID: {guid}")
                return None
            for i, comp in enumerate(record.properties.Components):
                if comp.name == 'SGeometryResourceParams':
                    try:
                        path = comp.properties.Geometry.properties.Geometry.properties.Geometry.properties.path
                        dae_path = Path(path).with_suffix('.dae')
                        return SCOrg_tools_import_missing_loadout.extract_dir / dae_path
                    except AttributeError as e:
                        print(f"⚠️ Missing attribute accessing geometry path in component {i}: {e}")
            return None
        except Exception as e:
            print(f"❌ Error processing GUID {guid}: {e}")
            return None

    def get_hardpoint_mapping_from_guid(dcb, guid):
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
            SCOrg_tools_import_missing_loadout.duplicate_hierarchy_linked(child, new_obj)

    def import_hardpoint_hierarchy(loadout, empties_to_fill, is_top_level=True):        
        entries = loadout.properties.get('entries', [])
        print(f"DEBUG: import_hardpoint_hierarchy called with {len(entries)} entries, empties to fill: {len(empties_to_fill)}, is_top_level={is_top_level}")
        for entry in entries:
            props = entry.properties
            item_port_name = props.get('itemPortName')
            guid = props.get('entityClassReference')
            nested_loadout = props.get('loadout')

            print(f"DEBUG: Processing entry '{item_port_name}' GUID {guid}")

            if not item_port_name or not guid:
                print("DEBUG: Missing item_port_name or guid, skipping")
                continue

            # Apply filter ONLY at top level
            if is_top_level and SCOrg_tools_import_missing_loadout.INCLUDE_HARDPOINTS and item_port_name not in SCOrg_tools_import_missing_loadout.INCLUDE_HARDPOINTS:
                print(f"DEBUG: Skipping '{item_port_name}' due to top-level filter")
                continue

            matching_empty = next((e for e in empties_to_fill if e.get('orig_name') == item_port_name), None)
            if not matching_empty:
                print(f"WARNING: No matching empty found for hardpoint '{item_port_name}'")
                continue

            guid_str = str(guid)
            if guid_str == '00000000-0000-0000-0000-000000000000':
                print("DEBUG: GUID is all zeros, skipping")
                continue

            if guid_str in SCOrg_tools_import_missing_loadout.imported_guid_objects:
                original_root = SCOrg_tools_import_missing_loadout.imported_guid_objects[guid_str]
                SCOrg_tools_import_missing_loadout.duplicate_hierarchy_linked(original_root, matching_empty)
                print(f"Duplicated hierarchy for '{item_port_name}' from GUID {guid_str}")
            else:
                geometry_path = SCOrg_tools_import_missing_loadout.get_geometry_path_from_guid(dcb, guid_str)
                if geometry_path is None or not geometry_path.exists():
                    print(f"ERROR: Geometry file missing for GUID {guid_str}: {geometry_path}")
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
                SCOrg_tools_import_missing_loadout.imported_guid_objects[guid_str] = root_obj

                imported_empties = [
                    obj for obj in imported_objs
                    if obj.type == 'EMPTY'
                ]

                mapping = SCOrg_tools_import_missing_loadout.get_hardpoint_mapping_from_guid(dcb, guid_str) or {}
                for empty in imported_empties:
                    if empty.name in mapping:
                        empty['orig_name'] = mapping[empty.name]

                print(f"Imported object for '{item_port_name}' GUID {guid_str} → {geometry_path}")

                # Recurse into nested loadout with is_top_level=False
                if nested_loadout:
                    entries_count = len(nested_loadout.properties.get('entries', []))
                    print(f"DEBUG: Nested loadout detected with {entries_count} entries, recursing...")
                    SCOrg_tools_import_missing_loadout.import_hardpoint_hierarchy(nested_loadout, imported_empties, is_top_level=False)
                else:
                    print("DEBUG: No nested loadout found, recursion ends here")


    def run_import():
        global dcb, sc
        os.system('cls')
        SCOrg_tools_import_missing_loadout.imported_guid_objects = {}
        SCOrg_tools_import_missing_loadout.INCLUDE_HARDPOINTS = [] # all
        SCOrg_tools_import_missing_loadout.extract_dir = bpy.context.preferences.addons["scorg_tools"].preferences.extract_dir
        
        SCOrg_tools_misc.select_base_collection() # Ensure the base collection is active before importing
        record = SCOrg_tools_misc.get_ship_record(dcb)
        top_level_loadout = record.properties.Components[1].reference.properties['loadout']

        empties_to_fill = [
            obj for obj in bpy.data.objects
            if obj.type == 'EMPTY'
            and 'orig_name' in obj.keys()
            and obj['orig_name'].startswith('hardpoint_')
        ]

        print(f"Total hardpoints to import: {len(empties_to_fill)}")

        SCOrg_tools_import_missing_loadout.import_hardpoint_hierarchy(top_level_loadout, empties_to_fill)
        SCOrg_tools_blender.fix_modifiers()





# Operator that runs when a button is clicked
class VIEW3D_OT_dynamic_button(bpy.types.Operator):
    bl_idname = "view3d.dynamic_button"
    bl_label = "Dynamic Button"

    button_index: bpy.props.IntProperty()

    def execute(self, context):
        on_button_pressed(self.button_index)
        return {'FINISHED'}

class VIEW3D_OT_refresh_button(bpy.types.Operator):
    bl_idname = "view3d.refresh_button"
    bl_label = "Check Loaded Ship"

    def execute(self, context):
        global button_labels, dcb, p4k, localizer, sc
        
        # Only load once, and not at startup
        prefs = bpy.context.preferences.addons[__name__].preferences
        if sc == None:
            p4k_path = prefs.p4k_path
            extract_dir = prefs.extract_dir
            sc = StarCitizen(p4k_path)
        if dcb == None:
            dcb = sc.datacore
        if p4k == None:
            p4k = sc.p4k
        if localizer == None:
            localizer = sc.localization 

        record = SCOrg_tools_misc.get_ship_record(dcb)
        tints = SCOrg_tools_tint.get_tint_pallet_list(record)

        tint_names = []
        for i, tint_guid in enumerate(tints):
            tint_record = dcb.records_by_guid.get(tint_guid)
            #print(dcb.dump_record_json(tint_record))
            tint_name = tint_record.properties.root.properties.name;
            if i == 0:
                name = f"Default Paint ("+tint_name.replace("_", " ").title()+")"
            else:
                name = localizer.gettext(SCOrg_tools_tint.convert_paint_name(tint_name).lower())
            tint_names.append(name)
            button_labels = tint_names
            SCOrg_tools_misc.redraw()
        return {'FINISHED'}
    
class VIEW3D_OT_import_loadout(bpy.types.Operator):
    bl_idname = "view3d.import_loadout"
    bl_label = "Import missing loadout"

    def execute(self, context):
        dir_path = Path(bpy.context.preferences.addons["scorg_tools"].preferences.extract_dir)
        if dir_path.is_dir():
            SCOrg_tools_import_missing_loadout.run_import()
        else:
            SCOrg_tools_misc.error("Error, could not find Extract Directory - set in preference");
        return {'FINISHED'}

class VIEW3D_OT_add_modifiers(bpy.types.Operator):
    bl_idname = "view3d.add_modifiers"
    bl_label = "Add modifiers"

    def execute(self, context):
        SCOrg_tools_blender.fix_modifiers()
        return {'FINISHED'}

class VIEW3D_OT_make_instance_real(bpy.types.Operator):
    bl_idname = "view3d.make_instance_real"
    bl_label = "Add modifiers"

    def execute(self, context):
        SCOrg_tools_blender.run_make_instances_real()
        return {'FINISHED'}

# Panel in the sidebar
class VIEW3D_PT_scorg_tools_panel(bpy.types.Panel):
    bl_label = "SCOrg.tools Blender utils"
    bl_idname = "VIEW3D_PT_scorg_tools_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SCOrg.tools"
    bl_parent_id = "VIEW3D_PT_BlenderLink_Panel"

    def draw(self, context):
        global ship_loaded, p4k
        layout = self.layout
        if 'StarFab' in bpy.data.scenes:
            layout.operator("view3d.make_instance_real", text="Make Instance Real", icon='OUTLINER_OB_GROUP_INSTANCE')
        else:
            if p4k == None:
                prefix = "Load data.p4k & "
            else:
                prefix = ""
            layout.operator("view3d.refresh_button", text=prefix+"Check Loaded Ship", icon='FILE_REFRESH')
            extract_dir = bpy.context.preferences.addons["scorg_tools"].preferences.extract_dir
            dir_path = Path(extract_dir)
            if dir_path.is_dir() != True or extract_dir == "":
                layout.label(text="To import loadout, set Extract Directory in Preferences", icon='ERROR')
            if ship_loaded == None:
                layout.label(text="Click Check to find ship", icon='ERROR')
            else:
                layout.label(text=ship_loaded, icon='CHECKBOX_HLT')
                layout.separator()
                if dir_path.is_dir() == True and extract_dir != "":
                    layout.operator("view3d.import_loadout", text="Import missing loadout", icon='IMPORT')
                layout.separator()
                layout.label(text="Paints")
                for idx, label in enumerate(button_labels):
                    op = layout.operator("view3d.dynamic_button", text=label)
                    op.button_index = idx
            layout.label(text="Utilities")
            layout.operator("view3d.add_modifiers", text="Add modifiers", icon='MODIFIER')


class SCOrg_tools_OT_SelectP4K(bpy.types.Operator):
    bl_idname = "scorg_tools.select_p4k"
    bl_label = "Select .p4k File"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(
        default="*.p4k",
        options={'HIDDEN'}
    )

    def execute(self, context):
        prefs = context.preferences.addons["scorg_tools"].preferences
        prefs.p4k_path = self.filepath
        self.report({'INFO'}, f"Selected: {self.filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
class SCOrg_tools_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    p4k_path: bpy.props.StringProperty(
        name="P4K File Path",
        description="Path to SC Data.p4k file",
        subtype='FILE_PATH',
        default=r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Data.p4k",
    )

    extract_dir: bpy.props.StringProperty(
        name="Extract Directory",
        description="Directory where extracted files are stored",
        subtype='DIR_PATH',
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="SCOrg.tools Settings")
        layout.label(text=f"Current P4K: {self.p4k_path}")
        layout.operator("scorg_tools.select_p4k", text="Select .p4k File")

        if self.p4k_path and not self.p4k_path.lower().endswith(".p4k"):
            layout.label(text="Warning: Not a .p4k file", icon='ERROR')
        layout.prop(self, "extract_dir")
        if self.extract_dir:
            abs_chosen_dir = os.path.abspath(bpy.path.abspath(self.extract_dir))
            objects_dir = os.path.join(abs_chosen_dir, "Objects")
            if not os.path.isdir(objects_dir):
                layout.label(text=f"Directory '{objects_dir}' not found. This doesn't appear to be the correct folder.", icon='ERROR')


# Register and unregister
classes = (
    VIEW3D_OT_refresh_button,
    VIEW3D_OT_import_loadout,
    VIEW3D_OT_make_instance_real,
    VIEW3D_OT_add_modifiers,
    VIEW3D_OT_dynamic_button,
    VIEW3D_PT_scorg_tools_panel,
    SCOrg_tools_AddonPreferences,
    SCOrg_tools_OT_SelectP4K,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

dcb = None
p4k = None
button_labels = []
ship_loaded = None
sc = None
localizer = None

if __name__ == "__main__":
    register()