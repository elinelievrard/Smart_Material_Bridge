import os
from ...config import SP_SMART_MATERIALS, SP_EXPORT_PRESETS

CATEGORY_ICONS = {
    'Metal':             'MATERIAL',
    'Fabric':            'MOD_CLOTH',
    'Leather':           'TEXTURE',
    'Wood':              'OUTLINER_OB_POINTCLOUD',
    'Plastic - rubber':  'OVERLAY',
    'Stone':             'PROP_CON',
    'Marble - granite':  'SHADING_RENDERED',
    'Organic':           'SHADING_TEXTURE',
    'Translucent':       'KEY_RING',
    'Effect':            'PROP_CON',
}

def get_smart_materials():
    search_paths = [p for p in [
        SP_SMART_MATERIALS,
        os.path.join(os.path.expanduser("~"), "Documents", "Adobe",
                     "Adobe Substance 3D Painter", "assets", "smart-materials"),
    ] if p]

    materials = []
    seen = set()

    for base_path in search_paths:
        if not os.path.exists(base_path):
            print(f"[SMB] Path not found: {base_path}")
            continue

        for root, dirs, files in os.walk(base_path):
            for f in files:
                if f.endswith(".spsm") and f not in seen:
                    name = os.path.splitext(f)[0]
                    full_path = os.path.join(root, f)
                    materials.append((name, full_path))
                    seen.add(f)

    print(f"[SMB] Found {len(materials)} smart materials total")
    return materials


def get_smart_material_items(self, context):
    materials = get_smart_materials()
    if not materials:
        return [('NONE', 'No materials found', '', 0, 0)]

    items = []
    for i, (name, path) in enumerate(materials):
        category = os.path.basename(os.path.dirname(path))
        icon = CATEGORY_ICONS.get(category, 'MATERIAL')
        items.append((name, name, category, icon, i))

    return items


def get_export_presets():

    presets = []
    seen = set()
    base_path = SP_EXPORT_PRESETS
    if not base_path:
        return presets

    if not os.path.exists(base_path):
        print(f"[SMB] Export presets path not found: {base_path}")
        return presets

    for f in os.listdir(base_path):
        if not f.endswith(".spexp"):
            continue
        filepath = os.path.join(base_path, f)
        # Try to read the internal name from the JSON content
        internal_name = None
        try:
            import json
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            internal_name = data.get("name") or data.get("Name")
        except Exception:
            pass
        # Fall back to filename if JSON read fails
        name = internal_name if internal_name else os.path.splitext(f)[0]
        if name not in seen:
            presets.append(name)
            seen.add(name)

    presets.sort(key=lambda x: x.lower())
    print(f"[SMB] Found {len(presets)} export presets on disk")
    return presets


def get_export_preset_items(self, context):
    presets = get_export_presets()
    if not presets:
        return [("", "No export presets found", "")]
    return [(name, name, "") for name in presets]