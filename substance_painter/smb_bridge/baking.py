from PySide6.QtCore import QUrl
import substance_painter.baking as sp_bake
from substance_painter.baking import BakingParameters, MeshMapUsage, CurvatureMethod

def setup_baking(texture_sets, high_path):
    # Unlinks any shared/common baking parameters that were set in a previous session
    # SP can have "common" params that apply to all texture sets at once — we reset
    # those first so we start fresh and don't inherit stale settings from a previous bake
    sp_bake.unlink_all_common_parameters()

    # SP's baking API expects the high poly path as a QUrl string, not a plain file path
    # QUrl.fromLocalFile converts a Windows path to a file URL
    # "C:\Users\eline\MyBakeFolder\chair\fbx\Chair_high.fbx"
    # -> "file:///C:/Users/eline/MyBakeFolder/chair/fbx/Chair_high.fbx"
    # .toString() converts the QUrl object to a plain string SP can consume
    high_url = QUrl.fromLocalFile(high_path).toString()
    print(f"[SP] High poly URL: {high_url}")

    for tset in texture_sets:
        # tset = <TextureSet "Chair_low">
        # BakingParameters.from_texture_set gives us the bake settings object for this texture set
        # this is where we configure everything: which maps to bake, high poly path, resolution etc.
        bake_params = BakingParameters.from_texture_set(tset)

        # Enable baking for this texture set
        # False would skip it entirely even if maps are listed below
        bake_params.set_textureset_enabled(True)

        # Tell SP which maps to bake — these are the 7 maps the bridge always bakes
        bake_params.set_enabled_bakers([
            MeshMapUsage.Normal,
            MeshMapUsage.WorldSpaceNormal,
            MeshMapUsage.ID,
            MeshMapUsage.AO,
            MeshMapUsage.Curvature,
            MeshMapUsage.Position,
            MeshMapUsage.Thickness,
        ])

        # CurvatureMethod.FromMesh calculates curvature directly from the mesh geometry
        bake_params.set_curvature_method(CurvatureMethod.FromMesh)

        # Configure the ID map to use vertex colors as its color source
        # id_params = the settings object specifically for the ID baker
        # id_params["ColorSource"] is the dropdown you'd set manually in SP's bake dialog
        # enum_value("Vertex color") gives us the correct internal enum value for that option
        id_params = bake_params.baker(MeshMapUsage.ID)
        BakingParameters.set({
            id_params["ColorSource"]: id_params["ColorSource"].enum_value("Vertex color")
        })

        # Set the high poly mesh path on the common (shared) parameters
        # common() returns the parameters that apply to all bakers in this texture set
        # HipolyMesh is the field SP uses to know which high poly to project detail from
        common = bake_params.common()
        BakingParameters.set({
            common["HipolyMesh"]: high_url
        })

        print(f"[SP] Baking setup complete for: {tset.name()} — 7 maps enabled")

def start_baking(texture_sets):
    # Kicks off the actual bake — this is non-blocking, SP bakes in the background
    # The BakingProcessEnded event in pipeline.py fires when it's done
    print("[SP] Starting bake...")
    for tset in texture_sets:
        # bake_async starts the bake for one texture set without blocking
        # If you had multiple texture sets (multiple UDIMs/materials) they'd each get baked here
        sp_bake.bake_async(tset)