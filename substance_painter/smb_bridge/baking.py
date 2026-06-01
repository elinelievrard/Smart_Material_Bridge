from PySide6.QtCore import QUrl
import substance_painter.baking as sp_bake
from substance_painter.baking import BakingParameters, MeshMapUsage, CurvatureMethod

def setup_baking(texture_sets, high_path, use_low_as_high=False):
    sp_bake.unlink_all_common_parameters()

    for tset in texture_sets:
        bake_params = BakingParameters.from_texture_set(tset)
        bake_params.set_textureset_enabled(True)
        bake_params.set_enabled_bakers([
            MeshMapUsage.Normal,
            MeshMapUsage.WorldSpaceNormal,
            MeshMapUsage.ID,
            MeshMapUsage.AO,
            MeshMapUsage.Curvature,
            MeshMapUsage.Position,
            MeshMapUsage.Thickness,
        ])
        bake_params.set_curvature_method(CurvatureMethod.FromMesh)

        id_params = bake_params.baker(MeshMapUsage.ID)
        BakingParameters.set({
            id_params["ColorSource"]: id_params["ColorSource"].enum_value("Vertex color")
        })

        # Only set high poly if we actually have a separate one
        if not use_low_as_high and high_path:
            high_url = QUrl.fromLocalFile(high_path).toString()
            print(f"[SP] High poly URL: {high_url}")
            common = bake_params.common()
            BakingParameters.set({
                common["HipolyMesh"]: high_url
            })
        else:
            print(f"[SP] No high poly — baking from low poly only")

        print(f"[SP] Baking setup complete for: {tset.name()}")

def start_baking(texture_sets):
    # Kicks off the actual bake — this is non-blocking, SP bakes in the background
    # The BakingProcessEnded event in pipeline.py fires when it's done
    print("[SP] Starting bake...")
    for tset in texture_sets:
        # bake_async starts the bake for one texture set without blocking
        # If you had multiple texture sets (multiple UDIMs/materials) they'd each get baked here
        sp_bake.bake_async(tset)