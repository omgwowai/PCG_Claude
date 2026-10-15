"""PCG_1_1_Terrain —— 地形底座（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 22 节点 / 22 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_1_1_Terrain',
              params=[P('CityFlatness', 'Float', 0.5, meta={'ToolTip': 'Controls how flat the terrain is under the city. 0 = fully hilly, 1 = fully flat.'}),
                      P('HillsHeight', 'Float', 7001, meta={'ToolTip': 'Controls the amplitude of the hills noise.'})],
              graph_props={'Description': 'This PCG is Shaping procedurally the mesh terrain to create the island base on which the city will exist.'}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoSpatial'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        get_mesh_terrain = g.sub('Get_MeshTerrain', 'Get Mesh Terrain', set={'MeshPartitionBoundSize': {'X': 300000, 'Y': 300000, 'Z': 30000}, 'ModifierSubPriority': 1})
        extract_mesh_terrain_points = g.sub('Extract_MeshTerrainPoints', 'Extract Mesh Terrain Points', PrimaryInput=get_mesh_terrain)
        get_terrain_shaping_1_spline = g.actor_by_tag('Terrain_shaping_1', 'Get Terrain_shaping_1 Spline')
        extract_bounds = g.sub('Extract_Bounds', 'Extract Bounds', PrimaryInput=extract_mesh_terrain_points)
        trace_bound_footprint_top = g.sub('Trace_Bound_Footprint', 'Trace Bound Footprint (Top)', set={'PlanarSurface': 'Top', 'ScaleFactor': {'X': 1, 'Y': 1, 'Z': 1}}, PrimaryInput=extract_bounds)
        expand_footprint_600m = g.sub('Transform_Areas_Expand', 'Expand Footprint 600m', set={'Expand': 60000}, PrimaryInput=trace_bound_footprint_top)
        offset_footprint_down = g.sub('Transform_Offset', 'Offset Footprint Down', set={'PerPoints': False, 'offset': {'X': 0, 'Y': 0, 'Z': -1820.424606}}, comment='Move down', PrimaryInput=expand_footprint_600m)
        get_city_shape_spline = g.actor_by_tag('City', 'Get City Shape Spline')
        city_flatness = g.param_path('CityFlatness', 'City Flatness')
        hills_height = g.param_path('HillsHeight', 'Hills Height')
        # 不生效：set.NoiseAmplitude 被同名 pin 的输入顶掉
        hills_noise = g.sub('Transform_Points_SpatialNoise', 'Hills Noise', set={'Distort': True, 'DistortAmplitude': 33000, 'DistortIterations': 3, 'DistortScale': {'X': 0.3, 'Y': 0.3, 'Z': 0.3}, 'NoiseAmplitude': 7001, 'NoiseBlur': True, 'NoiseBlurDistance': 12000, 'NoiseBlurIterations': 2, 'NoiseIterations': 2, 'NoiseScale': {'X': 0.3, 'Y': 0.3, 'Z': 1}}, PrimaryInput=extract_mesh_terrain_points, NoiseAmplitude=hills_height)
        metadatamaths = g.node('PCGMetadataMathsSettings', set={'Operation': 'OneMinus'}, comment='Invert CityFlatness so that 1.0 = fully flat city\nand 0.0 = full hills. Fed into the Lerp Ratio pin.', In=city_flatness)
        metadatamaths_2 = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Position.Z'), 'Operation': 'Set'}, defaults=[D(1)], comment='Flatten city shape to Z=0 before lifting it\nto the target elevation for projection.', InA=get_city_shape_spline)
        move_city_shape_up = g.sub('Transform_Offset', 'Move City Shape Up', set={'offset': {'X': 0, 'Y': 0, 'Z': 3000}, 'rotationOffset': {'Pitch': 0, 'Roll': 0, 'Yaw': 0}}, PrimaryInput=metadatamaths_2)
        offset_circle_down = g.sub('Transform_Offset', 'Offset Circle Down', set={'PerPoints': False, 'offset': {'X': 0, 'Y': 0, 'Z': -1820.424606}}, comment='Move down', PrimaryInput=get_terrain_shaping_1_spline)
        square_minus_circle = g.sub('Compose_Areas_Exclusion', 'Square Minus Circle', comment='Square footprint minus the Terrain_shaping_1 circle = annular flatten region.', PrimaryInput=offset_footprint_down, SecondaryInput=offset_circle_down)
        flatten_around_circle_falloff = g.sub('Transform_Project', 'Flatten Around Circle (Falloff)', set={'ConvertClosedSplineToPolygon2D': True, 'EndFalloffDistance': 50000, 'ProjectPositions': True, 'StartFalloffDistance': 0, 'UseFalloff': True}, comment='Projects hilly points onto the flat annular region with gradient blend at the boundary (= circle edge).', PrimaryInput=hills_noise, SecondaryInput=square_minus_circle)
        project_city_flat_zone = g.sub('Transform_Project', 'Project City Flat Zone', set={'ConvertClosedSplineToPolygon2D': True, 'EndFalloffDistance': 10000, 'UseFalloff': True}, PrimaryInput=flatten_around_circle_falloff, SecondaryInput=move_city_shape_up)
        metadatamaths_3 = g.node('PCGMetadataMathsSettings', set={'DebugSettings': {'MaterialOverride': 'None', 'PointMesh': '/PCG/DebugObjects/PCG_Cube.PCG_Cube', 'PointScale': 10, 'ScaleMethod': 'Absolute'}, 'InputSource1': sel('$Position'), 'InputSource2': sel('$Position'), 'Operation': 'Lerp'}, defaults=[D(0), D(1), D(2)], comment='Lerp between the hill-only terrain (InA)\nand the city-flat terrain (InB).\nRatio driven by (1 - CityFlatness).', InA=flatten_around_circle_falloff, InB=project_city_flat_zone, Ratio=metadatamaths)
        write_mesh_terrain = g.sub('Write_MeshTerrain', 'Write Mesh Terrain', set={'MeshPartitionBoundSize': {'X': 300000, 'Y': 300000, 'Z': 30000}, 'ModifierSubPriority': 1}, PrimaryInput=metadatamaths_3)
    g.out(write_mesh_terrain)
    return g
