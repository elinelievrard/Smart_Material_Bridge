import bpy
from .functions.get_smart_materials import get_smart_material_items

def clear_materials(obj):
    """Remove all material slots from a mesh object."""
    if not obj or obj.type != 'MESH':
        return
    obj.data.materials.clear()

def get_unique_vertex_colors(obj, color_layer_name=None, precision=3):
    # {
    #     (1.0, 0.0, 0.0),
    #     (0.0, 1.0, 0.0),
    #     (0.2, 0.2, 0.2)
    # }
    mesh = obj.data

    # Find color attribute explicitly instead of using .active
    color_layer = None
    if color_layer_name:
        color_layer = mesh.color_attributes.get(color_layer_name)
    else:
        # Find first actual color attribute (BYTE_COLOR or FLOAT_COLOR)
        for attr in mesh.color_attributes:
            if attr.data_type in ('BYTE_COLOR', 'FLOAT_COLOR'):
                color_layer = attr
                break

    if not color_layer:
        print("No vertex color layer found")
        return set()

    print("Using color layer:", color_layer.name, "| type:", color_layer.data_type, "| domain:", color_layer.domain)

    unique_colors = set()

    if color_layer.domain == 'CORNER':
        for loop in mesh.loops:
            item = color_layer.data[loop.index]
            color = item.color
            rounded = tuple(round(c, precision) for c in color[:3])
            unique_colors.add(rounded)

    elif color_layer.domain == 'POINT':
        for i in range(len(mesh.vertices)):
            item = color_layer.data[i]
            color = item.color
            rounded = tuple(round(c, precision) for c in color[:3])
            unique_colors.add(rounded)

    return unique_colors

class SMB_OT_pick_vertex_paint_color(bpy.types.Operator):
    bl_idname = "smb.pick_vertex_paint_color"
    bl_label = "Use Vertex Paint Color"
    bl_description = "Set this slot's color to the active vertex paint brush color"

    hex_name: bpy.props.StringProperty()

    def execute(self, context):
        for item in context.scene.smb_vertex_colors:
            if item.hex_name == self.hex_name:
                context.tool_settings.vertex_paint.brush.color = (
                    item.color[0], item.color[1], item.color[2]
                )
                break
        return {'FINISHED'}


class SMB_VertexColorItem(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=3,
        min=0.0, max=1.0
    )
    hex_name: bpy.props.StringProperty(name="Hex Name")
    smart_material: bpy.props.EnumProperty(
        name="Smart Material",
        description="Smart material to assign to this vertex color",
        items=get_smart_material_items
    )

class OBJECT_OT_detect_vertex_colors(bpy.types.Operator):
    bl_idname = "object.detect_vertex_colors"
    bl_label = "Detect Vertex Colors"
    bl_description = "Detect the vertex colors assigned to the mesh"

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object first")
            return {'CANCELLED'}

        colors = get_unique_vertex_colors(obj)

        if not colors:
            self.report({'WARNING'}, "No vertex colors found on this object")
            return {'CANCELLED'}

        # Save existing assignments keyed by float string (matches bake_preview color_mapping format)
        previous_assignments = {}
        for item in context.scene.smb_vertex_colors:
            if item.smart_material and item.smart_material != 'NONE':
                r, g, b = item.color[0], item.color[1], item.color[2]
                float_key = f"{r:.6f},{g:.6f},{b:.6f}"
                previous_assignments[float_key] = item.smart_material

        context.scene.smb_vertex_colors.clear()

        for color in colors:
            item = context.scene.smb_vertex_colors.add()
            item.color = color
            # hex_name is still used for display only in the UI
            item.hex_name = '#{:02X}{:02X}{:02X}'.format(
                int(color[0] * 255),
                int(color[1] * 255),
                int(color[2] * 255)
            )
            # Restore assignment using float key
            r, g, b = color[0], color[1], color[2]
            float_key = f"{r:.6f},{g:.6f},{b:.6f}"
            if float_key in previous_assignments:
                item.smart_material = previous_assignments[float_key]

        self.report({'INFO'}, f"Found {len(colors)} vertex colors")
        return {'FINISHED'}

def color_to_hex(color, precision=3):
    r = int(round(color[0], precision) * 255)
    g = int(round(color[1], precision) * 255)
    b = int(round(color[2], precision) * 255)
    return '#{:02X}{:02X}{:02X}'.format(
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
    )

class SMB_OT_show_vertex_colors(bpy.types.Operator):
    bl_idname = "smb.show_vertex_colors"
    bl_label = "Show Vertex Colors"
    bl_description = "Assign a flat-color material for each detected vertex color so you can see them on the mesh"

    def execute(self, context):
        scene = context.scene
        obj = context.object

        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object first")
            return {'CANCELLED'}

        if not scene.smb_vertex_colors:
            self.report({'WARNING'}, "No vertex colors detected yet — run Detect Vertex Colors first")
            return {'CANCELLED'}

        # Clear all existing materials before recalculating
        clear_materials(obj)

        mesh = obj.data

        color_layer = None
        for attr in mesh.color_attributes:
            if attr.data_type in ('BYTE_COLOR', 'FLOAT_COLOR'):
                color_layer = attr
                break

        if not color_layer:
            self.report({'WARNING'}, "No color attribute found on mesh")
            return {'CANCELLED'}

        print(f"[SMB] Using color layer: {color_layer.name} | {color_layer.data_type} | {color_layer.domain}")

        hex_to_mat = {}
        for item in scene.smb_vertex_colors:
            mat_name = f"SMB_VC_{item.hex_name}"
            mat = bpy.data.materials.get(mat_name)
            if not mat:
                mat = bpy.data.materials.new(name=mat_name)
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                nodes.clear()

                bsdf = nodes.new("ShaderNodeBsdfPrincipled")
                bsdf.location = (0, 0)
                bsdf.inputs["Base Color"].default_value = (*item.color, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.8
                bsdf.inputs["Metallic"].default_value = 0.0

                output = nodes.new("ShaderNodeOutputMaterial")
                output.location = (300, 0)
                links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

            hex_to_mat[item.hex_name] = mat
            print(f"[SMB] Material ready: {mat_name}")

        existing_names = [m.name for m in mesh.materials]
        for mat in hex_to_mat.values():
            if mat.name not in existing_names:
                mesh.materials.append(mat)

        slot_index = {m.name: i for i, m in enumerate(mesh.materials)}

        precision = 3
        assigned = 0
        missed = set()

        if color_layer.domain == 'CORNER':
            loop_hex = {}
            for loop in mesh.loops:
                item = color_layer.data[loop.index]
                color = item.color
                loop_hex[loop.index] = color_to_hex(color, precision)

            for poly in mesh.polygons:
                counts = {}
                for loop_idx in poly.loop_indices:
                    h = loop_hex[loop_idx]
                    counts[h] = counts.get(h, 0) + 1
                dominant = max(counts, key=counts.get)
                mat = hex_to_mat.get(dominant)
                if mat:
                    poly.material_index = slot_index[mat.name]
                    assigned += 1
                else:
                    missed.add(dominant)

        elif color_layer.domain == 'POINT':
            for poly in mesh.polygons:
                counts = {}
                for vert_idx in poly.vertices:
                    item = color_layer.data[vert_idx]
                    color = item.color
                    h = color_to_hex(color, precision)
                    counts[h] = counts.get(h, 0) + 1
                dominant = max(counts, key=counts.get)
                mat = hex_to_mat.get(dominant)
                if mat:
                    poly.material_index = slot_index[mat.name]
                    assigned += 1
                else:
                    missed.add(dominant)

        if missed:
            print(f"[SMB] Unmatched hex colors on faces: {missed}")
            print(f"[SMB] Known hex colors: {list(hex_to_mat.keys())}")

        self.report({'INFO'}, f"Assigned {assigned}/{len(mesh.polygons)} faces across {len(hex_to_mat)} materials")
        return {'FINISHED'}

class SMB_OT_clear_vertex_color_materials(bpy.types.Operator):
    bl_idname = "smb.clear_vertex_color_materials"
    bl_label = "Clear Materials"
    bl_description = "Remove all materials from the selected object"

    def execute(self, context):
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object first")
            return {'CANCELLED'}

        clear_materials(obj)
        self.report({'INFO'}, f"Cleared all materials from {obj.name}")
        return {'FINISHED'}