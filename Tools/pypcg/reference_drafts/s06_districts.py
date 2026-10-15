"""PCG_3_1_1_Districts —— 街区骨架（CODEGEN DRAFT：尚未按飞书文档分步整理）

官方 77 节点 / 89 边。由 Tools/pypcg/codegen.py 生成；整理规则见 docs/pypcg-guide.md。
"""
from pypcg import D, Graph, NodeRef, P, sel  # noqa: F401


def build():
    g = Graph('PCG_3_1_1_Districts',
              params=[P('SubDistrictSeed', 'Int32', 7, meta={'Tooltip': 'Seed for recursive sub-district split'}),
                      P('Dividable_district_Limit', 'Double', 150000),
                      P('Debug_Roads', 'Bool', False),
                      P('Debug_Undividable_districts', 'Bool', False),
                      P('SmallMediumThreshold', 'Double', 200000, meta={'Tooltip': 'Area threshold (cm^2). Below this -> Small district.'}),
                      P('MediumLargeThreshold', 'Double', 500000, meta={'Tooltip': 'Area threshold (cm^2). Below this -> Medium; Above -> Large.'}),
                      P('SmallGridWidth', 'Double', 6000, meta={'Tooltip': 'Block grid width for Small districts (cm).'}),
                      P('SmallGridLength', 'Double', 3000, meta={'Tooltip': 'Block grid length for Small districts (cm).'}),
                      P('LargeGridWidth', 'Double', 24000, meta={'Tooltip': 'Block grid width for Large districts (cm).'}),
                      P('LargeGridLength', 'Double', 12000, meta={'Tooltip': 'Block grid length for Large districts (cm).'}),
                      P('Debug_DistrictCategories', 'Bool', False, meta={'Tooltip': 'When true, spawn colored planar debug meshes for Small/Medium/Large districts.'}),
                      P('MediumGridWidth', 'Double', 12000, meta={'Tooltip': 'Block grid width for Medium districts (cm).'}),
                      P('MediumGridLength', 'Double', 6000, meta={'Tooltip': 'Block grid length for Medium districts (cm).'})],
              graph_props={'Description': "This PCG will define the main city layout. It consumes the city shape and the arteries. And we'll create out of it  districts, sub-districts, City blocks and the first network of roads. There are several parameters that allow you to adjust those districts and blocks. "}, input_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'In', 'PinStatus': 'Advanced', 'Tooltip': 'Default input pin.', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'Seed': 1533108465, 'bHasAddedDefaultPin': True}, output_settings={'Pins': [{'AllowedTypes': {'CustomSubtype': -1, 'Ids': [{'Struct': "/Script/CoreUObject.ScriptStruct'/Script/PCG.PCGDataTypeInfo'"}]}, 'Label': 'Out', 'PinStatus': 'Advanced', 'Tooltip': '', 'Usage': 'Normal', 'bAllowMultipleConnections': True, 'bAllowMultipleData': True, 'bInvisiblePin': False}], 'Seed': 1533108465, 'bHasAddedDefaultPin': True})
    with g.step(0, "未整理"):
        get_city_shape_spline = g.actor_by_tag('City', 'Get City Shape Spline', settings={'Seed': -1644386363})
        get_arteries = g.actor_by_tag('Arteries', 'Get Arteries', settings={'Seed': -1644386363})
        get_sub_district_seed = g.param_path('SubDistrictSeed', 'Get Sub District Seed', set={'OutputAttributeName': 'SubDistrictSeed', 'Seed': -1618447870})
        genericuserparameterget = g.param_path('Dividable_district_Limit', set={'Seed': -1618447870})
        debug_roads = g.param('Debug_Roads', 'Debug_Roads', set={'Seed': -1618446397})
        debug_undividable_districts = g.param('Debug_Undividable_districts', 'Debug_Undividable_districts')
        small_medium_threshold = g.param_path('SmallMediumThreshold', 'Small/Medium Threshold', set={'OutputAttributeName': 'SmallMediumThreshold'})
        medium_large_threshold = g.param_path('MediumLargeThreshold', 'Medium/Large Threshold', set={'OutputAttributeName': 'MediumLargeThreshold'})
        small_grid_width = g.param_path('SmallGridWidth', 'Small Grid Width', set={'OutputAttributeName': 'SmallGridWidth'})
        small_grid_length = g.param_path('SmallGridLength', 'Small Grid Length', set={'OutputAttributeName': 'SmallGridLength'})
        large_grid_width = g.param_path('LargeGridWidth', 'Large Grid Width', set={'OutputAttributeName': 'LargeGridWidth'})
        large_grid_length = g.param_path('LargeGridLength', 'Large Grid Length', set={'OutputAttributeName': 'LargeGridLength'})
        debug_district_categories = g.param_path('Debug_DistrictCategories', 'Debug District Categories', set={'OutputAttributeName': 'Debug_DistrictCategories'})
        medium_grid_width = g.param_path('MediumGridWidth', 'Medium Grid Width', set={'OutputAttributeName': 'MediumGridWidth'})
        medium_grid_length = g.param_path('MediumGridLength', 'Medium Grid Length', set={'OutputAttributeName': 'MediumGridLength'})
        metadatamaths = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Position.Z'), 'Operation': 'Set'}, defaults=[D(1)], comment='set to the ground level, regardless of the actor position in Z', InA=get_arteries)
        metadatamaths_2 = g.node('PCGMetadataMathsSettings', set={'InputSource1': sel('$Position.Z'), 'Operation': 'Set'}, defaults=[D(1)], comment='set to the ground level, regardless of the actor position in Z', InA=get_city_shape_spline)
        city_shape = g.declare('City Shape', metadatamaths_2)
        districts = g.sub('Subdivide_Areas_withSpline', 'Districts', settings={'Seed': 1387288479}, PrimaryInput=city_shape, SecondaryInput=metadatamaths)
        # 不生效：set.Seed 被同名 pin 的输入顶掉
        sub_districts = g.sub('Subdivide_Areas_WithRecursiveSplit', 'Sub_districts', set={'Iterations': 1, 'MaxSplitDistancFromCenter': 0.2, 'MinAreaSize': 1000, 'Seed': 7}, settings={'Seed': 1387288479}, PrimaryInput=districts.Areas, Seed=get_sub_district_seed)
        # 不生效：set.Size 被同名 pin 的输入顶掉
        dividable_districts = g.sub('Filter_Areas_BySize', 'Dividable districts', set={'Operator': 'Greater', 'Size': 50000}, settings={'Seed': 1387288479}, PrimaryInput=sub_districts.Areas, Size=genericuserparameterget)
        filter_small_medium_or_large = g.sub('Filter_Areas_BySize', 'Filter: Small | Medium-or-Large', PrimaryInput=dividable_districts.Selected, Size=small_medium_threshold)
        filter_medium_large = g.sub('Filter_Areas_BySize', 'Filter: Medium | Large', PrimaryInput=filter_small_medium_or_large.Selected, Size=medium_large_threshold)
        city_shape_2 = city_shape.use()
        districts_subdividing_splines = g.declare('Districts Subdividing Splines', districts['Subdividing Splines'])
        sub_districts_subdivide_splines = g.declare('Sub Districts Subdivide Splines', sub_districts['Subdivide Splines'])
        districts_subdividing_splines_2 = districts_subdividing_splines.use()
        addtag = g.node('PCGAddTagSettings', set={'Seed': -1617982074, 'TagsToAdd': 'ArteryRoads'}, comment='ARTERY ROADS', In=[city_shape_2, districts_subdividing_splines_2])
        sub_districts_subdivide_splines_2 = sub_districts_subdivide_splines.use()
        addtag_2 = g.node('PCGAddTagSettings', set={'Seed': -1617982074, 'TagsToAdd': 'CollectorRoads'}, comment='COLLECTOR ROADS', In=sub_districts_subdivide_splines_2)
        undividable_districts = g.declare('UnDividable Districts', dividable_districts.Unselected)
        undividable_districts_2 = undividable_districts.use()
        addtag_3 = g.node('PCGAddTagSettings', set={'Seed': -1617982074, 'TagsToAdd': 'UndividableDistricts'}, comment='Undividable Districts', In=undividable_districts_2)
        small_sub_districts = g.declare('Small Sub-Districts', filter_small_medium_or_large.Unselected)
        small_sub_districts_2 = small_sub_districts.use()
        small_district_blocks = g.sub('Subdivide_Areas_withGrid', 'Small District Blocks', PrimaryInput=small_sub_districts_2, GridWidth=small_grid_width, GridLength=small_grid_length)
        small_sub_districts_3 = small_sub_districts.use()
        add_tags = g.node('PCGAddTagSettings', 'Add Tags', set={'TagsToAdd': 'SmallDistricts'}, comment='SMALL DISTRICTS', In=small_sub_districts_3)
        medium_sub_districts = g.declare('Medium Sub-Districts', filter_medium_large.Unselected)
        medium_sub_districts_2 = medium_sub_districts.use()
        # 不生效：set.GridLength 被同名 pin 的输入顶掉
        # 不生效：set.GridWidth 被同名 pin 的输入顶掉
        medium_district_blocks = g.sub('Subdivide_Areas_withGrid', 'Medium District Blocks', set={'GridLength': 6000, 'GridWidth': 12000}, settings={'Seed': 1387288479}, PrimaryInput=medium_sub_districts_2, GridWidth=medium_grid_width, GridLength=medium_grid_length)
        large_sub_districts = g.declare('Large Sub-Districts', filter_medium_large.Selected)
        large_sub_districts_2 = large_sub_districts.use()
        large_district_blocks = g.sub('Subdivide_Areas_withGrid', 'Large District Blocks', PrimaryInput=large_sub_districts_2, GridWidth=large_grid_width, GridLength=large_grid_length)
        medium_sub_districts_3 = medium_sub_districts.use()
        add_tags_2 = g.node('PCGAddTagSettings', 'Add Tags', set={'TagsToAdd': 'MediumDistricts'}, comment='MEDIUM DISTRICTS', In=medium_sub_districts_3)
        large_sub_districts_3 = large_sub_districts.use()
        add_tags_3 = g.node('PCGAddTagSettings', 'Add Tags', set={'TagsToAdd': 'LargeDistricts'}, comment='LARGE DISTRICTS', In=large_sub_districts_3)
        small_sub_districts_4 = small_sub_districts.use()
        branch = g.node('PCGBranchSettings', 'Branch', In=small_sub_districts_4, bOutputToB=debug_district_categories)
        lift_95m_for_debug = g.sub('Transform_Offset', 'Lift +95m for Debug', set={'AbsoluteOffset': True, 'offset': {'X': 0, 'Y': 0, 'Z': 9500}}, PrimaryInput=branch['Output B'])
        small_debug_mesh_red = g.sub('Create_Mesh_Planar', 'Small Debug Mesh (Red)', set={'Material': '/PCGPrimitives/Materials/PCG_DebugRed0.PCG_DebugRed0'}, PrimaryInput=lift_95m_for_debug)
        medium_sub_districts_4 = medium_sub_districts.use()
        branch_2 = g.node('PCGBranchSettings', 'Branch', In=medium_sub_districts_4, bOutputToB=debug_district_categories)
        lift_95m_for_debug_2 = g.sub('Transform_Offset', 'Lift +95m for Debug', set={'AbsoluteOffset': True, 'offset': {'X': 0, 'Y': 0, 'Z': 9500}}, PrimaryInput=branch_2['Output B'])
        medium_debug_mesh_green = g.sub('Create_Mesh_Planar', 'Medium Debug Mesh (Green)', set={'Material': '/PCGPrimitives/Materials/PCG_DebugGreen1.PCG_DebugGreen1'}, PrimaryInput=lift_95m_for_debug_2)
        large_sub_districts_4 = large_sub_districts.use()
        branch_3 = g.node('PCGBranchSettings', 'Branch', In=large_sub_districts_4, bOutputToB=debug_district_categories)
        lift_95m_for_debug_3 = g.sub('Transform_Offset', 'Lift +95m for Debug', set={'AbsoluteOffset': True, 'offset': {'X': 0, 'Y': 0, 'Z': 9500}}, PrimaryInput=branch_3['Output B'])
        large_debug_mesh_blue = g.sub('Create_Mesh_Planar', 'Large Debug Mesh (Blue)', set={'Material': '/PCGPrimitives/Materials/PCG_DebugBlue1.PCG_DebugBlue1'}, PrimaryInput=lift_95m_for_debug_3)
        gather = g.node('PCGGatherSettings', In=[small_district_blocks.Subdividing_splines, medium_district_blocks.Subdividing_splines, large_district_blocks.Subdividing_splines])
        blocks_roads = g.declare('Blocks Roads', gather)
        blocks_roads_2 = blocks_roads.use()
        addtag_4 = g.node('PCGAddTagSettings', set={'Seed': -1617982074, 'TagsToAdd': 'localRoads'}, comment='LOCAL ROADS', In=blocks_roads_2)
        city_shape_3 = city_shape.use()
        districts_subdividing_splines_3 = districts_subdividing_splines.use()
        sub_districts_subdivide_splines_3 = sub_districts_subdivide_splines.use()
        blocks_roads_3 = blocks_roads.use()
        branch_4 = g.node('PCGBranchSettings', set={'Seed': -1618154696}, In=[city_shape_3, districts_subdividing_splines_3, sub_districts_subdivide_splines_3, blocks_roads_3], bOutputToB=debug_roads.Debug_Roads)
        lift_100m_for_debug = g.sub('Transform_Offset', 'Lift +100m for Debug', set={'AbsoluteOffset': True, 'offset': {'X': 0, 'Y': 0, 'Z': 10000}}, PrimaryInput=branch_4['Output B'])
        debug_primitivedata = g.sub('Debug_PrimitiveData', settings={'Seed': -1618237129}, PrimaryInput=lift_100m_for_debug)
        undividable_districts_3 = undividable_districts.use()
        branch_5 = g.node('PCGBranchSettings', set={'Seed': -1618154696}, In=undividable_districts_3, bOutputToB=debug_undividable_districts.Debug_Undividable_districts)
        lift_95m_for_debug_4 = g.sub('Transform_Offset', 'Lift + 95m For Debug', set={'AbsoluteOffset': True, 'offset': {'X': 0, 'Y': 0, 'Z': 9500}}, PrimaryInput=branch_5['Output B'])
        create_mesh_planar = g.sub('Create_Mesh_Planar', PrimaryInput=lift_95m_for_debug_4)
    g.out(addtag_4, addtag, addtag_2, addtag_3, add_tags, add_tags_2, add_tags_3)
    return g
