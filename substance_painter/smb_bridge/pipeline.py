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

_pipeline_started = False


def start_plugin():
    global _pipeline_started
    _pipeline_started = False
    sp_event.DISPATCHER.connect_strong(sp_event.ShelfCrawlingEnded, on_shelf_ready)


def on_shelf_ready(event):
    global _pipeline_started
    sp_event.DISPATCHER.disconnect(sp_event.ShelfCrawlingEnded, on_shelf_ready)
    if _pipeline_started:
        return
    _pipeline_started = True
    # Let SP fully settle before starting the pipeline
    sp_project.execute_when_not_busy(_run_pipeline)


def _run_pipeline():
    result = load_working_dir()
    if result is None:
        return

    working_dir, color_mapping, texture_out, projects_folder, size_log2, export_preset, delete_fbx_after, use_low_as_high = result

    if not working_dir:
        print("[SP] No working dir in config - nothing to do.")
        return

    files = os.listdir(working_dir)
    pairs = []
    for f in files:
        if f.endswith("_low.fbx"):
            prefix = f.replace("_low.fbx", "")
            hp = f"{prefix}_high.fbx"
            if hp in files:
                pairs.append((
                    prefix,
                    os.path.join(working_dir, f),
                    os.path.join(working_dir, hp)
                ))

    if not pairs:
        print("[SP] No _low/_high pairs found in working dir")
        return

    print(f"[SP] Found {len(pairs)} pairs")
    process_next(
        pairs, working_dir,
        color_mapping, texture_out, projects_folder,
        size_log2, export_preset, delete_fbx_after,
        use_low_as_high=use_low_as_high,
        index=0
    )


def finish_or_continue(pairs, working_dir, index, process_next_fn, close_sp=True):
    if index + 1 < len(pairs):
        process_next_fn(pairs, working_dir, index + 1)
    else:
        if close_sp:
            print("[SP] All done, closing Substance Painter...")
            sp_project.execute_when_not_busy(sp_app.close)
        else:
            print("[SP] All done, keeping Substance Painter open.")


def process_next(pairs, working_dir, color_mapping, texture_out, projects_folder,
                 size_log2, export_preset, delete_fbx_after, index, use_low_as_high=False):
    if index >= len(pairs):
        print("[SP] DONE ALL")
        return

    name, low_path, high_path = pairs[index]
    print(f"[SP] Processing {name}")

    def _create_project():
        # Connect to ProjectEditionEntered BEFORE calling create()
        # so we never miss the event even on very fast machines
        # ProjectEditionEntered is the guaranteed signal that the project
        # is fully loaded and ready — ProjectCreated fires too early
        def on_edition_entered(event):
            sp_event.DISPATCHER.disconnect(sp_event.ProjectEditionEntered, on_edition_entered)
            print("[SP] Project edition entered — fully ready to work with")
            after_project_ready()

        sp_event.DISPATCHER.connect_strong(sp_event.ProjectEditionEntered, on_edition_entered)
        sp_project.create(mesh_file_path=low_path)

    def after_project_ready():
        print("[SP] Setting up baking...")
        texture_sets = sp_textureset.all_texture_sets()
        if not texture_sets:
            print("[SP] No texture sets found")
            return

        setup_baking(texture_sets, high_path, use_low_as_high=use_low_as_high)

        def _do_export():
            if not sp_project.is_open():
                print("[SP] Project no longer open at export time — aborting")
                return

            current_texture_sets = sp_textureset.all_texture_sets()
            if not current_texture_sets:
                print("[SP] No texture sets at export time — aborting")
                return

            if texture_out:
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
                if projects_folder:
                    try:
                        os.makedirs(projects_folder, exist_ok=True)
                        spp_path = os.path.join(projects_folder, f"{name}.spp")
                        sp_project.save_as(spp_path)
                    except Exception as e:
                        print(f"[SP] Could not save project: {e}")

            cleanup_files(working_dir, delete_fbx_after)
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
            if color_mapping:
                apply_smart_materials(texture_sets, color_mapping)

            # Use execute_when_not_busy directly — simpler and more reliable
            # than BusyStatusChanged which fires for unrelated internal SP operations
            # Add the project check inside _do_export to catch the case where
            # SP closes the project between smart material insertion and export
            sp_project.execute_when_not_busy(_do_export)

        def on_bake_end(event):
            sp_event.DISPATCHER.disconnect(sp_event.BakingProcessEnded, on_bake_end)
            print(f"[SP] Bake finished with status: {event.status}")
            # execute_when_not_busy here confirms SP is fully idle after baking
            # before we start applying smart materials or exporting
            sp_project.execute_when_not_busy(do_export_and_continue)

        sp_event.DISPATCHER.connect_strong(sp_event.BakingProcessEnded, on_bake_end)
        sp_project.execute_when_not_busy(lambda: start_baking(texture_sets))

    if sp_project.is_open():
        sp_project.execute_when_not_busy(lambda: (sp_project.close(), _create_project()))
    else:
        _create_project()


def hex_to_rgb(hex_str):
    # "#808080"
    # (0.5019607843137255, 0.5019607843137255, 0.5019607843137255)
    hex_str = hex_str.lstrip('#')
    r, g, b = (int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b)


def apply_smart_materials(texture_sets, color_mapping):
    print(f"[SP] Applying smart materials: {color_mapping}")
    for tset in texture_sets:
        print(f"[SP] Processing texture set: {tset.name()}")
        id_map = tset.get_mesh_map_resource(MeshMapUsage.ID)
        if id_map is None:
            print("[SP] No ID map available, cannot mask by color")
            return
        sp_textureset.set_active_stack(tset.get_stack())
        for color_key, material_name in color_mapping.items():
            if material_name == 'NONE':
                continue
            apply_single_smart_material(tset, color_key, material_name, id_map)


def apply_single_smart_material(tset, color_key, material_name, id_map):
    print(f"[SP] Applying '{material_name}' for color key {color_key}")
    try:
        # Parse the "r,g,b" float string — these are Blender's raw linear values
        parts = color_key.split(",")
        r, g, b = float(parts[0]), float(parts[1]), float(parts[2])

        results = [res for res in sp_resource.search(material_name)
                   if res.type() == sp_resource.Type.SMART_MATERIAL]
        if not results:
            print(f"[SP] Smart material not found: {material_name}")
            return

        smart_mat = results[0]
        stack = tset.get_stack()
        position = sp_layerstack.InsertPosition.from_textureset_stack(stack)
        layer_node = sp_layerstack.insert_smart_material(position, smart_mat.identifier())
        layer_node.add_mask(sp_layerstack.MaskBackground.Black)

        mask_position = sp_layerstack.InsertPosition.inside_node(
            layer_node, sp_layerstack.NodeStack.Mask
        )
        color_effect = sp_layerstack.insert_color_selection_effect(mask_position)

        params = sp_layerstack.ColorSelectionEffectParams(
            id_mask=id_map,
            output_value=1.0,
            hardness=1.0,
            tolerance=0.15,
            background_color=sp_layerstack.ColorSelectionBackgroundColor.Black,
            # Raw = no color space conversion — matches how SP stores the baked ID map data
            colors=[sp_colormanagement.Color(r, g, b, sp_colormanagement.GenericColorSpace.Raw)]
        )
        color_effect.set_parameters(params)
        print(f"[SP] Applied '{material_name}' with Raw color ({r:.4f}, {g:.4f}, {b:.4f})")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SP] Failed to apply smart material: {e}")


def close_plugin():
    pass