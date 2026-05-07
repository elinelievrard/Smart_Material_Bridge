import os
import substance_painter.project as sp_project
import substance_painter.textureset as ts
import substance_painter.event as sp_event
from load_working_dir import load_working_dir

from .baking import setup_baking, start_baking
from .exporting import export_textures
from .cleanup import cleanup_files, finish_or_continue


def start_plugin():
    sp_event.DISPATCHER.connect_strong(sp_event.ShelfCrawlingEnded, on_shelf_ready)


def on_shelf_ready(event):
    sp_event.DISPATCHER.disconnect(sp_event.ShelfCrawlingEnded, on_shelf_ready)

    working_dir = load_working_dir()
    if not working_dir:
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
        print("[SP] No pairs found")
        return

    print(f"[SP] Found {len(pairs)} pairs")
    process_next(pairs, working_dir, 0)


def process_next(pairs, working_dir, index):
    if index >= len(pairs):
        print("[SP] DONE ALL")
        return

    name, low_path, high_path = pairs[index]
    print(f"[SP] Processing {name}")

    def after_project_ready():
        print("[SP] Project fully loaded!")

        texture_sets = ts.all_texture_sets()
        print(f"[SP] Texture sets: {texture_sets}")
        if not texture_sets:
            print("[SP] No texture sets found")
            return

        setup_baking(texture_sets, high_path)

        def do_export_and_continue():
            export_textures(texture_sets, working_dir)
            cleanup_files(low_path, high_path, name)          # ← only once now
            sp_project.close()
            finish_or_continue(pairs, working_dir, index, process_next)  # ← only once now

        def on_bake_end(event):
            sp_event.DISPATCHER.disconnect(sp_event.BakingProcessEnded, on_bake_end)
            print("[SP] Bake finished")
            sp_project.execute_when_not_busy(do_export_and_continue)

        sp_event.DISPATCHER.connect_strong(sp_event.BakingProcessEnded, on_bake_end)
        sp_project.execute_when_not_busy(lambda: start_baking(texture_sets))

    sp_project.create(mesh_file_path=low_path)
    sp_project.execute_when_not_busy(after_project_ready)


def close_plugin():
    pass