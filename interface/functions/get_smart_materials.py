import os
from ...config import SP_SMART_MATERIALS, SP_EXPORT_PRESETS

CATEGORY_ICONS = {
    'Metal': 'MATERIAL',
    'Fabric': 'MOD_CLOTH',
    'Leather': 'TEXTURE',
    'Wood': 'OUTLINER_OB_POINTCLOUD',
    'Plastic - rubber': 'OVERLAY',
    'Stone': 'PROP_CON',
    'Marble - granite': 'SHADING_RENDERED',
    'Organic': 'SHADING_TEXTURE',
    'Translucent': 'KEY_RING',
    'Effect': 'PROP_CON',
}


def get_smart_materials():
    # STEP 1: Build search paths
    # Substance Painter can be installed in different locations depending on the system:
    # 1. Program Files (official default install location)
    # 2. Documents/Adobe (user custom location or cloud sync)
    #
    # We create a list of both potential paths, but filter out None values
    # (None occurs when SP isn't installed, or the path doesn't exist in config)
    #
    # Example:
    #   SP_SMART_MATERIALS = "C:\Program Files\Adobe\Adobe Substance 3D Painter\resources\starter_assets\smart-materials"
    #   User path = "C:\Users\username\Documents\Adobe\Adobe Substance 3D Painter\assets\smart-materials"
    #
    # The `if p` filter removes None entries so we don't try to walk() a None path
    search_paths = [p for p in [
        SP_SMART_MATERIALS,
        os.path.join(os.path.expanduser("~"), "Documents", "Adobe",
                     "Adobe Substance 3D Painter", "assets", "smart-materials"),
    ] if p]

    materials = []  # List to store (material_name, full_path_to_file) tuples
    seen = set()  # Set to track filenames we've already added (prevents duplicates)

    # STEP 2: Walk through each search path and find all .spsm files
    for base_path in search_paths:
        # Guard: Check if this path actually exists on disk before trying to access it
        # If SP is installed to Program Files but the user's Documents path doesn't exist, skip it
        if not os.path.exists(base_path):
            print(f"[SMB] Path not found: {base_path}")
            continue

        # os.walk() recursively traverses all subdirectories
        # It yields (directory, subdirectories, files) tuples at each level
        #
        # Example structure:
        #   smart-materials/
        #       Metal/
        #           Metal_Rusty.spsm
        #           Metal_Polished.spsm
        #       Fabric/
        #           Fabric_Cotton.spsm
        #           Fabric_Wool.spsm
        #
        # os.walk handles all this nesting automatically without hardcoding paths
        for root, dirs, files in os.walk(base_path):
            # root = current directory being walked
            # dirs = subdirectories in root
            # files = files in root (not including subdirs)

            for f in files:
                # STEP 3: Filter for .spsm files and avoid duplicates
                # Only process files that:
                # 1. End with ".spsm" (Substance Painter smart material format)
                # 2. Haven't been seen before (f not in seen)
                #
                # Why check "not in seen"?
                # → If the user has smart materials in both Program Files AND Documents,
                #   and they have the same filename (e.g., "Metal_Rusty.spsm"),
                #   we only want to use the first one found.
                # → This prevents confusing the user with duplicate entries in the dropdown
                if f.endswith(".spsm") and f not in seen:
                    # Strip the .spsm extension to get the display name
                    # "Metal_Rusty.spsm" → "Metal_Rusty"
                    name = os.path.splitext(f)[0]

                    # Build the full path to the file
                    # root = "C:\Program Files\Adobe\...\smart-materials\Metal"
                    # f = "Metal_Rusty.spsm"
                    # full_path = "C:\Program Files\Adobe\...\smart-materials\Metal\Metal_Rusty.spsm"
                    full_path = os.path.join(root, f)

                    # Store as a tuple: (display_name, full_path_to_use_later)
                    # We need the full path so Substance Painter can load the material
                    materials.append((name, full_path))

                    # Mark this filename as seen so we don't add it again
                    # if we encounter it in a different search path
                    seen.add(f)

    # STEP 4: Return results
    # Print summary for debugging
    # Example output: "[SMB] Found 127 smart materials total"
    print(f"[SMB] Found {len(materials)} smart materials total")

    # Return list of tuples: [(name, path), (name, path), ...]
    return materials


def get_smart_material_items(self, context):
    # STEP 1: Get all smart materials from disk
    # This function is called by Blender whenever the UI dropdown needs to populate
    # (e.g., when you open the Smart Material dropdown menu)
    # It must return a list in Blender's EnumProperty format
    materials = get_smart_materials()

    # STEP 2: Graceful fallback if no materials found
    # If Substance Painter isn't installed or no .spsm files exist, show helpful message
    # Blender format: (identifier, label, description, icon_code, index)
    if not materials:
        return [('NONE', 'No materials found', '', 0, 0)]

    items = []  # Will build this into Blender EnumProperty format

    # STEP 3: Convert to Blender UI format
    # Blender's EnumProperty requires items in this format:
    #   (identifier, label, description, icon, index)
    #
    # Example:
    #   ("Metal_Rusty", "Metal_Rusty", "Metal", 'MATERIAL', 0)
    #   ↑identifier    ↑label          ↑description ↑icon    ↑index
    #
    # - identifier: What gets stored internally (used in code)
    # - label: What the user sees in the dropdown
    # - description: Tooltip or category hint (shown on hover)
    # - icon: Icon to display next to the label
    # - index: Numerical position in the list

    for i, (name, path) in enumerate(materials):
        # Extract the category from the file path
        # path = "C:\...\smart-materials\Metal\Metal_Rusty.spsm"
        # os.path.dirname(path) = "C:\...\smart-materials\Metal"
        # os.path.basename(...) = "Metal"
        #
        # This tells us the material's category without parsing the filename
        category = os.path.basename(os.path.dirname(path))

        # Look up the appropriate icon for this category
        # CATEGORY_ICONS = {'Metal': 'MATERIAL', 'Fabric': 'MOD_CLOTH', ...}
        # If the category isn't in our dictionary, default to 'MATERIAL'
        #
        # Why use category-specific icons?
        # → Visual feedback: Users see a metal icon for metal materials, cloth icon for fabric, etc.
        # → Better UX: Easier to scan the dropdown list and find what you need
        icon = CATEGORY_ICONS.get(category, 'MATERIAL')

        # Build the Blender enum item
        # Format: (identifier, label, description/tooltip, icon, index)
        # - We use `name` for both identifier and label (what user sees and what gets stored)
        # - Category goes in the description slot (appears as tooltip on hover)
        # - Icon comes from the category lookup above
        # - Index is just the position in the list
        items.append((name, name, category, icon, i))

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4: Return formatted list
    # ─────────────────────────────────────────────────────────────────────────
    # Blender now has a list it can render as a dropdown menu:
    #
    # Example output:
    #   [
    #     ("Metal_Rusty", "Metal_Rusty", "Metal", 'MATERIAL', 0),
    #     ("Metal_Polished", "Metal_Polished", "Metal", 'MATERIAL', 1),
    #     ("Fabric_Cotton", "Fabric_Cotton", "Fabric", 'MOD_CLOTH', 2),
    #     ("Fabric_Wool", "Fabric_Wool", "Fabric", 'MOD_CLOTH', 3),
    #   ]
    return items


def get_export_presets():
    # ─────────────────────────────────────────────────────────────────────────
    # SIMILAR PATTERN: Find all export preset files (.spexp)
    # ─────────────────────────────────────────────────────────────────────────
    # Export presets control what textures SP exports and how they're packed
    # (e.g., "PBR Metallic Roughness" exports separate BaseColor, Roughness, Metallic PNGs)
    # vs a packed preset like "Unreal Engine 4" which combines multiple channels

    presets = []  # List of preset names to return
    seen = set()  # Track filenames to avoid duplicates (same as get_smart_materials)

    base_path = SP_EXPORT_PRESETS
    # SP_EXPORT_PRESETS is set in config.py based on where SP is installed
    # Example: "C:\Program Files\Adobe\...\resources\starter_assets\export-presets"

    if not base_path:
        # SP not installed or config couldn't find it
        return presets

    if not os.path.exists(base_path):
        # The presets folder doesn't exist (corrupt install?)
        print(f"[SMB] Export presets path not found: {base_path}")
        return presets

    # Read all .spexp files
    # Unlike smart materials (which nest in subdirs), presets are flat in one folder
    for f in os.listdir(base_path):
        if not f.endswith(".spexp"):
            # Only process .spexp files (Substance Painter export preset format)
            continue

        filepath = os.path.join(base_path, f)

        # Try to read the internal name from the preset file
        # .spexp files are JSON, and they contain a "name" or "Name" field
        # This is the display name the user sees in Substance Painter
        #
        # Example .spexp file content:
        #   {
        #     "name": "PBR Metallic Roughness",
        #     "exportList": [...]
        #   }
        internal_name = None
        try:
            import json
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Check for "name" or "Name" key (case variation in different SP versions)
            internal_name = data.get("name") or data.get("Name")
        except Exception:
            # JSON parsing failed (corrupted file, wrong format, etc.)
            # We'll fall back to using the filename instead
            pass

        # Use internal name if available, otherwise use the filename
        # Example fallback:
        #   filename = "PBR_Metallic_Roughness.spexp"
        #   name = "PBR Metallic Roughness"  (from JSON)
        #   OR
        #   name = "PBR_Metallic_Roughness"  (if JSON parsing failed)
        name = internal_name if internal_name else os.path.splitext(f)[0]

        if name not in seen:
            presets.append(name)
            seen.add(name)

    # Sort alphabetically for a cleaner dropdown
    presets.sort(key=lambda x: x.lower())

    print(f"[SMB] Found {len(presets)} export presets on disk")
    return presets


def get_export_preset_items(self, context):
    # Convert export presets to Blender EnumProperty format
    # Same pattern as get_smart_material_items, but simpler:
    # - No categories or icons
    # - Just (name, name, "") tuples

    presets = get_export_presets()

    if not presets:
        # No presets found (SP not installed)
        return [("", "No export presets found", "")]

    # Create enum items: (identifier, label, description)
    # We use the preset name for both identifier and label
    return [(name, name, "") for name in presets]