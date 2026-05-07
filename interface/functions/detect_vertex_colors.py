import bpy

def get_unique_vertex_colors(obj, color_layer_name=None, precision=3):
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
            color = item.color if color_layer.data_type == 'BYTE_COLOR' else item.vector
            rounded = tuple(round(c, precision) for c in color[:3])
            unique_colors.add(rounded)

    elif color_layer.domain == 'POINT':
        for i in range(len(mesh.vertices)):
            item = color_layer.data[i]
            color = item.color if color_layer.data_type == 'BYTE_COLOR' else item.vector
            rounded = tuple(round(c, precision) for c in color[:3])
            unique_colors.add(rounded)

    return unique_colors