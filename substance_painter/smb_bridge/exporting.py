import substance_painter.export as sp_export
import substance_painter.project as sp_project
import os


def _resolve_preset_url(preset_name):
    for p in sp_export.list_predefined_export_presets():
        if p.name == preset_name:
            return p.url

    for r in sp_export.list_resource_export_presets():
        if r.resource_id.name == preset_name:
            return r.resource_id.url()

    # Debug: log what's actually available so you can spot name mismatches
    predefined = [p.name for p in sp_export.list_predefined_export_presets()]
    resource = [r.resource_id.name for r in sp_export.list_resource_export_presets()]
    print(f"[SP] Available predefined presets: {predefined}")
    print(f"[SP] Available resource presets: {resource}")

    return None


def export_textures(texture_sets, texture_out, projects_folder, name, size_log2=11, export_preset=""):
    os.makedirs(texture_out, exist_ok=True)

    if not export_preset:
        print("[SP] No export preset name provided, aborting export")
        return None

    preset_url = _resolve_preset_url(export_preset)

    if not preset_url:
        raise ValueError(
            f"Export preset '{export_preset}' not found in this SP session. "
            f"Try re-fetching presets from Blender."
        )

    print(f"[SP] Using export preset URL: '{preset_url}'")

    export_config = {
        "exportPath": texture_out,
        "exportShaderParams": False,
        "defaultExportPreset": preset_url,
        "exportList": [
            {"rootPath": tset.name()}
            for tset in texture_sets
        ],
        "exportParameters": [
            {
                "parameters": {
                    "sizeLog2": size_log2,
                    "paddingAlgorithm": "infinite",
                    "dilationDistance": 16,
                }
            }
        ]
    }

    result = sp_export.export_project_textures(export_config)

    print(f"[SP] Export status: {result.status}")
    print(f"[SP] Exported files: {result.textures}")

    if projects_folder:
        os.makedirs(projects_folder, exist_ok=True)
        spp_path = os.path.join(projects_folder, f"{name}.spp")
        sp_project.save_as(spp_path)
        print(f"[SP] Project saved: {spp_path}")

    return result