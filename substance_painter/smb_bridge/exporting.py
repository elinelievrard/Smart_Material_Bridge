import substance_painter.export as sp_export
import substance_painter.project as sp_project
import os


def _resolve_preset_url(preset_name):
    # SP has two separate lists of export presets:
    # 1. Predefined presets — built into SP itself e.g. "PBR Metallic Roughness", "Unity HD Render Pipeline"
    # 2. Resource presets   — custom .spexp files loaded from disk (the ones SMB copies from SP's starter assets)
    # We check both because the preset the user picked in Blender could be in either list

    # list_predefined_export_presets() returns a list of preset objects
    # each has a .name (display name) and a .url (internal SP resource URL)
    # e.g. p.name = "PBR Metallic Roughness"
    #      p.url  = "substance-painter://export/PBR Metallic Roughness"
    for p in sp_export.list_predefined_export_presets():
        if p.name == preset_name:
            return p.url

    # list_resource_export_presets() returns resource objects — slightly different structure
    # r.resource_id.name = "Unreal Engine 4"
    # r.resource_id.url() = "substance-painter://resource/..."
    for r in sp_export.list_resource_export_presets():
        if r.resource_id.name == preset_name:
            return r.resource_id.url()

    # Neither list had a match — log what's actually available so you can spot the mismatch
    # e.g. predefined = ["PBR Metallic Roughness", "Unity HD Render Pipeline", ...]
    #      resource   = ["Unreal Engine 4 (Packed)", "Custom_Preset", ...]
    predefined = [p.name for p in sp_export.list_predefined_export_presets()]
    resource = [r.resource_id.name for r in sp_export.list_resource_export_presets()]
    print(f"[SP] Available predefined presets: {predefined}")
    print(f"[SP] Available resource presets: {resource}")

    # Return None to signal the caller that the preset wasn't found
    return None


def export_textures(texture_sets, texture_out, projects_folder, name, size_log2=11, export_preset=""):
    # texture_out     = "C:\Users\eline\MyBakeFolder\chair\textures"
    # projects_folder = "C:\Users\eline\MyBakeFolder\chair\projects"  or  ""
    # name            = "Chair"  (used as the .spp filename)
    # size_log2       = 11  (2048px),  12 = 4096px,  9 = 512px
    # export_preset   = "PBR Metallic Roughness"
    os.makedirs(texture_out, exist_ok=True)

    if not export_preset:
        print("[SP] No export preset name provided, aborting export")
        return None

    # Look up the internal SP URL for the preset name the user picked in Blender
    # preset_url = "substance-painter://export/PBR Metallic Roughness"  or  None
    preset_url = _resolve_preset_url(export_preset)

    if not preset_url:
        # Raise so pipeline.py catches it and logs the error without crashing SP
        raise ValueError(
            f"Export preset '{export_preset}' not found in this SP session. "
            f"Try re-fetching presets from Blender."
        )

    print(f"[SP] Using export preset URL: '{preset_url}'")

    # export_config is the dict SP's export API expects
    # it controls where files go, which preset to use, which texture sets to export, and at what size
    export_config = {
        # Root output folder — all exported PNGs land here
        # "C:\Users\eline\MyBakeFolder\chair\textures"
        "exportPath": texture_out,

        # False = don't export shader-specific parameters (we only want texture maps)
        "exportShaderParams": False,

        # The preset URL tells SP what channels to export and how to pack them
        # e.g. "PBR Metallic Roughness" exports separate BaseColor, Roughness, Metallic, Normal PNGs
        # a packed preset like "Unreal Engine 4" would pack Roughness+Metallic+AO into one texture
        "defaultExportPreset": preset_url,

        # exportList tells SP which texture sets to include
        # rootPath = the texture set name, e.g. "Chair_low"
        # one entry per texture set — if you had multiple UDIMs you'd have multiple entries
        "exportList": [
            {"rootPath": tset.name()}
            for tset in texture_sets
        ],
        # e.g. [{"rootPath": "Chair_low"}]

        # exportParameters sets technical options for the export
        "exportParameters": [
            {
                "parameters": {
                    # sizeLog2 = 11 -> 2^11 = 2048px output textures
                    "sizeLog2": size_log2,

                    # paddingAlgorithm "infinite" fills empty UV space by extending
                    # the edge pixels outward — prevents dark seams on UV borders
                    "paddingAlgorithm": "infinite",

                    # dilationDistance = how many pixels of padding to apply around UV islands
                    # 16px is a safe value for most texture sizes — prevents seams at mip levels
                    "dilationDistance": 16,
                }
            }
        ]
    }

    # Run the export — this writes the PNG files to texture_out
    # result.status = ExportStatus.Success  or  ExportStatus.Error
    # result.textures = {"Chair_low": ["...\Chair_low_BaseColor.png", "...\Chair_low_Normal.png", ...]}
    result = sp_export.export_project_textures(export_config)

    print(f"[SP] Export status: {result.status}")
    print(f"[SP] Exported files: {result.textures}")

    if projects_folder:
        # Save the SP project as a .spp file so the user can re-open it later
        # spp_path = "C:\Users\eline\MyBakeFolder\chair\projects\Chair.spp"
        os.makedirs(projects_folder, exist_ok=True)
        spp_path = os.path.join(projects_folder, f"{name}.spp")
        # save_as writes a full copy of the project to the given path
        # unlike save() which overwrites the current file (there may not be one if we never saved before)
        sp_project.save_as(spp_path)
        print(f"[SP] Project saved: {spp_path}")

    return result