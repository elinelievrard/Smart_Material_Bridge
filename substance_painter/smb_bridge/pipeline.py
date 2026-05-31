import os
import substance_painter.project as sp_project
import substance_painter.textureset as sp_textureset
import substance_painter.event as sp_event
import substance_painter.resource as sp_resource
import substance_painter.layerstack as sp_layerstack
from substance_painter.baking import MeshMapUsage
import substance_painter.colormanagement as sp_colormanagement
import substance_painter.application as sp_app

from .load_working_dir import load_working_dir
from .baking import setup_baking, start_baking
from .exporting import export_textures
from .cleanup import cleanup_files

# Global flag that prevents the pipeline from running twice
# if SP fires ShelfCrawlingEnded more than once in one session
# False = pipeline hasn't run yet,  True = already running, ignore any duplicate events
_pipeline_started = False


def start_plugin():
    # Called by smb_bridge_startup.py when SP loads this file on startup
    # Resets the flag so a fresh bake always starts clean
    global _pipeline_started
    _pipeline_started = False

    # sp_event.DISPATCHER is SP's global event bus — all SP events flow through it
    # connect_strong keeps the connection alive even if nothing else holds a reference to on_shelf_ready
    # ShelfCrawlingEnded fires when SP has finished scanning and loading all its assets/smart materials
    # We wait for this before doing anything because smart materials aren't searchable until the shelf is ready
    sp_event.DISPATCHER.connect_strong(sp_event.ShelfCrawlingEnded, on_shelf_ready)


def on_shelf_ready(event):
    # SP's asset shelf is now fully loaded — smart materials are searchable from here on
    global _pipeline_started

    # Disconnect immediately so this function never runs twice in the same session
    sp_event.DISPATCHER.disconnect(sp_event.ShelfCrawlingEnded, on_shelf_ready)

    if _pipeline_started:
        # Safety net: if somehow ShelfCrawlingEnded fired twice, ignore the second one
        print("[SP] Pipeline already started, ignoring duplicate ShelfCrawlingEnded")
        return
    _pipeline_started = True

    _run_pipeline()


def _run_pipeline():
    # Reads bake_config.json that Blender wrote before launching SP
    # result is a tuple of 7 values, or None if the config is missing/stale
    result = load_working_dir()
    if result is None:
        return

    # Unpack all 7 values from the config
    # working_dir     = "C:\Users\eline\MyBakeFolder\chair\fbx"
    # color_mapping   = {"#FF0000": "Metal_Rusty", "#00FF00": "Fabric_Cotton"}  or  {}
    # texture_out     = "C:\Users\eline\MyBakeFolder\chair\textures"  or  ""
    # projects_folder = "C:\Users\eline\MyBakeFolder\chair\projects"  or  ""
    # size_log2       = 11  (for 2048px)
    # export_preset   = "PBR Metallic Roughness"  or  ""
    # delete_fbx_after = True / False
    working_dir, color_mapping, texture_out, projects_folder, size_log2, export_preset, delete_fbx_after = result

    if not working_dir:
        print("[SP] No working dir in config - nothing to do.")
        return

    # Scan the fbx folder for _low/_high file pairs
    # files = ["Chair_low.fbx", "Chair_high.fbx", "Cube_low.fbx", "Cube_high.fbx"]
    files = os.listdir(working_dir)
    pairs = []
    for f in files:
        if f.endswith("_low.fbx"):
            # f = "Chair_low.fbx"
            # prefix = "Chair"
            prefix = f.replace("_low.fbx", "")
            # hp = "Chair_high.fbx"
            hp = f"{prefix}_high.fbx"
            if hp in files:
                pairs.append((
                    prefix,                                  # "Chair"
                    os.path.join(working_dir, f),            # "...\fbx\Chair_low.fbx"
                    os.path.join(working_dir, hp)            # "...\fbx\Chair_high.fbx"
                ))
    # pairs = [("Chair", "...\Chair_low.fbx", "...\Chair_high.fbx"),
    #          ("Cube",  "...\Cube_low.fbx",  "...\Cube_high.fbx")]

    if not pairs:
        print("[SP] No _low/_high pairs found in working dir")
        return

    print(f"[SP] Found {len(pairs)} pairs")

    # Start processing from index 0 — process_next handles one pair at a time
    # and calls itself recursively for the next index when each pair is done
    process_next(
        pairs, working_dir,
        color_mapping, texture_out, projects_folder,
        size_log2, export_preset, delete_fbx_after,
        index=0
    )

def finish_or_continue(pairs, working_dir, index, process_next_fn, close_sp=True):
    if index + 1 < len(pairs):
        # There are more pairs after this one — move to the next index
        # e.g. index=0, len=2 -> process index 1 next
        process_next_fn(pairs, working_dir, index + 1)
    else:
        # This was the last pair — all done
        if close_sp:
            print("[SP] All done, closing Substance Painter...")
            # execute_when_not_busy queues the close call until SP has finished
            # any ongoing operations — safer than calling sp_app.close() directly
            sp_project.execute_when_not_busy(sp_app.close)
        else:
            print("[SP] All done, keeping Substance Painter open.")


def process_next(pairs, working_dir, color_mapping, texture_out, projects_folder,
                 size_log2, export_preset, delete_fbx_after, index):
    if index >= len(pairs):
        print("[SP] DONE ALL")
        return

    # e.g. index=0
    # name     = "Chair"
    # low_path = "C:\Users\eline\MyBakeFolder\chair\fbx\Chair_low.fbx"
    # high_path = "C:\Users\eline\MyBakeFolder\chair\fbx\Chair_high.fbx"
    name, low_path, high_path = pairs[index]
    print(f"[SP] Processing {name}")

    def _create_project():
        # Opens a new SP project using the low poly FBX as the mesh
        # This is what you'd normally do manually: File -> New -> pick mesh
        sp_project.create(mesh_file_path=low_path)
        # Queue after_project_ready to run once SP has fully loaded the project
        # execute_when_not_busy is needed because create() returns before the project is actually ready
        sp_project.execute_when_not_busy(after_project_ready)

    def after_project_ready():
        # SP project is fully loaded and safe to work with from here
        print("[SP] Project fully loaded!")

        # texture_sets = all texture sets in the project
        # A texture set = one UV island group / material slot in the mesh
        # e.g. [<TextureSet "Chair_low">]  — usually one per mesh unless you have multiple UDIMs/materials
        texture_sets = sp_textureset.all_texture_sets()
        if not texture_sets:
            print("[SP] No texture sets found")
            return

        # Configures what maps to bake (Normal, AO, ID, Curvature etc.)
        # and sets the high poly mesh path for each texture set
        setup_baking(texture_sets, high_path)

        def do_export_and_continue():
            # Runs after the bake is finished (called from on_bake_end below)

            if color_mapping:
                # color_mapping = {"#FF0000": "Metal_Rusty", "#00FF00": "Fabric_Cotton"}
                # Reads the baked ID map and assigns smart materials per color region
                apply_smart_materials(texture_sets, color_mapping)

            if texture_out:
                # texture_out = "C:\Users\eline\MyBakeFolder\chair\textures"
                # Exports BaseColor, Roughness, Metallic, Normal etc. as PNGs
                # Also saves the .spp project file if projects_folder is set
                try:
                    export_textures(
                        texture_sets, texture_out, projects_folder,
                        name, size_log2, export_preset
                    )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[SP] Export failed for '{name}': {e}")
                    print("[SP] Continuing despite export error...")
            else:
                # texture_out is "" — user only wanted the .spp project, not textures
                print("[SP] No texture_out set - skipping texture export.")
                if projects_folder:
                    try:
                        os.makedirs(projects_folder, exist_ok=True)
                        # spp_path = "C:\Users\eline\MyBakeFolder\chair\projects\Chair.spp"
                        spp_path = os.path.join(projects_folder, f"{name}.spp")
                        sp_project.save_as(spp_path)
                        print(f"[SP] Project saved: {spp_path}")
                    except Exception as e:
                        print(f"[SP] Could not save project: {e}")

            # Delete or keep the fbx/ folder depending on user's Export FBX setting
            cleanup_files(working_dir, delete_fbx_after)

            # Move on to the next pair, or close SP if this was the last one
            finish_or_continue(
                pairs, working_dir, index,
                lambda p, w, i: process_next(
                    p, w, color_mapping,
                    texture_out, projects_folder,
                    size_log2, export_preset,
                    delete_fbx_after, i
                ),
                close_sp=True
            )

        def on_bake_end(event):
            # SP fires BakingProcessEnded when all bakers have finished
            # Disconnect immediately so this doesn't trigger again if baking runs a second time
            sp_event.DISPATCHER.disconnect(sp_event.BakingProcessEnded, on_bake_end)
            print("[SP] Bake finished")
            # Queue export — don't call it directly in the event handler
            # because SP may still be busy finalizing bake results
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: sp_project.execute_when_not_busy(do_export_and_continue))

        # Register the bake-end listener before starting the bake
        # so we don't miss the event if baking finishes very fast
        sp_event.DISPATCHER.connect_strong(sp_event.BakingProcessEnded, on_bake_end)

        # Queue the bake start — don't call start_baking() directly
        # because we need SP to be idle before kicking off a bake
        sp_project.execute_when_not_busy(lambda: start_baking(texture_sets))

    # If a project is already open from a previous pair, close it first then open the new one
    # If nothing is open yet, go straight to creating the project
    if sp_project.is_open():
        # Close the current project then immediately create the next one
        # The lambda chains both calls: close() runs, then _create_project() runs
        sp_project.execute_when_not_busy(lambda: (sp_project.close(), _create_project()))
    else:
        _create_project()


def hex_to_rgb(hex_str):
    # Converts a hex color string to a 0.0-1.0 RGB tuple for SP's color API
    # "#FF0000" -> (1.0, 0.0, 0.0)
    # "#333333" -> (0.2, 0.2, 0.2)
    hex_str = hex_str.lstrip('#')   # "FF0000"
    # int("FF", 16) = 255,  255 / 255.0 = 1.0
    # int("00", 16) = 0,    0   / 255.0 = 0.0
    r, g, b = (int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b)


def apply_smart_materials(texture_sets, color_mapping):
    # color_mapping = {"#FF0000": "Metal_Rusty", "#00FF00": "Fabric_Cotton"}
    print(f"[SP] Applying smart materials: {color_mapping}")
    for tset in texture_sets:
        print(f"[SP] Processing texture set: {tset.name()}")

        # The ID map was baked from vertex colors — it's what we use to mask each material
        # get_mesh_map_resource returns the baked ID map resource, or None if baking didn't produce one
        id_map = tset.get_mesh_map_resource(MeshMapUsage.ID)
        if id_map is None:
            print("[SP] No ID map available, cannot mask by color")
            return

        # Make this texture set the active one so layer operations target it
        sp_textureset.set_active_stack(tset.get_stack())

        for hex_color, material_name in color_mapping.items():
            # hex_color     = "#FF0000"
            # material_name = "Metal_Rusty"
            if material_name == 'NONE':
                continue
            apply_single_smart_material(tset, hex_color, material_name, id_map)


def apply_single_smart_material(tset, hex_color, material_name, id_map):
    # hex_color     = "#FF0000"
    # material_name = "Metal_Rusty"
    print(f"[SP] Applying '{material_name}' for color {hex_color}")
    try:
        # Search SP's asset library for the smart material by name
        # sp_resource.search returns all matching resources across all types
        # we filter to only Type.SMART_MATERIAL to avoid false matches on textures/brushes etc.
        # results = [<Resource "Metal_Rusty">]  or  []  if not found
        results = [r for r in sp_resource.search(material_name)
                   if r.type() == sp_resource.Type.SMART_MATERIAL]
        if not results:
            print(f"[SP] Smart material not found: {material_name}")
            return

        # Take the first match — names should be unique in SP's library
        smart_mat = results[0]

        # stack = the layer stack of this texture set (where all layers/materials live)
        stack = tset.get_stack()

        # InsertPosition.from_textureset_stack puts the new layer at the top of the stack
        position = sp_layerstack.InsertPosition.from_textureset_stack(stack)

        # Adds the smart material as a new layer at that position
        # layer_node = the new layer node we just inserted
        layer_node = sp_layerstack.insert_smart_material(position, smart_mat.identifier())

        # Add a black mask to the layer — black means fully hidden by default
        # We then punch holes in the mask using the color selection effect below
        # so only the polygons with the matching vertex color show this material
        layer_node.add_mask(sp_layerstack.MaskBackground.Black)

        # InsertPosition.inside_node targets the mask stack of this layer specifically
        mask_position = sp_layerstack.InsertPosition.inside_node(
            layer_node, sp_layerstack.NodeStack.Mask
        )

        # Adds a Color Selection effect into the mask
        # This effect reads the ID map and outputs white (visible) wherever the color matches
        color_effect = sp_layerstack.insert_color_selection_effect(mask_position)

        # "#FF0000" -> (1.0, 0.0, 0.0)
        r, g, b = hex_to_rgb(hex_color)

        # Configure the color selection effect parameters
        params = sp_layerstack.ColorSelectionEffectParams(
            id_mask=id_map,          # which baked map to sample colors from
            output_value=1.0,        # output white (fully visible) where color matches
            hardness=1.0,            # hard edge, no feathering between color regions
            tolerance=0.5,           # how closely the sampled color must match — 0.5 gives some leeway for compression artifacts
            background_color=sp_layerstack.ColorSelectionBackgroundColor.Black,  # everything else stays masked
            colors=[sp_colormanagement.Color(r, g, b)]  # the specific color to select
        )
        color_effect.set_parameters(params)

        print(f"[SP] Applied '{material_name}' with mask for {hex_color}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SP] Failed to apply smart material: {e}")


def close_plugin():
    pass