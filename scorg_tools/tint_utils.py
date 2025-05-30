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
        print(f"Button {index} pressed: {globals_and_threading.button_labels[index]}")
        # Add your custom logic here
