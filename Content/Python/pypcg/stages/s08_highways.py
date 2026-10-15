"""PCG_3_1_3_Highways —— 高速（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 36 节点 / 35 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_3_1_3_Highways',
              params=[P('Highway_Width', 'Double', 2000, meta={'ToolTip': 'Width of the generated highway in centimeters. Drives the Size parameter of the Assign_ShapeGrammarDefinition subgraph that runs SGD_ElevatedHighway.'}),
                      P('Partitioned', 'Bool', False),
                      P('PartitionGridSize', 'Double', 25600)],
              graph_props={'Description': 'Generates the elevated highway running through the city. '}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoSpatial'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        highway_width = g.param_path('Highway_Width', 'Highway Width')
        get_roads_graph_output = g.ref('Roads', 'Get Roads Graph Output')
        filter_road_modified_terrain = g.sub('Filter_Tags', 'Filter: Road-Modified Terrain', set={'FilteredInputTags': 'ModifiedTerrain'}, PrimaryInput=get_roads_graph_output)
        filter_road_footprints = g.sub('Filter_Tags', 'Filter: Road Footprints', set={'FilteredInputTags': 'RoadFootprints'}, PrimaryInput=get_roads_graph_output)
        make_road_footprints_concrete = g.node('PCGMakeConcreteSettings', 'Make Road Footprints Concrete', In=filter_road_footprints.Selected)
        get_final_mesh_terrain = g.sub('Get_MeshTerrain', 'Get Final Mesh Terrain', set={'MeshPartitionBoundSize': {'X': 300000, 'Y': 300000, 'Z': 300000}, 'MeshPartitionQueryType': 'Final'})
        get_highway_spline_actors = g.ref(['HighwaySpline2', 'HighwaySpline3'], 'Get Highway Spline Actors')
        flatten_spline_to_z_0 = g.node('PCGMetadataMathsSettings', 'Flatten Spline to Z = 0', set={'InputSource1': sel('$Position.Z'), 'Operation': 'Set'}, defaults=[D(1)], InA=get_highway_spline_actors)
        resample_spline_40m_intervals = g.sub('Transform_Resample', 'Resample Spline (40m intervals)', set={'Distance': 8000, 'SamplingMode': 'Distance'}, PrimaryInput=flatten_spline_to_z_0)
        project_spline_onto_road_modified_terrain = g.sub('Transform_Project', 'Project Spline onto Road-Modified Terrain', comment='To ensure flat Highway we project the curve instead of \r\nresulting points. At the opposite of the roads, which are \r\nused to flatten the terrain.', PrimaryInput=resample_spline_40m_intervals, SecondaryInput=get_final_mesh_terrain)
        keep_polyline_data_only = g.node('PCGFilterByTypeSettings', 'Keep Polyline Data Only', set={'TargetType': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoPolyline'"}]}}, In=project_spline_onto_road_modified_terrain)
        getsplinecontrolpoints = g.node('PCGGetSplineControlPointsSettings', In=keep_polyline_data_only.InsideFilter)
        metadatamaths = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Position.Z'), 'Operation': 'Clamp'}, defaults=[D(1, 'Double', -500), D(2, 'Double', 1000000000)], comment='Clamping proj down at Water level', In=getsplinecontrolpoints)
        createspline = g.node('PCGCreateSplineSettings', set={'ArriveTangentAttribute': 'ArriveTangent', 'InterpTypeAttribute': 'InterpType', 'LeaveTangentAttribute': 'LeaveTangent'}, In=metadatamaths)
        partitiongridsize = g.param('PartitionGridSize', 'PartitionGridSize')
        partitioned = g.param('Partitioned', 'Partitioned')
        metadatamaths_2 = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Rotation.Roll'), 'Operation': 'Set'}, defaults=[D(1)], InA=createspline)
        metadatamaths_3 = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Rotation.Pitch'), 'Operation': 'Set'}, defaults=[D(1)], InA=metadatamaths_2)
        assign_highway_shape_grammar = g.sub('Assign_ShapeGrammarDefinition', 'Assign Highway Shape Grammar', set={'ShapeGrammarDefinition': '/CitySamplePCG/PCG/DataAssets/Roads/ElevatedHighway/SGD_ElevatedHighway_oneWay.SGD_ElevatedHighway_oneWay', 'SpawnAssets': False}, comment='Runs the SGD_ElevatedHighway shape grammar definition along the spline.\r\nWidth is driven by the Highway_Width graph parameter.', bubble_visible=False, PrimaryInput=metadatamaths_3, Size=highway_width)
        expand_footprint_15m = g.sub('Transform_Areas_Expand', 'Expand Footprint 15m', set={'Expand': 1500}, PrimaryInput=assign_highway_shape_grammar.Footprints)
        tag_as_highway = g.node('PCGAddTagSettings', 'Tag as Highway', set={'TagsToAdd': 'Highway'}, comment='Marks the output so downstream steps can identify and avoid the highway footprint.', bubble_visible=False, In=expand_footprint_15m)
        cast_asset_attribute_to_string = g.node('PCGAttributeCastSettings', 'Cast Asset Attribute to String', set={'InputSource': sel('Asset'), 'OutputTarget': sel('AssetString'), 'OutputType': 'String'}, In=assign_highway_shape_grammar.Points)
        keep_points_attribute_sets = g.node('PCGFilterByTypeSettings', 'Keep Points & Attribute Sets', set={'TargetType': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoPoint'"}, {'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoParam'"}]}}, In=cast_asset_attribute_to_string)
        filter_pillar_assets_only = g.node('PCGAttributeFilteringSettings', 'Filter: Pillar Assets Only', set={'AttributeTypes': {'BoolValue': False, 'DoubleValue': 0, 'FloatValue': 0, 'Int32Value': 0, 'IntValue': 0, 'NameValue': 'None', 'QuatValue': {'W': 1, 'X': 0, 'Y': 0, 'Z': 0}, 'RotatorValue': {'Pitch': 0, 'Roll': 0, 'Yaw': 0}, 'SoftClassPathValue': 'None', 'SoftObjectPathValue': 'None', 'StringValue': 'Round', 'TransformValue': {'Rotation': {'W': 1, 'X': 0, 'Y': 0, 'Z': 0}, 'Scale3D': {'X': 1, 'Y': 1, 'Z': 1}, 'Translation': {'X': 0, 'Y': 0, 'Z': 0}}, 'Type': 'String', 'Vector2Value': {'X': 0, 'Y': 0}, 'Vector4Value': {'W': 0, 'X': 0, 'Y': 0, 'Z': 0}, 'VectorValue': {'X': 0, 'Y': 0, 'Z': 0}, 'bAllowsTypeChange': True}, 'Operator': 'Substring', 'TargetAttribute': sel('AssetString'), 'ThresholdAttribute': sel('@Last'), 'bUseConstantThreshold': True, 'bUseSpatialQuery': False}, In=keep_points_attribute_sets.InsideFilter)
        filterbytype = g.node('PCGFilterByTypeSettings', set={'TargetType': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoPoint'"}]}}, In=filter_pillar_assets_only.InsideFilter)
        project_assets_onto_road_footprints = g.node('PCGProjectionSettings', 'Project Assets onto Road Footprints', set={'ProjectionParams': {'AttributeList': '', 'AttributeMergeOperation': 'TargetValue', 'AttributeMode': 'ExcludeAttributes', 'ColorBlendMode': 'SourceValue', 'TagMergeOperation': 'Source', 'bProjectPositions': False, 'bProjectRotations': False, 'bProjectScales': False}, 'bKeepZeroDensityPoints': True}, In=filterbytype.InsideFilter, pins={'Projection Target': make_road_footprints_concrete})
        keep_points_attribute_sets_post_projection = g.node('PCGFilterByTypeSettings', 'Keep Points & Attribute Sets (post-projection)', set={'TargetType': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoPoint'"}, {'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfoParam'"}]}}, In=project_assets_onto_road_footprints)
        filter_density_1_keep_grounded_points = g.node('PCGAttributeFilteringSettings', 'Filter: Density = 1 (keep grounded points)', set={'Operator': 'Equal', 'ThresholdAttribute': sel('@Last'), 'bUseConstantThreshold': True, 'bUseSpatialQuery': False}, In=keep_points_attribute_sets_post_projection.InsideFilter)
        reroute = g.reroute(filter_pillar_assets_only.OutsideFilter)
        outside_highrise_filter_no_footprint_match = g.reroute(reroute, 'Outside HighRise Filter (no footprint match)')
        branch = g.node('PCGBranchSettings', In=[filter_density_1_keep_grounded_points.InsideFilter, outside_highrise_filter_no_footprint_match], bOutputToB=partitioned.Partitioned)
        spawn_highway_support_assets = g.sub('Spawn_Assets', 'Spawn Highway Support Assets', PrimaryInput=branch['Output A'])
        gridpartition = g.sub('GridPartition', Points=branch['Output B'], Grid_Size=partitiongridsize.PartitionGridSize)
        loopspawnactorperdata = g.loop('LoopSpawnActorPerData', set={'ActorBaseName': 'Highways_', 'EnableCollision': True}, Points=gridpartition)
    g.out(tag_as_highway)
    return g
