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

_pipeline_started = False  # Guard to prevent pipeline from running multiple times


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP: Called when SP opens (smb_bridge_startup.py triggers this)
# ─────────────────────────────────────────────────────────────────────────────
def start_plugin():
    global _pipeline_started
    _pipeline_started = False
    # Wait for SP's shelf (materials library) to fully load before starting
    sp_event.DISPATCHER.connect_strong(sp_event.ShelfCrawlingEnded, on_shelf_ready)


def on_shelf_ready(event):
    # Shelf is ready, so we can search for smart materials now
    global _pipeline_started
    sp_event.DISPATCHER.disconnect(sp_event.ShelfCrawlingEnded, on_shelf_ready)
    if _pipeline_started:
        return  # Already running, prevent double-execution
    _pipeline_started = True
    # execute_when_not_busy waits for SP to finish initializing before starting the pipeline
    sp_project.execute_when_not_busy(_run_pipeline)


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INITIALIZATION: Load config and find mesh pairs
# ─────────────────────────────────────────────────────────────────────────────
def _run_pipeline():
    # Load bake_config.json written by Blender
    result = load_working_dir()
    if result is None:
        return

    working_dir, color_mapping, texture_out, projects_folder, size_log2, export_preset, delete_fbx_after, use_low_as_high = result

    if not working_dir:
        print("[SP] No working dir in config - nothing to do.")
        return

    # Find all _low.fbx/_high.fbx pairs in the working directory
    files = os.listdir(working_dir)
    pairs = []
    for f in files:
        if f.endswith("_low.fbx"):
            prefix = f.replace("_low.fbx", "")
            hp = f"{prefix}_high.fbx"
            if hp in files:
                # Store as: (name, low_path, high_path)
                pairs.append((
                    prefix,
                    os.path.join(working_dir, f),
                    os.path.join(working_dir, hp)
                ))

    if not pairs:
        print("[SP] No _low/_high pairs found in working dir")
        return

    print(f"[SP] Found {len(pairs)} pairs")
    # Start processing the first pair
    process_next(
        pairs, working_dir,
        color_mapping, texture_out, projects_folder,
        size_log2, export_preset, delete_fbx_after,
        use_low_as_high=use_low_as_high,
        index=0
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONTINUATION LOGIC: After each pair finishes, move to the next or close SP
# ─────────────────────────────────────────────────────────────────────────────
def finish_or_continue(pairs, working_dir, index, process_next_fn, close_sp=True):
    # If there are more pairs, process the next one
    if index + 1 < len(pairs):
        process_next_fn(pairs, working_dir, index + 1)
    else:
        # All pairs processed
        if close_sp:
            print("[SP] All done, closing Substance Painter...")
            sp_project.execute_when_not_busy(sp_app.close)
        else:
            print("[SP] All done, keeping Substance Painter open.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROCESSING: For each mesh pair, create project → bake → apply materials → export
# ─────────────────────────────────────────────────────────────────────────────
def process_next(pairs, working_dir, color_mapping, texture_out, projects_folder,
                 size_log2, export_preset, delete_fbx_after, index, use_low_as_high=False):
    # Sanity check: index out of bounds
    if index >= len(pairs):
        print("[SP] DONE ALL")
        return

    name, low_path, high_path = pairs[index]
    print(f"[SP] Processing {name}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: Create new project from the low poly mesh
    # ─────────────────────────────────────────────────────────────────────────
    def _create_project():
        # Connect to ProjectEditionEntered BEFORE calling create()
        # (ProjectCreated fires too early, before we can access texture sets)
        # ProjectEditionEntered = guaranteed fully-loaded and ready to work with
        def on_edition_entered(event):
            sp_event.DISPATCHER.disconnect(sp_event.ProjectEditionEntered, on_edition_entered)
            print("[SP] Project edition entered — fully ready to work with")
            after_project_ready()

        sp_event.DISPATCHER.connect_strong(sp_event.ProjectEditionEntered, on_edition_entered)
        sp_project.create(mesh_file_path=low_path)

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: Setup baking and apply smart materials
    # ─────────────────────────────────────────────────────────────────────────
    def after_project_ready():
        print("[SP] Setting up baking...")
        texture_sets = sp_textureset.all_texture_sets()
        if not texture_sets:
            print("[SP] No texture sets found")
            return

        # Configure bakers (normal, AO, ID, etc.) with correct high poly mesh
        setup_baking(texture_sets, high_path, use_low_as_high=use_low_as_high)

        # ─────────────────────────────────────────────────────────────────────
        # STEP 3: After baking completes, apply smart materials and export
        # ─────────────────────────────────────────────────────────────────────
        def _do_export():
            # Guard: project might have closed between baking and export
            if not sp_project.is_open():
                print("[SP] Project no longer open at export time — aborting")
                return

            current_texture_sets = sp_textureset.all_texture_sets()
            if not current_texture_sets:
                print("[SP] No texture sets at export time — aborting")
                return

            if texture_out:
                # Export textures using the preset
                try:
                    export_textures(
                        current_texture_sets, texture_out, projects_folder,
                        name, size_log2, export_preset
                    )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[SP] Export failed for '{name}': {e}")
            else:
                # No texture export, just save the project file
                if projects_folder:
                    try:
                        os.makedirs(projects_folder, exist_ok=True)
                        spp_path = os.path.join(projects_folder, f"{name}.spp")
                        sp_project.save_as(spp_path)
                    except Exception as e:
                        print(f"[SP] Could not save project: {e}")

            # Clean up FBX folder if user didn't want FBX export
            cleanup_files(working_dir, delete_fbx_after)

            # Move to the next pair or close SP
            finish_or_continue(
                pairs, working_dir, index,
                lambda p, w, i: process_next(
                    p, w, color_mapping,
                    texture_out, projects_folder,
                    size_log2, export_preset,
                    delete_fbx_after, i,
                    use_low_as_high=use_low_as_high
                ),
                close_sp=True
            )

        def do_export_and_continue():
            # Apply smart materials using the baked ID map as a mask
            if color_mapping:
                apply_smart_materials(texture_sets, color_mapping)

            # Wait for SP to be idle before exporting (ensures materials are applied)
            sp_project.execute_when_not_busy(_do_export)

        # ─────────────────────────────────────────────────────────────────────
        # STEP 2.5: Start baking and wait for it to finish
        # ─────────────────────────────────────────────────────────────────────
        def on_bake_end(event):
            # Baking finished, now apply smart materials and export
            sp_event.DISPATCHER.disconnect(sp_event.BakingProcessEnded, on_bake_end)
            print(f"[SP] Bake finished with status: {event.status}")
            # Wait for SP to be fully idle before proceeding
            sp_project.execute_when_not_busy(do_export_and_continue)

        # Connect to baking completion event, then start baking
        sp_event.DISPATCHER.connect_strong(sp_event.BakingProcessEnded, on_bake_end)
        sp_project.execute_when_not_busy(lambda: start_baking(texture_sets))

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 0: Close any existing project, then create a new one
    # ─────────────────────────────────────────────────────────────────────────
    if sp_project.is_open():
        # Close current, then create new (both in one execute_when_not_busy call)
        sp_project.execute_when_not_busy(lambda: (sp_project.close(), _create_project()))
    else:
        _create_project()


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY: Color conversion for smart material masking
# ─────────────────────────────────────────────────────────────────────────────
def hex_to_rgb(hex_str):
    # Convert "#808080" → (0.502, 0.502, 0.502) in 0-1 range
    hex_str = hex_str.lstrip('#')
    r, g, b = (int(hex_str[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b)


# ─────────────────────────────────────────────────────────────────────────────
# SMART MATERIALS: Apply each color's material to the ID map
# ─────────────────────────────────────────────────────────────────────────────
def apply_smart_materials(texture_sets, color_mapping):
    # color_mapping = {"0.5,0.0,0.0": "Metal_Rusty", "0.0,0.5,0.0": "Fabric_Cotton", ...}
    print(f"[SP] Applying smart materials: {color_mapping}")
    for tset in texture_sets:
        print(f"[SP] Processing texture set: {tset.name()}")
        # Get the baked ID map (identifies vertex colors by pixel color)
        id_map = tset.get_mesh_map_resource(MeshMapUsage.ID)
        if id_map is None:
            print("[SP] No ID map available, cannot mask by color")
            return
        sp_textureset.set_active_stack(tset.get_stack())
        # Apply each smart material to its corresponding color
        for color_key, material_name in color_mapping.items():
            if material_name == 'NONE':
                continue
            apply_single_smart_material(tset, color_key, material_name, id_map)


def apply_single_smart_material(tset, color_key, material_name, id_map):
    print(f"[SP] Applying '{material_name}' for color key {color_key}")
    try:
        # Parse "r,g,b" string (Blender's raw linear values from 0-1 range)
        parts = color_key.split(",")
        r, g, b = float(parts[0]), float(parts[1]), float(parts[2])

        # Search SP's resource library for the smart material by name
        results = [res for res in sp_resource.search(material_name)
                   if res.type() == sp_resource.Type.SMART_MATERIAL]
        if not results:
            print(f"[SP] Smart material not found: {material_name}")
            return

        # Insert the smart material into the layer stack
        smart_mat = results[0]
        stack = tset.get_stack()
        position = sp_layerstack.InsertPosition.from_textureset_stack(stack)
        layer_node = sp_layerstack.insert_smart_material(position, smart_mat.identifier())
        # Add a black mask (everything masked out initially, then revealed by color selection)
        layer_node.add_mask(sp_layerstack.MaskBackground.Black)

        # Create a Color Selection effect inside the mask to unmask only the target color
        mask_position = sp_layerstack.InsertPosition.inside_node(
            layer_node, sp_layerstack.NodeStack.Mask
        )
        color_effect = sp_layerstack.insert_color_selection_effect(mask_position)

        # Configure the color selection to match the target color from the ID map
        params = sp_layerstack.ColorSelectionEffectParams(
            id_mask=id_map,  # Use the ID map as the source texture
            output_value=1.0,  # Full opacity for matching colors
            hardness=1.0,  # Sharp selection edge
            tolerance=0.15,  # Allow slight variation in color (0-1 range)
            background_color=sp_layerstack.ColorSelectionBackgroundColor.Black,
            # Raw = no color space conversion (matches how SP stores baked ID data)
            colors=[sp_colormanagement.Color(r, g, b, sp_colormanagement.GenericColorSpace.Raw)]
        )
        color_effect.set_parameters(params)
        print(f"[SP] Applied '{material_name}' with Raw color ({r:.4f}, {g:.4f}, {b:.4f})")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SP] Failed to apply smart material: {e}")


def close_plugin():
    # Called when SP closes (cleanup hook, currently unused)
    pass