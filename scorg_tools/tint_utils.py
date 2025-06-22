import bpy
# Import globals
from . import globals_and_threading

class SCOrg_tools_tint():
    def get_tint_pallet_list(record):
        tints = {}
        if hasattr(record, 'properties') and hasattr(record.properties, 'Components'):
            for i, comp in enumerate(record.properties.Components):
                if comp.name == 'SGeometryResourceParams':
                    try:
                        # Default tint first
                        guid = str(comp.properties.Geometry.properties.Geometry.properties.Palette.properties.RootRecord)
                        if guid and guid != '00000000-0000-0000-0000-000000000000':
                            if globals_and_threading.debug:
                                print(f"DEBUG: Found default tint GUID {guid} in component {i} for item {record.name}")
                            tints[guid] = record.name.replace('_', ' ').title()
                        for subgeo in comp.properties.Geometry.properties.SubGeometry:
                            guid = str(subgeo.properties.Geometry.properties.Palette.properties.RootRecord)
                            tags = subgeo.properties.Tags
                            if globals_and_threading.debug:
                                print(f"DEBUG: Checking subgeometry {i} for item {record.name}, GUID: {guid}, Tags: {tags}")
                            # Check if the subgeometry has a tint GUID
                            if guid:
                                if guid != '00000000-0000-0000-0000-000000000000':
                                    if globals_and_threading.debug:
                                        print(f"DEBUG: Found tint GUID {guid} in subgeometry of component {i} for item {record.name}")
                                    # check to see if the record for the guid exists before adding it to the list
                                    if globals_and_threading.dcb.records_by_guid.get(guid):
                                        tints[guid] = __class__.get_paint_name_by_tag(tags) if tags else f"Tint {len(tints) + 1}"
                                    else:
                                        if globals_and_threading.debug:
                                            print(f"DEBUG: tint with GUID {guid} not found in records, skipping.")
                                else:
                                    print(f"⚠️ Empty tint GUID found item {record.name}, skipping.")
                    except AttributeError as e:
                        print(f"⚠️ Missing attribute accessing geometry tint pallet in component {i}: {e}")
        return tints

    # Function to call when a button is pressed
    def on_button_pressed(index):
        from . import import_utils
        print(f"Button {index} pressed: {index}")
        # apply the tint
        import_utils.SCOrg_tools_import.import_missing_materials(tint_number=index)
    
    def update_tints(record):
        if not record:
            print("WARNING: No record provided to update tints.")
            return False
        print(f"DEBUG: Updating tints for record: {record.name}")
        # Get tints for loaded item
        tints = __class__.get_tint_pallet_list(record)
        if globals_and_threading.debug:
            print(f"DEBUG: Found {len(tints)} tints for item {record.name}: {tints}")
        
        globals_and_threading.button_labels = tints.values() if isinstance(tints, dict) else list(tints)

    def get_paint_name_by_tag(tag):
        """Get the localized name of a paint by its tag."""
        if not tag or not isinstance(tag, str):
            return "Unknown Paint"
            
        original_tag = tag  # Keep the original for fallback formatting
        
        try:
            # Validate globals
            if not globals_and_threading.dcb or not globals_and_threading.localizer:
                return original_tag.replace('_', ' ').title()
            
            # Clean and format tag for file search
            search_tag = tag.strip().lower()
            if not search_tag.startswith('paint_'):
                search_tag = 'paint_' + search_tag
            
            # Search for paint file
            filename = f"libs/foundry/records/entities/scitem/ships/paints/{search_tag}.xml"
            search_results = globals_and_threading.dcb.search_filename(filename)
            if not search_results:
                return original_tag.replace('_', ' ').title()
            
            # Navigate to localization name with compact path
            record = search_results[0]
            locale_name = record.properties.Components[0].properties.AttachDef.properties.Localization.properties.Name
            
            # Clean and localize
            if locale_name:
                clean_locale_name = locale_name.lstrip('@')
                localized_name = globals_and_threading.localizer.gettext(clean_locale_name)
                
                # Check if localization succeeded (didn't just return the key back)
                if localized_name and localized_name != clean_locale_name and not localized_name.startswith('item_name'):
                    return localized_name
            
            # Fallback to formatted original tag name
            return original_tag.replace('_', ' ').title()
            
        except (IndexError, AttributeError, KeyError, TypeError):
            return original_tag.replace('_', ' ').title()