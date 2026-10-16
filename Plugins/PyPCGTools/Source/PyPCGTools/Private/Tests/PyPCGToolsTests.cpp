#if WITH_DEV_AUTOMATION_TESTS

#include "Data/PCGPolygon2DData.h"
#include "Data/PCGSplineData.h"
#include "Dom/JsonObject.h"
#include "Elements/Metadata/PCGMetadataMathsOpElement.h"
#include "Elements/PCGUserParameterGet.h"
#include "Misc/AutomationTest.h"
#include "PCGGraph.h"
#include "PCGNode.h"
#include "PCGPin.h"
#include "PCGSubgraph.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "PyPCGToolsLibrary.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace PyPCGToolsTests
{
	const TCHAR* OffsetPath = TEXT("/PCGPrimitives/Primitives/Transform/Transform_Offset.Transform_Offset");
	const TCHAR* ByRefPath = TEXT("/PCGPrimitives/Primitives/Get/Get_ActorDataByRef.Get_ActorDataByRef");

	UPCGGraph* NewGraph()
	{
		return NewObject<UPCGGraph>(GetTransientPackage(), NAME_None, RF_Transient);
	}

	TSharedPtr<FJsonObject> Parse(const FString& Text)
	{
		TSharedPtr<FJsonObject> Object;
		FJsonSerializer::Deserialize(TJsonReaderFactory<TCHAR>::Create(Text), Object);
		return Object;
	}

	TSharedPtr<FJsonObject> NodeIR(UPCGGraph* Graph, const UPCGNode* Node)
	{
		const TSharedPtr<FJsonObject> IR = Parse(UPyPCGToolsLibrary::ExportGraphIR(Graph));
		for (const TSharedPtr<FJsonValue>& Value : IR->GetArrayField(TEXT("nodes")))
		{
			if (Value->AsObject()->GetStringField(TEXT("name")) == Node->GetName())
			{
				return Value->AsObject();
			}
		}
		return nullptr;
	}

	// A field of an exported param's hierarchy Common entry, as text ("" when absent).
	FString CommonField(const TSharedPtr<FJsonObject>& Param, const TCHAR* Field)
	{
		const TSharedPtr<FJsonObject>* Hier = nullptr;
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (!Param->TryGetObjectField(TEXT("hier_meta"), Hier) || !(*Hier)->TryGetArrayField(TEXT("Values"), Values))
		{
			return FString();
		}
		for (const TSharedPtr<FJsonValue>& Value : *Values)
		{
			const TSharedPtr<FJsonObject> Entry = Value->AsObject();
			FString Type;
			if (Entry->TryGetStringField(TEXT("_structType"), Type) && Type.EndsWith(TEXT("PropertyBagPropertyMetadata_Common")))
			{
				// Check the JSON type first: TryGetBoolField also converts any string to a bool.
				const TSharedPtr<FJsonValue> Field_ = Entry->TryGetField(Field);
				if (!Field_.IsValid())
				{
					return FString();
				}
				if (Field_->Type == EJson::Boolean)
				{
					return Field_->AsBool() ? TEXT("true") : TEXT("false");
				}
				return Field_->AsString();
			}
		}
		return FString();
	}

	// An exported param's meta object, condensed JSON with keys in stored order.
	FString MetaJson(const TSharedPtr<FJsonObject>& Param)
	{
		FString Out;
		const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
			TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
		FJsonSerializer::Serialize(Param->GetObjectField(TEXT("meta")).ToSharedRef(), Writer);
		return Out;
	}

	UPCGSubgraphSettings* AddSubgraph(UPCGGraph* Graph, const TCHAR* Path, UPCGNode*& OutNode)
	{
		UPCGSettings* Settings = nullptr;
		OutNode = Graph->AddNodeOfType(UPCGSubgraphSettings::StaticClass(), Settings);
		UPCGSubgraphSettings* Subgraph = CastChecked<UPCGSubgraphSettings>(Settings);
		Subgraph->SetSubgraph(LoadObject<UPCGGraph>(nullptr, Path));
		return Subgraph;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsUserParameters, "PyPCGTools.UserParameters",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsUserParameters::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGGraph* Graph = NewGraph();
	const FString Error = UPyPCGToolsLibrary::SetGraphUserParameters(Graph, TEXT(R"({"params":[
		{"name":"Ratio","type":"Double","container":"None","type_object":"","meta":{},"value":0.9,"category":"Road Parameters","tooltip":"a tip"},
		{"name":"Seed","type":"Int32","container":"None","type_object":"","meta":{},"value":7,"category":"","tooltip":""}]})"));
	TestEqual(TEXT("SetGraphUserParameters"), Error, FString());
	const TArray<TSharedPtr<FJsonValue>> Params = Parse(UPyPCGToolsLibrary::ExportGraphIR(Graph))->GetArrayField(TEXT("params"));
	if (!TestEqual(TEXT("param count"), Params.Num(), 2))
	{
		return false;
	}
	TestEqual(TEXT("Ratio value"), Params[0]->AsObject()->GetNumberField(TEXT("value")), 0.9);
	TestEqual(TEXT("Ratio category"), Params[0]->AsObject()->GetStringField(TEXT("category")), FString(TEXT("Road Parameters")));
	TestEqual(TEXT("Seed value"), Params[1]->AsObject()->GetNumberField(TEXT("value")), 7.0);
	TestEqual(TEXT("Ratio panel tooltip"), CommonField(Params[0]->AsObject(), TEXT("Tooltip")), FString(TEXT("a tip")));

	// Ruling T7a: descriptor metadata round-trips verbatim (key spelling included); the panel's
	// tooltip and advanced flag are set in the hierarchy from their own fields.
	UPCGGraph* MetaGraph = NewGraph();
	TestEqual(TEXT("SetGraphUserParameters meta"), UPyPCGToolsLibrary::SetGraphUserParameters(MetaGraph, TEXT(R"({"params":[
		{"name":"Lower","type":"Float","container":"None","type_object":"","meta":{"Tooltip":"lower-t tip"},"value":1,"category":"Cat"},
		{"name":"Upper","type":"Float","container":"None","type_object":"","meta":{"ToolTip":"upper-T tip"},"value":2,"category":"","tooltip":"panel tip","advanced":true}]})")), FString());
	const TSharedPtr<FJsonObject> MetaIR = Parse(UPyPCGToolsLibrary::ExportGraphIR(MetaGraph));
	const TArray<TSharedPtr<FJsonValue>> MetaParams = MetaIR->GetArrayField(TEXT("params"));
	if (!TestEqual(TEXT("meta param count"), MetaParams.Num(), 2))
	{
		return false;
	}
	const TSharedPtr<FJsonObject> Lower = MetaParams[0]->AsObject();
	const TSharedPtr<FJsonObject> Upper = MetaParams[1]->AsObject();
	// Exactly the input: the Category key used to build the hierarchy is not left in the meta.
	TestEqual(TEXT("lower meta verbatim"), MetaJson(Lower), FString(TEXT(R"({"Tooltip":"lower-t tip"})")));
	TestEqual(TEXT("upper meta verbatim"), MetaJson(Upper), FString(TEXT(R"({"ToolTip":"upper-T tip"})")));
	TestEqual(TEXT("lower category"), Lower->GetStringField(TEXT("category")), FString(TEXT("Cat")));
	TestEqual(TEXT("lower panel tooltip"), CommonField(Lower, TEXT("Tooltip")), FString());
	TestEqual(TEXT("upper panel tooltip"), CommonField(Upper, TEXT("Tooltip")), FString(TEXT("panel tip")));
	TestEqual(TEXT("upper advanced"), CommonField(Upper, TEXT("bAdvanced")), FString(TEXT("true")));
	TestEqual(TEXT("lower not advanced"), CommonField(Lower, TEXT("bAdvanced")), FString(TEXT("false")));

	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(UPCGUserParameterGetSettings::StaticClass(), Settings);
	TestEqual(TEXT("Bind"), UPyPCGToolsLibrary::BindUserParameterGetter(Settings, TEXT("Seed")), FString());
	const TSharedPtr<FJsonObject> NodeJson = NodeIR(Graph, Node);
	TestEqual(TEXT("getter_param"), NodeJson->GetStringField(TEXT("getter_param")), FString(TEXT("Seed")));
	TestTrue(TEXT("getter_bound"), NodeJson->GetBoolField(TEXT("getter_bound")));
	TestEqual(TEXT("getter output pin"), NodeJson->GetArrayField(TEXT("outputs"))[0]->AsString(), FString(TEXT("Seed")));
	TestNotEqual(TEXT("unknown param refused"), UPyPCGToolsLibrary::BindUserParameterGetter(Settings, TEXT("Nope")), FString());

	UPCGSettings* LowerSettings = nullptr;
	UPCGNode* LowerNode = Graph->AddNodeOfType(UPCGUserParameterGetSettings::StaticClass(), LowerSettings);
	TestEqual(TEXT("Bind lowercase"), UPyPCGToolsLibrary::BindUserParameterGetter(LowerSettings, TEXT("seed")), FString());
	const TSharedPtr<FJsonObject> LowerNodeJson = NodeIR(Graph, LowerNode);
	TestEqual(TEXT("lowercase getter_param"), LowerNodeJson->GetStringField(TEXT("getter_param")), FString(TEXT("seed")));
	TestTrue(TEXT("lowercase getter_bound"), LowerNodeJson->GetBoolField(TEXT("getter_bound")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsPinDefaults, "PyPCGTools.PinDefaults",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsPinDefaults::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGGraph* Graph = NewGraph();
	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(UPCGMetadataMathsSettings::StaticClass(), Settings);
	TestEqual(TEXT("index 1 value"), UPyPCGToolsLibrary::SetPinDefaultValue(Settings, 1, TEXT("Double"), TEXT(R"({"v":-1820.4246063232422})"), true, true), FString());
	TestEqual(TEXT("index 0 activate only"), UPyPCGToolsLibrary::SetPinDefaultValue(Settings, 0, FString(), FString(), false, true), FString());
	TestNotEqual(TEXT("index 9 refused"), UPyPCGToolsLibrary::SetPinDefaultValue(Settings, 9, FString(), FString(), false, true), FString());
	// A type the pin cannot hold must be refused, not silently written into the old-typed property.
	TestNotEqual(TEXT("impossible type refused"), UPyPCGToolsLibrary::SetPinDefaultValue(Settings, 1, TEXT("Transform"), TEXT(R"({"v":{"X":0,"Y":0,"Z":0}})"), true, true), FString());
	const TArray<TSharedPtr<FJsonValue>> Defaults = NodeIR(Graph, Node)->GetArrayField(TEXT("pin_defaults"));
	bool bSaw0 = false;
	bool bSaw1 = false;
	for (const TSharedPtr<FJsonValue>& Value : Defaults)
	{
		const TSharedPtr<FJsonObject> Entry = Value->AsObject();
		const int32 Index = static_cast<int32>(Entry->GetNumberField(TEXT("index")));
		if (Index == 0)
		{
			bSaw0 = Entry->GetBoolField(TEXT("activated"));
		}
		if (Index == 1)
		{
			bSaw1 = Entry->GetBoolField(TEXT("activated"));
			TestEqual(TEXT("type"), Entry->GetStringField(TEXT("type")), FString(TEXT("Double")));
			// Exact: the default tolerance (UE_KINDA_SMALL_NUMBER) would pass a 6-decimal round trip.
			TestEqual(TEXT("exact value"), Entry->GetNumberField(TEXT("value")), -1820.4246063232422, 0.0);
		}
	}
	TestTrue(TEXT("index 0 activated"), bSaw0);
	TestTrue(TEXT("index 1 activated"), bSaw1);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsInstanceParameters, "PyPCGTools.InstanceParameters",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsInstanceParameters::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGGraph* Graph = NewGraph();
	UPCGNode* Node = nullptr;
	UPCGSubgraphSettings* Offset = AddSubgraph(Graph, OffsetPath, Node);
	UPCGGraphInstance* Instance = Offset->SubgraphInstance;
	if (!TestNotNull(TEXT("instance"), Instance))
	{
		return false;
	}
	TestEqual(TEXT("offset"), UPyPCGToolsLibrary::SetInstanceParameter(Instance, TEXT("offset"), TEXT(R"({"v":{"X":0,"Y":0,"Z":-1820.4246063232422}})")), FString());

	// An override equal to the subgraph's own default must stay overridden (Review Focus 2).
	bool bParentAbsolute = false;
	// Hold the parsed object in a local: GetArrayField returns a reference into it, and a reference
	// bound directly to the temporary from Parse would dangle once the temporary is destroyed.
	const TSharedPtr<FJsonObject> ParentIR = Parse(UPyPCGToolsLibrary::ExportGraphIR(LoadObject<UPCGGraph>(nullptr, OffsetPath)));
	for (const TSharedPtr<FJsonValue>& Value : ParentIR->GetArrayField(TEXT("params")))
	{
		if (Value->AsObject()->GetStringField(TEXT("name")) == TEXT("AbsoluteOffset"))
		{
			bParentAbsolute = Value->AsObject()->GetBoolField(TEXT("value"));
		}
	}
	const FString SameAsParent = bParentAbsolute ? TEXT(R"({"v":true})") : TEXT(R"({"v":false})");
	TestEqual(TEXT("AbsoluteOffset"), UPyPCGToolsLibrary::SetInstanceParameter(Instance, TEXT("AbsoluteOffset"), SameAsParent), FString());

	const TSharedPtr<FJsonObject> Overrides = Parse(UPyPCGToolsLibrary::ExportInstanceOverrides(Instance));
	// Exact: the default tolerance (UE_KINDA_SMALL_NUMBER) would pass a 6-decimal round trip.
	TestEqual(TEXT("offset.Z exact"), Overrides->GetObjectField(TEXT("offset"))->GetNumberField(TEXT("Z")), -1820.4246063232422, 0.0);
	TestTrue(TEXT("default-valued override kept"), Overrides->HasField(TEXT("AbsoluteOffset")));
	TestEqual(TEXT("only the two set"), Overrides->Values.Num(), 2);
	TestNotEqual(TEXT("unknown param refused"), UPyPCGToolsLibrary::SetInstanceParameter(Instance, TEXT("Nope"), TEXT(R"({"v":1})")), FString());

	UPCGSubgraphSettings* ByRef = AddSubgraph(Graph, ByRefPath, Node);
	TestEqual(TEXT("ActorReferences"), UPyPCGToolsLibrary::SetInstanceParameter(ByRef->SubgraphInstance, TEXT("ActorReferences"),
		TEXT(R"({"v":["/Game/X.X:PersistentLevel.A"]})")), FString());
	const TArray<TSharedPtr<FJsonValue>> Refs = Parse(UPyPCGToolsLibrary::ExportInstanceOverrides(ByRef->SubgraphInstance))->GetArrayField(TEXT("ActorReferences"));
	TestEqual(TEXT("ActorReferences round trip"), Refs.Num() == 1 ? Refs[0]->AsString() : FString(), FString(TEXT("/Game/X.X:PersistentLevel.A")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsCommentsAndBoxes, "PyPCGTools.CommentsAndBoxes",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsCommentsAndBoxes::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGGraph* Graph = NewGraph();
	TestEqual(TEXT("boxes"), UPyPCGToolsLibrary::SetGraphCommentBoxes(Graph, TEXT(R"({"boxes":[{"NodePosX":10,"NodePosY":20,"NodeWidth":300,"NodeHeight":200,"NodeComment":"1 INPUT","FontSize":24,"CommentColor":{"R":0.15,"G":0.35,"B":0.6,"A":1}}]})")), FString());
	const TArray<TSharedPtr<FJsonValue>> Boxes = Parse(UPyPCGToolsLibrary::ExportGraphIR(Graph))->GetArrayField(TEXT("comment_boxes"));
	if (!TestEqual(TEXT("box count"), Boxes.Num(), 1))
	{
		return false;
	}
	TestEqual(TEXT("box text"), Boxes[0]->AsObject()->GetStringField(TEXT("NodeComment")), FString(TEXT("1 INPUT")));
	TestEqual(TEXT("box font"), Boxes[0]->AsObject()->GetNumberField(TEXT("FontSize")), 24.0);
	TestFalse(TEXT("no GUID exported"), Boxes[0]->AsObject()->HasField(TEXT("GUID")));

	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(UPCGMetadataMathsSettings::StaticClass(), Settings);
	// A fresh node has the default white title, so no title_color is emitted at all.
	TestFalse(TEXT("default white title has no title_color"), NodeIR(Graph, Node)->HasField(TEXT("title_color")));
	TestEqual(TEXT("comment"), UPyPCGToolsLibrary::SetNodeComment(Node, TEXT("hello"), true, false), FString());
	const TSharedPtr<FJsonObject> NodeJson = NodeIR(Graph, Node);
	TestEqual(TEXT("comment text"), NodeJson->GetStringField(TEXT("comment")), FString(TEXT("hello")));
	TestTrue(TEXT("bubble visible"), NodeJson->GetBoolField(TEXT("bubble_visible")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsSetProperties, "PyPCGTools.SetProperties",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsSetProperties::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGGraph* Graph = NewGraph();
	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(UPCGMetadataMathsSettings::StaticClass(), Settings);
	TestEqual(TEXT("set"), UPyPCGToolsLibrary::SetPropertiesJson(Settings, TEXT(R"({"Operation":"Set","InputSource1":"PCGBegin($Position.Z)PCGEnd"})")), FString());
	const TSharedPtr<FJsonObject> Json = NodeIR(Graph, Node)->GetObjectField(TEXT("settings"));
	TestEqual(TEXT("Operation"), Json->GetStringField(TEXT("Operation")), FString(TEXT("Set")));
	TestEqual(TEXT("InputSource1"), Json->GetStringField(TEXT("InputSource1")), FString(TEXT("PCGBegin($Position.Z)PCGEnd")));
	TestTrue(TEXT("unknown property refused"), UPyPCGToolsLibrary::SetPropertiesJson(Settings, TEXT(R"({"Nope":1})")).Contains(TEXT("no property")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsProtectedMounts, "PyPCGTools.ProtectedMounts",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsProtectedMounts::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGGraph* Primitive = LoadObject<UPCGGraph>(nullptr, OffsetPath);
	if (!TestNotNull(TEXT("primitive loads"), Primitive))
	{
		return false;
	}
	const int32 Before = Primitive->GetCommentNodes().Num();
	TestNotEqual(TEXT("boxes refused"), UPyPCGToolsLibrary::SetGraphCommentBoxes(Primitive, TEXT(R"({"boxes":[]})")), FString());
	TestEqual(TEXT("boxes untouched"), Primitive->GetCommentNodes().Num(), Before);
	TestNotEqual(TEXT("properties refused"), UPyPCGToolsLibrary::SetPropertiesJson(Primitive, TEXT("{}")), FString());
	TestNotEqual(TEXT("params refused"), UPyPCGToolsLibrary::SetGraphUserParameters(Primitive, TEXT(R"({"params":[]})")), FString());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsPolygon2D, "PyPCGTools.Polygon2D",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsPolygon2D::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	// A 10 m square at z 100 with a 2 m square hole. The outer ring is given clockwise; it must
	// come back counter-clockwise, in a frame centred on the ring like CreatePolygon2D's.
	UPCGPolygon2DData* Data = UPyPCGToolsLibrary::MakePolygon2DData(TEXT(R"({"outer":[[0,0,100],[0,1000,100],[1000,1000,100],[1000,0,100]],
		"holes":[[[400,400,100],[600,400,100],[600,600,100],[400,600,100]]]})"));
	if (!TestNotNull(TEXT("polygon made"), Data))
	{
		return false;
	}
	TestTrue(TEXT("frame origin at the centroid"), Data->GetTransform().GetLocation().Equals(FVector(500, 500, 100), 1e-6));
	TestFalse(TEXT("outer counter-clockwise"), Data->GetPolygon().OuterIsClockwise());
	TestEqual(TEXT("hole count"), Data->GetPolygon().GetHoles().Num(), 1);
	TestEqual(TEXT("area"), Data->GetPolygon().SignedArea(), 1000.0 * 1000.0 - 200.0 * 200.0, 1e-6);

	const TSharedPtr<FJsonObject> Back = Parse(UPyPCGToolsLibrary::Polygon2DToJson(Data));
	const TArray<TSharedPtr<FJsonValue>> Outer = Back->GetArrayField(TEXT("outer"));
	TestEqual(TEXT("outer vertex count"), Outer.Num(), 4);
	for (const FVector Corner : {FVector(0, 0, 100), FVector(1000, 0, 100), FVector(1000, 1000, 100), FVector(0, 1000, 100)})
	{
		bool bFound = false;
		for (const TSharedPtr<FJsonValue>& Value : Outer)
		{
			const TArray<TSharedPtr<FJsonValue>> Xyz = Value->AsArray();
			bFound |= FVector(Xyz[0]->AsNumber(), Xyz[1]->AsNumber(), Xyz[2]->AsNumber()).Equals(Corner, 1e-6);
		}
		TestTrue(*FString::Printf(TEXT("corner %s round-trips"), *Corner.ToString()), bFound);
	}
	TestEqual(TEXT("hole round-trips"), Back->GetArrayField(TEXT("holes")).Num(), 1);
	TestNull(TEXT("two vertices refused"), UPyPCGToolsLibrary::MakePolygon2DData(TEXT(R"({"outer":[[0,0,0],[1,0,0]]})")));
	TestNull(TEXT("bad JSON refused"), UPyPCGToolsLibrary::MakePolygon2DData(TEXT("{")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsSplineJson, "PyPCGTools.SplineJson",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsSplineJson::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UPCGSplineData* Spline = NewObject<UPCGSplineData>(GetTransientPackage());
	TArray<FSplinePoint> Points;
	const FVector Corners[] = {FVector(0, 0, 0), FVector(1000, 0, 0), FVector(1000, 500, 0), FVector(0, 500, 0)};
	for (int32 Index = 0; Index < 4; ++Index)
	{
		FSplinePoint& Point = Points.AddDefaulted_GetRef();
		Point.InputKey = static_cast<float>(Index);
		Point.Position = Corners[Index];
		Point.Type = ESplinePointType::Linear;
	}
	Spline->K2_Initialize(Points, /*bInClosedLoop=*/true, FTransform(FVector(100, 0, 0)), {});
	const TSharedPtr<FJsonObject> Json = Parse(UPyPCGToolsLibrary::SplineDataToJson(Spline, 1.0f));
	TestTrue(TEXT("closed"), Json->GetBoolField(TEXT("closed")));
	const TArray<TSharedPtr<FJsonValue>> Control = Json->GetArrayField(TEXT("control"));
	if (!TestEqual(TEXT("control points"), Control.Num(), 4))
	{
		return false;
	}
	const TArray<TSharedPtr<FJsonValue>> P0 = Control[0]->AsObject()->GetArrayField(TEXT("p"));
	TestTrue(TEXT("control point in world space"), FVector(P0[0]->AsNumber(), P0[1]->AsNumber(), P0[2]->AsNumber()).Equals(FVector(100, 0, 0), 1e-6));
	TestEqual(TEXT("linear type"), static_cast<int32>(Control[0]->AsObject()->GetNumberField(TEXT("type"))), 0);
	const TArray<TSharedPtr<FJsonValue>> Polyline = Json->GetArrayField(TEXT("polyline"));
	for (const FVector& Corner : Corners)
	{
		bool bFound = false;
		for (const TSharedPtr<FJsonValue>& Value : Polyline)
		{
			const TArray<TSharedPtr<FJsonValue>> Xyz = Value->AsArray();
			bFound |= FVector(Xyz[0]->AsNumber(), Xyz[1]->AsNumber(), Xyz[2]->AsNumber()).Equals(Corner + FVector(100, 0, 0), 1e-3);
		}
		TestTrue(*FString::Printf(TEXT("polyline has corner %s"), *Corner.ToString()), bFound);
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPyPCGToolsDynamicPins, "PyPCGTools.DynamicPins",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FPyPCGToolsDynamicPins::RunTest(const FString& Parameters)
{
	using namespace PyPCGToolsTests;
	UClass* PythonNode = FindObject<UClass>(nullptr, TEXT("/Script/PCGPythonInteropEditor.PCGPythonDataProcessorSettings"));
	if (!TestNotNull(TEXT("PCGPythonInterop is loaded"), PythonNode))
	{
		return false;
	}
	UPCGGraph* Graph = NewGraph();
	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(PythonNode, Settings);
	TestEqual(TEXT("set pins"), UPyPCGToolsLibrary::SetDynamicPinLabels(Settings,
		TArray<FString>({TEXT("Params"), TEXT("City")}), TArray<FString>({TEXT("Areas"), TEXT("Roads")})), FString());
	TArray<FString> In, Out;
	for (const TObjectPtr<UPCGPin>& Pin : Node->GetInputPins())
	{
		In.Add(Pin->Properties.Label.ToString());
	}
	for (const TObjectPtr<UPCGPin>& Pin : Node->GetOutputPins())
	{
		Out.Add(Pin->Properties.Label.ToString());
	}
	TestTrue(TEXT("Params pin"), In.Contains(TEXT("Params")));
	TestTrue(TEXT("City pin"), In.Contains(TEXT("City")));
	TestFalse(TEXT("default Input pin gone"), In.Contains(TEXT("Input")));
	TestTrue(TEXT("Areas pin"), Out.Contains(TEXT("Areas")));
	TestTrue(TEXT("Roads pin"), Out.Contains(TEXT("Roads")));
	TestFalse(TEXT("default Output pin gone"), Out.Contains(TEXT("Output")));
	TestNotEqual(TEXT("duplicate labels refused"), UPyPCGToolsLibrary::SetDynamicPinLabels(Settings,
		TArray<FString>({TEXT("A"), TEXT("A")}), TArray<FString>()), FString());
	UPCGSettings* Maths = nullptr;
	Graph->AddNodeOfType(UPCGMetadataMathsSettings::StaticClass(), Maths);
	TestNotEqual(TEXT("node without dynamic pins refused"), UPyPCGToolsLibrary::SetDynamicPinLabels(Maths,
		TArray<FString>({TEXT("A")}), TArray<FString>()), FString());
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
