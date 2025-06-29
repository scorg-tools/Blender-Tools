import bpy
import re
# Import globals
from . import globals_and_threading
from . import misc_utils

class SCOrg_tools_tint():
    paint_records = None

    def get_tint_pallet_list(record):
        __class__.get_paint_records()  # Ensure paint records are loaded
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
                        else:
                            name = record.name.lower() # e.g. "misc_starlancer_max"
                            # get the manufacturer name from the first part of the name
                            man = name.split('_')[0]
                            # search dcb for a default paint record, e.g. "misc_starlancer_max_default"
                            # Loop through the name parts, removing the last part each time until we find a match or we reach 2 parts
                            while len(name.split('_')) >= 2:
                                if globals_and_threading.debug: print(f"DEBUG: Searching for default paint record for {name} in component {i}")
                                # Check if the paint record exists in the dcb
                                results = globals_and_threading.dcb.search_filename(f"libs/foundry/records/tintpalettes/brand/{man}/*{name}_default.xml")
                                if results:
                                    # If we find a record, use it as the default paint
                                    tint_guid = results[0].id.value
                                    tint_name = results[0].name
                                    if globals_and_threading.debug: print(f"DEBUG: Found default paint record for {name}: {guid} ({tint_name})")
                                    tints[tint_guid] = tint_name.replace('_', ' ').title()
                                    break
                                # Remove the last part of the name and try again, e.g. "misc_starlancer_default"
                                name = '_'.join(name.split('_')[:-1])
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
        # Clear progress when done
        misc_utils.SCOrg_tools_misc.clear_progress()

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

    def clean_paint_tag(tag):
        """Clean and format a paint tag for display."""
        # Replace underscores with spaces, strip
        cleaned_tag = tag.replace('_', ' ').strip()
        # Add spaces between CamelCase words
        cleaned_tag = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', cleaned_tag)
        # Capitalize Each Word
        return cleaned_tag.title()
    
    def get_paint_name_by_tag(tag):
        """Get the localized name of a paint by its tag."""
        if not tag or not isinstance(tag, str):
            return "Unknown Paint"
            
        original_tag = tag  # Keep the original for fallback formatting
        
        try:
            # Validate globals
            if not globals_and_threading.dcb or not globals_and_threading.localizer:
                return __class__.clean_paint_tag(original_tag)
            
            # Clean and format tag for file search
            search_tag = tag.strip().lower()
            if not search_tag.startswith('paint_'):
                search_tag = 'paint_' + search_tag
            
            # Search for paint file
            if search_tag in __class__.paint_records.keys():
                record = __class__.paint_records[search_tag]
            else:
                return __class__.clean_paint_tag(original_tag)
            
            # Navigate to localization name with compact path
            locale_name = record.properties.Components[0].properties.AttachDef.properties.Localization.properties.Name
            
            # Clean and localize
            if locale_name:
                clean_locale_name = locale_name.lstrip('@')
                localized_name = globals_and_threading.localizer.gettext(clean_locale_name)
                
                # Check if localization succeeded (didn't just return the key back)
                if localized_name and localized_name != clean_locale_name and not localized_name.startswith('item_name'):
                    return localized_name
            
            # Fallback to formatted original tag name
            return __class__.clean_paint_tag(original_tag)
            
        except (IndexError, AttributeError, KeyError, TypeError):
            return __class__.clean_paint_tag(original_tag)
    
    def get_paint_records():
        # Retrieve paint records from the database, caching them for future use.
        if __class__.paint_records is None:
            filename = f"libs/foundry/records/entities/scitem/ships/paints/*.xml"
            search_results = globals_and_threading.dcb.search_filename(filename)
            # loop through the search results and display the components -> SAttachableComponentParams -> tags
            paint_records = {}
            for paint in search_results:
                tags = paint.properties.Components[0].properties.AttachDef.properties.Tags
                # split tags by @ and get the second part
                tag = tags.split('@')[1].strip().lower() if '@' in tags else None
                paint_records[tag] = paint
            __class__.paint_records = paint_records
        return __class__.paint_records
    
    def get_applied_tint():
        """
        Get the currently applied tint for the active ship or item.
        Returns the GUID of the applied tint or None if no tint is applied.
        """
        if globals_and_threading.ship_loaded:
            # Get base empty from import_utils since it has the function
            from . import import_utils
            base_empty = import_utils.SCOrg_tools_import.get_base_empty()
            if base_empty:
                tint_guid = base_empty.get("Applied_Tint", None)
                return tint_guid
        return None
    
    def get_applied_tint_number():
        """
        Get the index of the currently applied tint for the active ship or item.
        Returns the index of the applied tint or None if no tint is applied.
        """
        tint_guid = __class__.get_applied_tint()
        if tint_guid:
            # Get the current ship/item record to get the tint list
            from . import misc_utils
            record = misc_utils.SCOrg_tools_misc.get_ship_record(skip_error=True)
            if record:
                tints = __class__.get_tint_pallet_list(record)
                # Get list of tint GUIDs in the same order as button labels
                tint_guids = list(tints.keys()) if isinstance(tints, dict) else []
                
                try:
                    # Find the index of the applied tint GUID
                    index = tint_guids.index(tint_guid)
                    if globals_and_threading.debug:
                        print(f"DEBUG: Applied tint GUID {tint_guid} found at index {index}")
                    return index
                except ValueError:
                    if globals_and_threading.debug:
                        print(f"DEBUG: Applied tint GUID {tint_guid} not found in current tint list")
                    return None
        return None