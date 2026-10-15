"""PCG_1_2_BG_Buildings —— 远景天际线（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 9 节点 / 8 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_1_2_BG_Buildings',
              params=[],
              graph_props={'Description': 'Generates the distant background city silhouette visible beyond the playable area, excluding a center zone so it never overlaps the real city.'}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoSpatial'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        create_outer_area_25km_square = g.sub('Create_Spline_Shape', 'Create Outer Area (25km square)', set={'Length': 2500000, 'Width': 2500000})
        center_exclusion_size_4_1_km = g.node('PCGCreateAttributeSetSettings', 'Center Exclusion Size (~4.1 km)', set={'AttributeTypes': {'BoolValue': False, 'DoubleValue': 0, 'FloatValue': 411769.84375, 'Int32Value': 0, 'IntValue': 0, 'NameValue': 'None', 'QuatValue': {'W': 1, 'X': 0, 'Y': 0, 'Z': 0}, 'RotatorValue': {'Pitch': 0, 'Roll': 0, 'Yaw': 0}, 'SoftClassPathValue': 'None', 'SoftObjectPathValue': 'None', 'StringValue': '', 'TransformValue': {'Rotation': {'W': 1, 'X': 0, 'Y': 0, 'Z': 0}, 'Scale3D': {'X': 1, 'Y': 1, 'Z': 1}, 'Translation': {'X': 0, 'Y': 0, 'Z': 0}}, 'Type': 'Float', 'Vector2Value': {'X': 0, 'Y': 0}, 'Vector4Value': {'W': 0, 'X': 0, 'Y': 0, 'Z': 0}, 'VectorValue': {'X': 0, 'Y': 0, 'Z': 0}, 'bAllowsTypeChange': True}})
        # 不生效：set.Length 被同名 pin 的输入顶掉
        # 不生效：set.Width 被同名 pin 的输入顶掉
        create_center_exclusion_area_3km_square = g.sub('Create_Spline_Shape', 'Create Center Exclusion Area (3km square)', set={'Length': 300000, 'Width': 300000}, Width=center_exclusion_size_4_1_km, Length=center_exclusion_size_4_1_km)
        exclude_center_from_outer_area = g.sub('Compose_Areas_Exclusion', 'Exclude Center from Outer Area', comment='Subtract 3km center area from 25km outer area \r\nto leave space for the city building', PrimaryInput=create_outer_area_25km_square, SecondaryInput=create_center_exclusion_area_3km_square)
        sparse_random_scatter = g.sub('Fill_Areas_Randomly', 'Sparse Random Scatter', set={'PointsPerSquaredMeter': 1e-06, 'RotationRange': {'Pitch': 0, 'Roll': 0, 'Yaw': 180}, 'SamplingSeed': 1898920501}, comment='Scatter points extremely sparsely across background area.\r\nThisi is becasue we are covering an extremely large area.', PrimaryInput=exclude_center_from_outer_area)
        random_cull_36_removed = g.sub('Filter_RandomChoice', 'Random Cull (~36% removed)', set={'RandomPerDataset': False, 'Ratio': 0.641598}, PrimaryInput=sparse_random_scatter)
        spawn_background_buildings = g.sub('Spawn_Assets', 'Spawn Background Buildings', set={'Assets': ['/Game/Environment/Background_City/Mesh/SM_bgcitya.SM_bgcitya', '/Game/Environment/Background_City/Mesh/SM_bgcityb.SM_bgcityb', '/Game/Environment/Background_City/Mesh/SM_bgcityb_NotNanite.SM_bgcityb_NotNanite'], 'MaterialOverride': '/CitySamplePCG/Materials/BackGroundCity/MI_BackgroundCity.MI_BackgroundCity', 'PositionOffset': {'X': 0, 'Y': 0, 'Z': 13200}, 'ScaleOffset': {'X': 100, 'Y': 1, 'Z': 1}}, comment='Spawn selected static meshes at scattered points', bubble_visible=False, PrimaryInput=random_cull_36_removed.Selected)
    g.out(spawn_background_buildings)
    return g
