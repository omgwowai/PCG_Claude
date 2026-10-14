"""PCG_2_2_CentralPark_Footprint —— 中央公园范围（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 5 节点 / 3 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_2_2_CentralPark_Footprint',
              params=[],
              graph_props={'Description': "Defines the Central Park boundary as a rectangular spline at 1:4 scale relative to NYC's Central Park. Consumed by downstream graphs as an exclusion zone and visual layout reference."}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoSpatial'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        park_footprint_1000x200m_1_4_scale = g.sub('Create_Spline_Shape', 'Park Footprint 1000x200m (1:4 scale)', set={'AtWorldOrigin': False, 'Length': 20000, 'Linear': True, 'Ngon': 4, 'Width': 100000})
        debug_footprint = g.sub('Debug_PrimitiveData', 'Debug Footprint', set={'RandomColorPerData': True}, PrimaryInput=park_footprint_1000x200m_1_4_scale)
        metadatamaths = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Position.Z'), 'Operation': 'Set'}, defaults=[D(1)], comment='Ensure footprint is set to the ground level, regardless of the PCG actor position in Z', InA=park_footprint_1000x200m_1_4_scale)
    g.out(metadatamaths)
    return g
