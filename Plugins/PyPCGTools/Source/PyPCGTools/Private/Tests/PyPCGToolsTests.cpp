#if WITH_DEV_AUTOMATION_TESTS

#include "Dom/JsonObject.h"
#include "Elements/Metadata/PCGMetadataMathsOpElement.h"
#include "Elements/PCGUserParameterGet.h"
#include "Misc/AutomationTest.h"
#include "PCGGraph.h"
#include "PCGNode.h"
#include "PCGSubgraph.h"
#include "PyPCGToolsLibrary.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

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

	UPCGSettings* Settings = nullptr;
	UPCGNode* Node = Graph->AddNodeOfType(UPCGUserParameterGetSettings::StaticClass(), Settings);
	TestEqual(TEXT("Bind"), UPyPCGToolsLibrary::BindUserParameterGetter(Settings, TEXT("Seed")), FString());
	const TSharedPtr<FJsonObject> NodeJson = NodeIR(Graph, Node);
	TestEqual(TEXT("getter_param"), NodeJson->GetStringField(TEXT("getter_param")), FString(TEXT("Seed")));
	TestEqual(TEXT("getter output pin"), NodeJson->GetArrayField(TEXT("outputs"))[0]->AsString(), FString(TEXT("Seed")));
	TestNotEqual(TEXT("unknown param refused"), UPyPCGToolsLibrary::BindUserParameterGetter(Settings, TEXT("Nope")), FString());
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
			TestEqual(TEXT("exact value"), Entry->GetNumberField(TEXT("value")), -1820.4246063232422);
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
	TestEqual(TEXT("offset.Z exact"), Overrides->GetObjectField(TEXT("offset"))->GetNumberField(TEXT("Z")), -1820.4246063232422);
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

#endif // WITH_DEV_AUTOMATION_TESTS
