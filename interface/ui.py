import bpy
import os

# Resolution options for texture export (2^9 to 2^13 pixels)
RESOLUTION_ITEMS = [
    ('512', '512', ''),
    ('1024', '1024', ''),
    ('2048', '2048', ''),
    ('4096', '4096', ''),
    ('8192', '8192', ''),
]

# Map resolution strings to log2 values for Substance Painter API
# (SP uses log2 internally: 2^11 = 2048px)
RESOLUTION_TO_LOG2 = {
    '512': 9,
    '1024': 10,
    '2048': 11,
    '4096': 12,
    '8192': 13,
}

class OBJECT_PT_bake_panel(bpy.types.Panel):
    # UI panel that appears in the 3D viewport's "SMB" tab
    bl_label = "Smart Material Bridge"
    bl_idname = "OBJECT_PT_bake_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SMB'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ─────────────────────────────────────────────────────────────────────
        # BAKE FOLDER SECTION
        # ─────────────────────────────────────────────────────────────────────
        row = layout.row(align=True)
        row.prop(scene, "bake_base_folder", text="Bake Folder")
        row.operator("smb.reset_bake_folder", text="", icon='FILE_REFRESH')
        layout.prop(scene, "smb_bake_folder_name", text="Bake Name")

        # Warn if folder name already exists (will auto-increment)
        raw_name = scene.smb_bake_folder_name.strip()

        if raw_name and not scene.smb_overwrite_bake:
            # Sanitize the folder name: spaces→underscores, remove special chars
            clean_name = "_".join(raw_name.split())
            clean_name = "".join(c for c in clean_name if c.isalnum() or c in "_-")
            existing_path = os.path.join(scene.bake_base_folder, clean_name)
            if os.path.exists(existing_path):
                # Calculate what the actual folder name will be (clean_name_1, clean_name_2, etc.)
                i = 1
                while os.path.exists(os.path.join(scene.bake_base_folder, f"{clean_name}_{i}")):
                    i += 1
                new_name = f"{clean_name}_{i}"
                box = layout.box()
                box.label(
                    text=f"Folder already exists — will be saved as '{new_name}'",
                    icon='INFO'
                )

        # ─────────────────────────────────────────────────────────────────────
        # EXPORT SETTINGS
        # ─────────────────────────────────────────────────────────────────────
        layout.prop(scene, "smb_resolution", text="Resolution")

        col = layout.column(align=True)
        col.prop(scene, "smb_export_fbx")
        col.prop(scene, "smb_save_blend")

        # "Export SP Project" only enabled if FBX is also enabled
        row = col.row(align=True)
        row.enabled = scene.smb_export_fbx
        row.prop(scene, "smb_export_project")

        col.prop(scene, "smb_export_textures")

        # Helper: is project export actually happening?
        effective_project_export = scene.smb_export_project and scene.smb_export_fbx

        # Guard: must export at least something
        if (
                not scene.smb_export_fbx and
                not effective_project_export and
                not scene.smb_export_textures
        ):
            layout.separator()
            box = layout.box()
            box.alert = True
            box.label(text="Nothing can be exported.", icon='ERROR')
            box.label(text="Enable at least one export option.")
            return  # Exit early, don't draw rest of panel

        # Show export preset dropdown only if textures will be exported
        if scene.smb_export_textures:
            row = col.row(align=True)
            row.prop(scene, "smb_export_preset", text="Preset")

        # ─────────────────────────────────────────────────────────────────────
        # OVERWRITE SECTION
        # ─────────────────────────────────────────────────────────────────────
        layout.separator()
        layout.prop(scene, "smb_overwrite_bake")

        if scene.smb_overwrite_bake:
            box = layout.box()
            overwrite_col = box.column(align=True)

            row = overwrite_col.row(align=True)
            row.prop(scene, "smb_overwrite_folder", text="")
            row.operator("smb.refresh_overwrite_folder", text="", icon='FILE_REFRESH')

            overwrite = scene.smb_overwrite_folder.strip()
            base = scene.bake_base_folder.strip()

            overwrite_col.separator()

            # Show status/instructions based on selection
            if not overwrite:
                has_subfolders = False
                if base and os.path.exists(base):
                    has_subfolders = any(
                        os.path.isdir(os.path.join(base, d))
                        for d in os.listdir(base)
                    )
                if has_subfolders:
                    overwrite_col.label(text="Pick a folder to overwrite.", icon='INFO')
                else:
                    overwrite_col.label(text="Nothing to overwrite.", icon='INFO')
            else:
                # Validate the overwrite path is safe and valid
                norm_overwrite = os.path.normpath(overwrite)
                norm_base = os.path.normpath(base)

                if not os.path.exists(norm_overwrite):
                    overwrite_col.label(text="Folder no longer exists — pick again.", icon='CANCEL')
                elif norm_overwrite == norm_base:
                    # Guard: prevent accidentally nuking the root bake folder
                    overwrite_col.label(text="Cannot overwrite the root Bake Folder.", icon='CANCEL')
                elif not norm_overwrite.startswith(norm_base + os.sep):
                    # Guard: folder must be inside the base, not a random path elsewhere
                    overwrite_col.label(text="Must be inside the Bake Folder!", icon='CANCEL')
                else:
                    # All valid, show confirmation
                    overwrite_col.label(
                        text=f"Will overwrite: {os.path.basename(norm_overwrite)}",
                        icon='ERROR'
                    )
                    overwrite_col.label(text="Bake Name is ignored when overwriting.", icon='INFO')

        # ─────────────────────────────────────────────────────────────────────
        # BAKE VALIDATION & BUTTON
        # ─────────────────────────────────────────────────────────────────────
        layout.separator()

        can_bake = True  # Assume baking is allowed, then disable for various reasons
        bake_error = ""

        # Validate overwrite folder if overwrite mode is enabled
        if scene.smb_overwrite_bake:
            overwrite = scene.smb_overwrite_folder.strip()
            base = scene.bake_base_folder.strip()

            if not overwrite:
                can_bake = False
                bake_error = "Overwrite folder not valid."
            else:
                norm_overwrite = os.path.normpath(overwrite)
                norm_base = os.path.normpath(base)

                if not os.path.exists(norm_overwrite):
                    can_bake = False
                    bake_error = "Overwrite folder not valid."
                elif norm_overwrite == norm_base:
                    can_bake = False
                    bake_error = "Overwrite folder not valid."
                elif not norm_overwrite.startswith(norm_base + os.sep):
                    can_bake = False
                    bake_error = "Overwrite folder not valid."

        layout.prop(scene, "smb_use_low_as_high")

        # ─────────────────────────────────────────────────────────────────────
        # MESH VALIDATION
        # ─────────────────────────────────────────────────────────────────────
        obj = context.object  # Currently selected object in viewport

        # If user selected a _low mesh, validate that the _high mesh exists
        if obj and obj.type == 'MESH' and obj.name.endswith("_low"):
            if not scene.smb_use_low_as_high:
                base_name = obj.name[:-4]  # Strip "_low" suffix
                high_obj = bpy.data.objects.get(base_name + "_high")
                if not high_obj or high_obj.type != 'MESH':
                    row = layout.row()
                    row.alert = True
                    row.label(text=f"No '{base_name}_high' found in scene", icon='ERROR')

            # ─────────────────────────────────────────────────────────────────
            # VERTEX COLOR VALIDATION
            # ─────────────────────────────────────────────────────────────────
            # If vertex colors are enabled, check they actually match the selected mesh
            if scene.smb_use_vertex_colors and len(scene.smb_vertex_colors) > 0:
                from .vertex_colors import get_unique_vertex_colors

                # Get colors from the currently selected mesh
                mesh_colors = get_unique_vertex_colors(obj)

                # Get colors from the UI detection list
                detected_colors = {
                    tuple(round(item.color[i], 3) for i in range(3))
                    for item in scene.smb_vertex_colors
                }

                # If they don't match, the detection is stale (user switched meshes)
                if mesh_colors != detected_colors:
                    row = layout.row()
                    row.alert = True

                    row = layout.row()
                    row.alert = True

                    can_bake = False
                    bake_error = "Vertex colors don't match — re-detect them."

        # Validate that a _low mesh is actually selected
        has_valid_selection = (
                obj is not None and
                obj.type == 'MESH' and
                obj.name.endswith("_low")
        )

        if not has_valid_selection:
            can_bake = False
            bake_error = "Select a _low mesh to bake."

        # ─────────────────────────────────────────────────────────────────────
        # PROCESS STATE CHECKS
        # ─────────────────────────────────────────────────────────────────────
        layout.separator()

        # Block baking if Substance Painter is still running or addon is initializing
        from .classes.bake_watcher import OBJECT_OT_bake_watcher
        import time

        # Check if SP process is still alive (poll() returns None while running)
        sp_still_running = (
                OBJECT_OT_bake_watcher._sp_process is not None and
                OBJECT_OT_bake_watcher._sp_process.poll() is None
        )

        # Check cooldown after last bake (20s to prevent rapid-fire bakes)
        bake_cooldown_active = False
        if OBJECT_OT_bake_watcher._last_bake_completed_time:
            elapsed = time.time() - OBJECT_OT_bake_watcher._last_bake_completed_time
            bake_cooldown_active = elapsed < 20

        # Check startup cooldown (10s for addon initialization)
        startup_cooldown_active = False
        from .. import _addon_startup_time
        if _addon_startup_time:
            elapsed = time.time() - _addon_startup_time
            startup_cooldown_active = elapsed < 10

        # Apply state blocks in priority order
        if sp_still_running:
            can_bake = False
            bake_error = "Substance Painter is still running."
        elif bake_cooldown_active:
            can_bake = False
            bake_error = "Bake in progress, please wait..."
        elif startup_cooldown_active:
            can_bake = False
            bake_error = "Addon initializing, please wait..."

        # Draw the main bake button
        row = layout.row()
        row.enabled = can_bake
        row.operator("object.bake_preview", text="Bake Preview", icon='RENDER_STILL')

        # Show error message if baking is blocked
        if not can_bake:
            box = layout.box()
            box.alert = True
            box.label(text=bake_error, icon='ERROR')

        # Show live status while baking
        if hasattr(scene, "smb_status") and scene.smb_status:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Processing...", icon='SORTTIME')
            col.label(text=scene.smb_status)

        # ─────────────────────────────────────────────────────────────────────
        # VERTEX COLORS SECTION
        # ─────────────────────────────────────────────────────────────────────
        layout.separator()
        layout.prop(scene, "smb_use_vertex_colors")

        if scene.smb_use_vertex_colors:
            row = layout.row(align=True)
            row.operator("object.detect_vertex_colors", text="Detect Vertex Colors", icon='GROUP_VCOL')
            row.operator("smb.show_vertex_colors", text="Show Colors", icon='SHADING_SOLID')
            row.operator("smb.clear_vertex_color_materials", text="", icon='TRASH')

            if not hasattr(scene, "smb_vertex_colors"):
                layout.label(text="Reload addon to enable color detection", icon='ERROR')
                return

            if len(scene.smb_vertex_colors) > 0:
                layout.separator()
                layout.label(text=f"Found {len(scene.smb_vertex_colors)} colors:")
                for item in scene.smb_vertex_colors:
                    box = layout.box()
                    row = box.row(align=True)
                    row.prop(item, "color", text="")
                    row.label(text=item.hex_name)
                    row.operator("smb.pick_vertex_paint_color", text="", icon='EYEDROPPER').hex_name = item.hex_name
                    box.prop(item, "smart_material", text="Material")

                    # Warn if color is too dark (won't bake reliably on ID map)
                    r, g, b = item.color[0], item.color[1], item.color[2]
                    brightness = (r + g + b) / 3.0
                    if brightness < 0.15:
                        warn_row = box.row()
                        warn_row.alert = True
                        warn_row.label(text="Too dark — may not bake reliably", icon='ERROR')
            else:
                layout.label(text="No colors detected yet", icon='INFO')
        else:
            # Single material mode: apply one material to entire mesh
            layout.prop(scene, "smb_single_smart_material", text="Smart Material")

        # ─────────────────────────────────────────────────────────────────────
        # LAST BAKE SUMMARY (COLLAPSIBLE)
        # ─────────────────────────────────────────────────────────────────────
        # Show summary only if at least one previous bake exists
        if scene.smb_last_baked_material and scene.smb_last_bake_time:
            layout.separator()

            import time

            def _time_ago(ts_str):
                # Convert timestamp to human-readable "X seconds ago" format
                try:
                    elapsed = time.time() - float(ts_str)
                    if elapsed < 60:
                        return f"{int(elapsed)}s ago"
                    elif elapsed < 3600:
                        return f"{int(elapsed // 60)}m ago"
                    else:
                        return f"{int(elapsed // 3600)}h ago"
                except:
                    return ""

            box = layout.box()
            row = box.row()
            # Toggle expansion with triangle icon
            row.prop(
                scene, "smb_bake_summary_expanded",
                icon='TRIA_DOWN' if scene.smb_bake_summary_expanded else 'TRIA_RIGHT',
                text="Last Bake",
                emboss=False
            )

            if scene.smb_bake_summary_expanded:
                time_ago = _time_ago(scene.smb_last_bake_time)
                res = scene.smb_last_bake_resolution
                bake_folder = scene.smb_last_bake_folder.strip()

                # Display bake metadata
                col = box.column(align=True)
                col.label(text=f"Material:   {scene.smb_last_baked_material}", icon='MATERIAL')
                col.label(text=f"Resolution: {res}px", icon='IMAGE_DATA')
                if time_ago:
                    col.label(text=f"Baked:      {time_ago}", icon='SORTTIME')

                # List textures in the baked material
                mat = bpy.data.materials.get(scene.smb_last_baked_material)
                if mat and mat.use_nodes:
                    tex_nodes = [
                        n for n in mat.node_tree.nodes
                        if n.type == 'TEX_IMAGE' and n.image
                    ]
                    if tex_nodes:
                        box.separator()
                        tex_col = box.column(align=True)
                        tex_col.label(text=f"Textures ({len(tex_nodes)}):", icon='TEXTURE')
                        for node in tex_nodes:
                            tex_col.label(text=f"{node.image.name}")

                # Show bake folder with "Open in Explorer" button
                if bake_folder and os.path.exists(os.path.dirname(bake_folder)):
                    box.separator()
                    folder_col = box.column(align=True)
                    # Display parent folder (one level up from textures/)
                    display_folder = os.path.dirname(bake_folder)
                    folder_col.label(text=display_folder, icon='FILE_FOLDER')
                    folder_col.operator(
                        "smb.open_bake_folder",
                        text="Open in Explorer",
                    )
