import bpy
# Import globals
from . import globals_and_threading

class SCOrg_tools_tint():
    def get_tint_pallet_list(record):
        tints = []
        if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
            for i, comp in enumerate(record.properties.Components):
                if comp.name == 'SGeometryResourceParams':
                    try:
                        # Default tint first
                        guid = str(comp.properties.Geometry.properties.Geometry.properties.Palette.properties.RootRecord)
                        if guid and guid != '00000000-0000-0000-0000-000000000000':
                            tints.append(guid)
                        for subgeo in comp.properties.Geometry.properties.SubGeometry:
                            guid = str(subgeo.properties.Geometry.properties.Palette.properties.RootRecord)
                            if guid:
                                if guid != '00000000-0000-0000-0000-000000000000':
                                    tints.append(guid)
                                else:
                                    print(f"⚠️ Empty tint GUID found item {record.name}, skipping.")
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
        from . import import_utils
        print(f"Button {index} pressed: {globals_and_threading.button_labels[index]}")
        # apply the tint
        import_utils.SCOrg_tools_import.import_missing_materials(tint_number=index)
    
    def update_tints(record):
        if not record:
            print("WARNING: No record provided to update tints.")
            return False
        print(f"DEBUG: Updating tints for record: {record.name}")
        # Get tints for loaded item
        tints = __class__.get_tint_pallet_list(record)

        tint_names = []
        for i, tint_guid in enumerate(tints):
            tint_record = globals_and_threading.dcb.records_by_guid.get(tint_guid)
            if tint_record:
                tint_name = tint_record.properties.root.properties.get('name')
                if tint_name:
                    if i == 0:
                        name = f"Default Paint ({tint_name.replace('_', ' ').title()})"
                    else:
                        name = globals_and_threading.localizer.gettext(__class__.convert_paint_name(tint_name).lower())
                    tint_names.append(name)
                else:
                    print(f"WARNING: Tint record {tint_guid} missing 'name' property.")
            else:
                print(f"WARNING: Tint record not found for GUID: {tint_guid}")
        
        globals_and_threading.button_labels = tint_names