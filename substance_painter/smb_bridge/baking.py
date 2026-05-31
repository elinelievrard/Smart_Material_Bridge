from PySide6.QtCore import QUrl
import substance_painter.baking as sp_bake
from substance_painter.baking import BakingParameters, MeshMapUsage, CurvatureMethod

def setup_baking(texture_sets, high_path):
    sp_bake.unlink_all_common_parameters()

    high_url = QUrl.fromLocalFile(high_path).toString()
    print(f"[SP] High poly URL: {high_url}")

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

        # Curvature from mesh gives the best edge wear results
        bake_params.set_curvature_method(CurvatureMethod.FromMesh)

        # Set vertex color source for ID map
        id_params = bake_params.baker(MeshMapUsage.ID)
        BakingParameters.set({
            id_params["ColorSource"]: id_params["ColorSource"].enum_value("Vertex color")
        })

        # Set high poly and shared common params
        common = bake_params.common()
        BakingParameters.set({
            common["HipolyMesh"]: high_url
        })

        print(f"[SP] Baking setup complete for: {tset.name()} — 7 maps enabled")

def start_baking(texture_sets):
    print("[SP] Starting bake...")
    for tset in texture_sets:
        sp_bake.bake_async(tset)