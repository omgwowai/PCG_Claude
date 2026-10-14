"""PCG_2_1_MainTower_Footprint —— 主塔占位（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 8 节点 / 6 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_2_1_MainTower_Footprint',
              params=[P('RectWidth', 'Float', 16000, meta={'Tooltip': 'Width of the landmark rectangle in centimeters'}),
                      P('RectLength', 'Float', 16000, meta={'Tooltip': 'Length of the landmark rectangle in centimeters'}),
                      P('NewProperty', 'Float', 8000)],
              graph_props={'Description': 'Defines the hero tower landmark footprint as a parametric hexagonal spline shape. Consumed by downstream graphs as the boundary for the main tower complex.'}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoSpatial'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        get_width = g.param_path('RectWidth', 'Get Width')
        get_length = g.param_path('RectLength', 'Get Length')
        # 不生效：set.Length 被同名 pin 的输入顶掉
        # 不生效：set.Width 被同名 pin 的输入顶掉
        create_landmark_hexagon = g.sub('Create_Spline_Shape', 'Create Landmark Hexagon', set={'AtWorldOrigin': False, 'Length': 5000, 'Linear': True, 'Ngon': 6, 'Width': 5000}, Width=get_width, Length=get_length)
        transform_offset = g.sub('Transform_Offset', set={'offset': {'X': 0, 'Y': 0, 'Z': 10000}}, comment='shifting up for vizibility above the terrain', PrimaryInput=create_landmark_hexagon)
        debug_primitivedata = g.sub('Debug_PrimitiveData', comment='to visuallize the shape in the viewport', PrimaryInput=transform_offset)
        reroute = g.reroute(create_landmark_hexagon)
    g.out(reroute)
    return g
