"""PCG_5_1_CityEdge —— 滨水设施（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 20 节点 / 17 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_5_1_CityEdge',
              params=[P('Partitioned', 'Bool', False),
                      P('PartitionGridSize', 'Float', 25600)],
              graph_props={'Description': "Generates pier and warehouse structures along the city's waterfront edge.\r\n"}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'Seed': 1533108465, 'bEnabled': False, 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'Seed': 1533108465, 'bEnabled': False, 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        get_mesh_terrain_final = g.sub('Get_MeshTerrain', 'Get Mesh Terrain (Final)', set={'MeshPartitionBoundSize': {'X': 300000, 'Y': 300000, 'Z': 100000}, 'MeshPartitionQueryType': 'Final'})
        extract_terrain_points = g.sub('Extract_MeshTerrainPoints', 'Extract Terrain Points', PrimaryInput=get_mesh_terrain_final)
        filter_point_data_post_terrain_extract = g.node('PCGFilterByTypeSettings', 'Filter Point Data (Post Terrain Extract)', set={'TargetType': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoPoint'"}, {'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoParam'"}]}}, In=extract_terrain_points)
        filter_above_sea_level_z_72_6 = g.node('PCGAttributeFilteringSettings', 'Filter: Above Sea Level (Z > -72.6)', set={'AttributeTypes': {'BoolValue': False, 'DoubleValue': -72.639648, 'FloatValue': 0, 'Int32Value': 0, 'IntValue': 0, 'NameValue': 'None', 'QuatValue': {'W': 1, 'X': 0, 'Y': 0, 'Z': 0}, 'RotatorValue': {'Pitch': 0, 'Roll': 0, 'Yaw': 0}, 'SoftClassPathValue': 'None', 'SoftObjectPathValue': 'None', 'StringValue': '', 'TransformValue': {'Rotation': {'W': 1, 'X': 0, 'Y': 0, 'Z': 0}, 'Scale3D': {'X': 1, 'Y': 1, 'Z': 1}, 'Translation': {'X': 0, 'Y': 0, 'Z': 0}}, 'Type': 'Double', 'Vector2Value': {'X': 0, 'Y': 0}, 'Vector4Value': {'W': 0, 'X': 0, 'Y': 0, 'Z': 0}, 'VectorValue': {'X': 0, 'Y': 0, 'Z': 0}, 'bAllowsTypeChange': True}, 'DebugSettings': {'MaterialOverride': 'None', 'PointMesh': '/PCG/DebugObjects/PCG_Cube.PCG_Cube', 'PointScale': 7.56789493560791, 'ScaleMethod': 'Absolute'}, 'TargetAttribute': sel('$Position.Z'), 'ThresholdAttribute': sel('@Last'), 'bUseConstantThreshold': True, 'bUseSpatialQuery': False}, comment='Threshold of -72.6 corresponds to the sea surface Z in this level.\nKeeps only terrain points above water to bound the convex hull correctly.', In=filter_point_data_post_terrain_extract.InsideFilter)
        filter_point_data_pre_convex_hull = g.node('PCGFilterByTypeSettings', 'Filter Point Data (Pre Convex Hull)', set={'TargetType': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoPoint'"}]}}, In=filter_above_sea_level_z_72_6.InsideFilter)
        build_convex_hull_of_terrain_boundary = g.node('PCGConvexHull2DSettings', 'Build Convex Hull Of Terrain Boundary', set={'DebugSettings': {'MaterialOverride': 'None', 'PointMesh': '/PCG/DebugObjects/PCG_Cube.PCG_Cube', 'PointScale': 7.157337188720703, 'ScaleMethod': 'Absolute'}}, In=filter_point_data_pre_convex_hull.InsideFilter)
        create_city_edge_spline_closed_linear = g.node('PCGCreateSplineSettings', 'Create City Edge Spline (Closed Linear)', set={'ArriveTangentAttribute': 'ArriveTangent', 'InterpTypeAttribute': 'InterpType', 'LeaveTangentAttribute': 'LeaveTangent', 'bClosedLoop': True, 'bLinear': True}, In=build_convex_hull_of_terrain_boundary)
        get_edge_spline_control_points = g.node('PCGGetSplineControlPointsSettings', 'Get Edge Spline Control Points', In=create_city_edge_spline_closed_linear)
        random_selection_of_dock_spawn_points_51 = g.node('PCGRandomChoiceSettings', 'Random Selection Of Dock Spawn Points (~51%)', set={'Ratio': 0.5152000188827515, 'Seed': -1017473487, 'bFixedMode': False}, In=get_edge_spline_control_points)
        zero_roll_on_dock_points = g.node('PCGMetadataMathsSettings', 'Zero Roll On Dock Points', set={'InputSource1': sel('$Rotation.Roll'), 'Operation': 'Set'}, defaults=[D(1)], InA=random_selection_of_dock_spawn_points_51.Chosen)
        zero_pitch_on_dock_points = g.node('PCGMetadataMathsSettings', 'Zero Pitch On Dock Points', set={'InputSource1': sel('$Rotation.Pitch'), 'Operation': 'Set'}, defaults=[D(1)], InA=zero_roll_on_dock_points)
        partitiongridsize = g.param('PartitionGridSize', 'PartitionGridSize')
        partitioned = g.param('Partitioned', 'Partitioned')
        assign_pier_warehouse_assemblies = g.sub('Assign_Assets', 'Assign Pier & Warehouse Assemblies', set={'Assets': ['/CitySamplePCG/PCG/DataAssets/Piers/Dock_A_PCG.Dock_A_PCG', '/CitySamplePCG/PCG/DataAssets/Piers/Dock_B_PCG.Dock_B_PCG', '/CitySamplePCG/PCG/DataAssets/Piers/Warehouse_A_PCG.Warehouse_A_PCG', '/CitySamplePCG/PCG/DataAssets/Piers/Warehouse_B_PCG.Warehouse_B_PCG', '/CitySamplePCG/PCG/DataAssets/Piers/Warehouse_C_PCG.Warehouse_C_PCG'], 'PositionOffset': {'X': 0, 'Y': -492.541261, 'Z': 0}, 'RotationOffset': {'Pitch': 0, 'Roll': 0, 'Yaw': 0}}, PrimaryInput=zero_pitch_on_dock_points)
        branch = g.node('PCGBranchSettings', In=assign_pier_warehouse_assemblies, bOutputToB=partitioned.Partitioned)
        spawn_pier_warehouse_assemblies = g.sub('Spawn_Assets', 'Spawn Pier & Warehouse Assemblies', PrimaryInput=branch['Output A'])
        gridpartition = g.sub('GridPartition', Points=branch['Output B'], Grid_Size=partitiongridsize.PartitionGridSize)
        loopspawnactorperdata = g.loop('LoopSpawnActorPerData', set={'ActorBaseName': 'CityEdge_'}, Points=gridpartition)
    return g
