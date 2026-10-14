#include "PyPCGToolsLibrary.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Editor/IPCGEditorModule.h"
#include "Editor/PCGGraphComment.h"
#include "Elements/Metadata/PCGMetadataOpElementBase.h"
#include "Engine/World.h"
#include "Elements/PCGUserParameterGet.h"
#include "Helpers/PCGPropertyHelpers.h"
#include "JsonObjectConverter.h"
#include "Metadata/PCGDefaultValueInterface.h"
#include "Metadata/PCGMetadataCommon.h"
#include "PCGEdge.h"
#include "PCGGraph.h"
#include "PCGNode.h"
#include "PCGPin.h"
#include "PCGSettings.h"
#include "PCGSubgraph.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "StructUtils/PropertyBag.h"
#include "UObject/UnrealType.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PyPCGToolsLibrary)

namespace PyPCGTools::Private
{
	// Transient and deprecated properties are not part of a graph's saved state.
	constexpr int64 SkipFlags = CPF_Transient | CPF_Deprecated;
	constexpr EJsonObjectConversionFlags ConversionFlags = EJsonObjectConversionFlags::SkipStandardizeCase;
	// A value the JSON converter cannot express travels as UE property text behind this prefix.
	const FString TextPrefix = TEXT("$text:");

	using FHierarchyEntry = TPair<FString, TSharedPtr<FJsonValue>>;

	bool IsProtected(const UObject* Object, FString& OutError)
	{
		// A level object (anything with a world in its outer chain) is never saved by this tool, and
		// its package may sit under /CitySamplePCG/__ExternalActors__/. Allow it before the mounts.
		if (Object->GetTypedOuter<UWorld>() != nullptr)
		{
			return false;
		}
		const FString Package = Object->GetOutermost()->GetName();
		if (Package.StartsWith(TEXT("/Engine/Transient")))
		{
			return false;
		}
		for (const TCHAR* Root : {TEXT("/CitySamplePCG/"), TEXT("/PCGPrimitives"), TEXT("/Engine/")})
		{
			if (Package.StartsWith(Root))
			{
				OutError = FString::Printf(TEXT("refused: %s is under the protected mount %s"), *Package, Root);
				return true;
			}
		}
		return false;
	}

	FString Write(const TSharedRef<FJsonObject>& Object)
	{
		FString Out;
		const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
			TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
		FJsonSerializer::Serialize(Object, Writer);
		return Out;
	}

	FString WriteValue(const TSharedPtr<FJsonValue>& Value)
	{
		const TSharedRef<FJsonObject> Wrap = MakeShared<FJsonObject>();
		Wrap->SetField(TEXT("v"), Value.IsValid() ? Value : MakeShared<FJsonValueNull>());
		return Write(Wrap);
	}

	TSharedPtr<FJsonObject> ParseObject(const FString& Text, FString& OutError)
	{
		TSharedPtr<FJsonObject> Object;
		const TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(Text);
		if (!FJsonSerializer::Deserialize(Reader, Object) || !Object.IsValid())
		{
			OutError = FString::Printf(TEXT("bad JSON: %s"), *Text.Left(200));
			return nullptr;
		}
		return Object;
	}

	TSharedPtr<FJsonValue> NumberArray(std::initializer_list<double> Values)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const double Value : Values)
		{
			Out.Add(MakeShared<FJsonValueNumber>(Value));
		}
		return MakeShared<FJsonValueArray>(Out);
	}

	// Property is const here because FPropertyBagPropertyDesc::CachedProperty is a const FProperty*;
	// the JSON converter still takes a non-const FProperty* for a read-only conversion, hence the cast.
	TSharedPtr<FJsonValue> PropertyToJson(const FProperty* Property, const void* Value, UObject* Owner)
	{
		TSharedPtr<FJsonValue> Json = FJsonObjectConverter::UPropertyToJsonValue(const_cast<FProperty*>(Property), Value, 0, SkipFlags, nullptr, nullptr, ConversionFlags);
		if (!Json.IsValid())
		{
			FString Text;
			Property->ExportTextItem_Direct(Text, Value, nullptr, Owner, PPF_None);
			Json = MakeShared<FJsonValueString>(TextPrefix + Text);
		}
		return Json;
	}

	bool JsonToProperty(const TSharedPtr<FJsonValue>& Value, const FProperty* Property, void* Data, UObject* Owner, FString& OutError)
	{
		FString Text;
		if (Value.IsValid() && Value->Type == EJson::String && Value->TryGetString(Text) && Text.StartsWith(TextPrefix))
		{
			if (!Property->ImportText_Direct(*Text.Mid(TextPrefix.Len()), Data, Owner, PPF_None))
			{
				OutError = FString::Printf(TEXT("%s: cannot import text %s"), *Property->GetName(), *Text.Left(120));
				return false;
			}
			return true;
		}
		FText Fail;
		if (!FJsonObjectConverter::JsonValueToUProperty(Value, const_cast<FProperty*>(Property), Data, 0, 0, false, &Fail))
		{
			OutError = FString::Printf(TEXT("%s: %s"), *Property->GetName(), *Fail.ToString());
			return false;
		}
		return true;
	}

	TSharedRef<FJsonObject> ObjectToJson(UObject* Object, const TSet<FString>& Strip)
	{
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		for (TFieldIterator<FProperty> It(Object->GetClass()); It; ++It)
		{
			FProperty* Property = *It;
			const FString Name = Property->GetName();
			if (Property->HasAnyPropertyFlags(SkipFlags) || Strip.Contains(Name))
			{
				continue;
			}
			Out->SetField(Name, PropertyToJson(Property, Property->ContainerPtrToValuePtr<void>(Object), Object));
		}
		return Out;
	}

	// Properties whose JSON differs from the class default object.
	TSharedRef<FJsonObject> NonDefault(UObject* Object, const TSet<FString>& Strip)
	{
		const TSharedRef<FJsonObject> Full = ObjectToJson(Object, Strip);
		const TSharedRef<FJsonObject> Default = ObjectToJson(Object->GetClass()->GetDefaultObject(), Strip);
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		for (const auto& Field : Full->Values)
		{
			const TSharedPtr<FJsonValue>* Base = Default->Values.Find(Field.Key);
			if (!Base || WriteValue(*Base) != WriteValue(Field.Value))
			{
				Out->SetField(Field.Key, Field.Value);
			}
		}
		return Out;
	}

	void RefreshNode(UObject* Object)
	{
		Object->PostEditChange();
		if (UPCGNode* Node = Cast<UPCGNode>(Object->GetOuter()))
		{
			Node->UpdateAfterSettingsChangeDuringCreation();
		}
	}

	// UPCGMetadataSettingsBase::DefaultValues is private; reach its bag and activation set by reflection.
	FInstancedPropertyBag* DefaultValueBag(UObject* Settings, TSet<FName>** OutActivated)
	{
		*OutActivated = nullptr;
		const FStructProperty* Container = FindFProperty<FStructProperty>(Settings->GetClass(), TEXT("DefaultValues"));
		if (!Container)
		{
			return nullptr;
		}
		void* Data = Container->ContainerPtrToValuePtr<void>(Settings);
		if (const FSetProperty* Activated = FindFProperty<FSetProperty>(Container->Struct, TEXT("ActivatedProperties")))
		{
			*OutActivated = Activated->ContainerPtrToValuePtr<TSet<FName>>(Data);
		}
		const FStructProperty* Bag = FindFProperty<FStructProperty>(Container->Struct, TEXT("PropertyBag"));
		return Bag ? Bag->ContainerPtrToValuePtr<FInstancedPropertyBag>(Data) : nullptr;
	}

	TArray<TSharedPtr<FJsonValue>> ExportPinDefaults(UPCGSettings* Settings)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		TSet<FName>* Activated = nullptr;
		FInstancedPropertyBag* Bag = DefaultValueBag(Settings, &Activated);
		TSet<FName> Names;
		if (Activated)
		{
			Names.Append(*Activated);
		}
		if (const UPropertyBag* BagStruct = Bag ? Bag->GetPropertyBagStruct() : nullptr)
		{
			for (const FPropertyBagPropertyDesc& Desc : BagStruct->GetPropertyDescs())
			{
				Names.Add(Desc.Name);
			}
		}
		TArray<FName> Sorted = Names.Array();
		Sorted.Sort(FNameLexicalLess());
		for (const FName Name : Sorted)
		{
			const FString Text = Name.ToString();
			if (!Text.StartsWith(TEXT("DefaultValue")))
			{
				continue;
			}
			const TSharedRef<FJsonObject> Entry = MakeShared<FJsonObject>();
			Entry->SetNumberField(TEXT("index"), FCString::Atoi(*Text.Mid(12)) - 1);
			Entry->SetStringField(TEXT("prop"), Text);
			Entry->SetBoolField(TEXT("activated"), Activated && Activated->Contains(Name));
			const FPropertyBagPropertyDesc* Desc = Bag ? Bag->FindPropertyDescByName(Name) : nullptr;
			if (Desc && Desc->CachedProperty)
			{
				const EPCGMetadataTypes Type = PCGPropertyHelpers::GetMetadataTypeFromProperty(Desc->CachedProperty);
				Entry->SetStringField(TEXT("type"), StaticEnum<EPCGMetadataTypes>()->GetNameStringByValue(static_cast<int64>(Type)));
				const void* Value = Desc->CachedProperty->ContainerPtrToValuePtr<void>(Bag->GetValue().GetMemory());
				Entry->SetField(TEXT("value"), PropertyToJson(Desc->CachedProperty, Value, Settings));
			}
			else
			{
				Entry->SetField(TEXT("type"), MakeShared<FJsonValueNull>());
				Entry->SetField(TEXT("value"), MakeShared<FJsonValueNull>());
			}
			Out.Add(MakeShared<FJsonValueObject>(Entry));
		}
		return Out;
	}

	TSharedRef<FJsonObject> ExportOverrides(UPCGGraphInstance* Instance)
	{
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		const FInstancedPropertyBag& Bag = Instance->ParametersOverrides.Parameters;
		const UPropertyBag* BagStruct = Bag.GetPropertyBagStruct();
		if (!BagStruct)
		{
			return Out;
		}
		for (const FPropertyBagPropertyDesc& Desc : BagStruct->GetPropertyDescs())
		{
			if (Desc.CachedProperty && Instance->IsPropertyOverridden(Desc.CachedProperty))
			{
				const void* Value = Desc.CachedProperty->ContainerPtrToValuePtr<void>(Bag.GetValue().GetMemory());
				Out->SetField(Desc.Name.ToString(), PropertyToJson(Desc.CachedProperty, Value, Instance));
			}
		}
		return Out;
	}

	// The parameter hierarchy uses StructUtilsEditor / DataHierarchyEditor classes whose members are not
	// exported; walk it generically by property name.
	void CollectHierarchy(UObject* Element, const FString& Chain, TMap<FGuid, FHierarchyEntry>& Out)
	{
		if (!Element)
		{
			return;
		}
		UClass* Class = Element->GetClass();
		FString Here = Chain;
		if (const FNameProperty* Category = FindFProperty<FNameProperty>(Class, TEXT("Category")))
		{
			const FString Name = Category->GetPropertyValue_InContainer(Element).ToString();
			Here = Chain.IsEmpty() ? Name : Chain + TEXT("|") + Name;
		}
		if (FStructProperty* Metadata = FindFProperty<FStructProperty>(Class, TEXT("PropertyMetadata")))
		{
			const FStructProperty* Identity = FindFProperty<FStructProperty>(Class, TEXT("Identity"));
			const FArrayProperty* Guids = Identity ? FindFProperty<FArrayProperty>(Identity->Struct, TEXT("Guids")) : nullptr;
			if (Guids)
			{
				FScriptArrayHelper Helper(Guids, Guids->ContainerPtrToValuePtr<void>(Identity->ContainerPtrToValuePtr<void>(Element)));
				if (Helper.Num() > 0)
				{
					const FGuid Id = *reinterpret_cast<const FGuid*>(Helper.GetRawPtr(0));
					Out.Add(Id, FHierarchyEntry(Chain, PropertyToJson(Metadata, Metadata->ContainerPtrToValuePtr<void>(Element), Element)));
				}
			}
		}
		if (const FArrayProperty* Children = FindFProperty<FArrayProperty>(Class, TEXT("Children")))
		{
			const FObjectPropertyBase* Inner = CastField<FObjectPropertyBase>(Children->Inner);
			FScriptArrayHelper Helper(Children, Children->ContainerPtrToValuePtr<void>(Element));
			for (int32 Index = 0; Inner && Index < Helper.Num(); ++Index)
			{
				CollectHierarchy(Inner->GetObjectPropertyValue(Helper.GetRawPtr(Index)), Here, Out);
			}
		}
	}

	void ClearChildren(UObject* Element)
	{
		if (const FArrayProperty* Children = FindFProperty<FArrayProperty>(Element->GetClass(), TEXT("Children")))
		{
			Element->Modify();
			FScriptArrayHelper Helper(Children, Children->ContainerPtrToValuePtr<void>(Element));
			Helper.EmptyValues();
		}
	}

	TArray<TSharedPtr<FJsonValue>> ExportParams(UPCGGraph* Graph)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		const FInstancedPropertyBag* Bag = Graph->GetUserParametersStruct();
		const UPropertyBag* BagStruct = Bag ? Bag->GetPropertyBagStruct() : nullptr;
		if (!BagStruct)
		{
			return Out;
		}
		TMap<FGuid, FHierarchyEntry> Hierarchy;
		CollectHierarchy(Graph->GetUserParameterHierarchyRoot(), FString(), Hierarchy);
		for (const FPropertyBagPropertyDesc& Desc : BagStruct->GetPropertyDescs())
		{
			const TSharedRef<FJsonObject> Param = MakeShared<FJsonObject>();
			Param->SetStringField(TEXT("name"), Desc.Name.ToString());
			Param->SetStringField(TEXT("type"), StaticEnum<EPropertyBagPropertyType>()->GetNameStringByValue(static_cast<int64>(Desc.ValueType)));
			Param->SetStringField(TEXT("container"), StaticEnum<EPropertyBagContainerType>()->GetNameStringByValue(static_cast<int64>(Desc.ContainerTypes.GetFirstContainerType())));
			Param->SetStringField(TEXT("type_object"), Desc.ValueTypeObject ? Desc.ValueTypeObject->GetPathName() : FString());
			const TSharedRef<FJsonObject> Meta = MakeShared<FJsonObject>();
#if WITH_EDITORONLY_DATA
			for (const FPropertyBagPropertyDescMetaData& Entry : Desc.MetaData)
			{
				Meta->SetStringField(Entry.Key.ToString(), Entry.Value);
			}
#endif
			Param->SetObjectField(TEXT("meta"), Meta);
			const void* Value = Desc.CachedProperty->ContainerPtrToValuePtr<void>(Bag->GetValue().GetMemory());
			Param->SetField(TEXT("value"), PropertyToJson(Desc.CachedProperty, Value, Graph));
			if (const FHierarchyEntry* Entry = Hierarchy.Find(Desc.ID))
			{
				Param->SetStringField(TEXT("category"), Entry->Key);
				Param->SetField(TEXT("hier_meta"), Entry->Value);
			}
			else
			{
				Param->SetStringField(TEXT("category"), FString());
				Param->SetField(TEXT("hier_meta"), MakeShared<FJsonValueNull>());
			}
			Out.Add(MakeShared<FJsonValueObject>(Param));
		}
		return Out;
	}

	// FPCGGraphCommentNodeData is not exported from PCG; find its reflection data by path.
	UScriptStruct* CommentStruct()
	{
		return FindObject<UScriptStruct>(nullptr, TEXT("/Script/PCG.PCGGraphCommentNodeData"));
	}

	TArray<TSharedPtr<FJsonValue>> ExportBoxes(UPCGGraph* Graph)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
#if WITH_EDITOR
		UScriptStruct* Struct = CommentStruct();
		if (!Struct)
		{
			return Out;
		}
		for (const FPCGGraphCommentNodeData& Box : Graph->GetCommentNodes())
		{
			const TSharedRef<FJsonObject> Json = MakeShared<FJsonObject>();
			FJsonObjectConverter::UStructToJsonObject(Struct, &Box, Json, 0, SkipFlags, nullptr, ConversionFlags);
			Json->RemoveField(TEXT("GUID"));
			Out.Add(MakeShared<FJsonValueObject>(Json));
		}
#endif
		return Out;
	}

	FString ResolveGetter(const UPCGGraph* Graph, const UPCGUserParameterGetSettings* Getter)
	{
		const FInstancedPropertyBag* Bag = Graph->GetUserParametersStruct();
		const FPropertyBagPropertyDesc* Desc = Bag ? Bag->FindPropertyDescByID(Getter->PropertyGuid) : nullptr;
		return Desc ? Desc->Name.ToString() : TEXT("!unbound:") + Getter->PropertyName.ToString();
	}

	TSharedRef<FJsonObject> ExportNode(UPCGGraph* Graph, UPCGNode* Node)
	{
		const TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		UPCGSettings* Settings = Node->GetSettings();
		Out->SetStringField(TEXT("name"), Node->GetName());
		Out->SetStringField(TEXT("class"), Settings ? Settings->GetClass()->GetName() : FString());
		Out->SetStringField(TEXT("title"), Node->NodeTitle.IsNone() ? FString() : Node->NodeTitle.ToString());
#if WITH_EDITORONLY_DATA
		const FLinearColor Color = Node->NodeTitleColor;
		if (Color != FLinearColor::White)
		{
			Out->SetField(TEXT("title_color"), NumberArray({Color.R, Color.G, Color.B, Color.A}));
		}
		Out->SetStringField(TEXT("comment"), Node->NodeComment);
		Out->SetBoolField(TEXT("bubble_visible"), Node->bCommentBubbleVisible != 0);
		Out->SetBoolField(TEXT("bubble_pinned"), Node->bCommentBubblePinned != 0);
		Out->SetField(TEXT("pos"), NumberArray({static_cast<double>(Node->PositionX), static_cast<double>(Node->PositionY)}));
#endif
		TSet<FString> Strip = {TEXT("SubgraphInstance"), TEXT("SubgraphOverride"), TEXT("CachedOverridableParams"), TEXT("DefaultValues")};
		FString GetterParam;
		if (const UPCGUserParameterGetSettings* Getter = Cast<UPCGUserParameterGetSettings>(Settings))
		{
			Strip.Add(TEXT("PropertyGuid"));
			Strip.Add(TEXT("PropertyName"));
			GetterParam = ResolveGetter(Graph, Getter);
		}
		Out->SetObjectField(TEXT("settings"), Settings ? NonDefault(Settings, Strip) : MakeShared<FJsonObject>());
		Out->SetStringField(TEXT("getter_param"), GetterParam);
		if (UPCGSubgraphSettings* Subgraph = Cast<UPCGSubgraphSettings>(Settings))
		{
			UPCGGraphInstance* Instance = Subgraph->SubgraphInstance;
			Out->SetStringField(TEXT("subgraph"), Instance && Instance->Graph ? Instance->Graph->GetPathName() : FString());
			Out->SetObjectField(TEXT("overrides"), Instance ? ExportOverrides(Instance) : MakeShared<FJsonObject>());
		}
		Out->SetArrayField(TEXT("pin_defaults"), Settings ? ExportPinDefaults(Settings) : TArray<TSharedPtr<FJsonValue>>());

		TArray<TSharedPtr<FJsonValue>> Inputs;
		for (const TObjectPtr<UPCGPin>& Pin : Node->GetInputPins())
		{
			TArray<TSharedPtr<FJsonValue>> Edges;
			for (const TObjectPtr<UPCGEdge>& Edge : Pin->Edges)
			{
				const UPCGPin* Other = Edge ? Edge->GetOtherPin(Pin.Get()) : nullptr;
				if (Other && Other->Node)
				{
					TArray<TSharedPtr<FJsonValue>> Pair;
					Pair.Add(MakeShared<FJsonValueString>(Other->Node->GetName()));
					Pair.Add(MakeShared<FJsonValueString>(Other->Properties.Label.ToString()));
					Edges.Add(MakeShared<FJsonValueArray>(Pair));
				}
			}
			const TSharedRef<FJsonObject> PinJson = MakeShared<FJsonObject>();
			PinJson->SetStringField(TEXT("label"), Pin->Properties.Label.ToString());
			PinJson->SetArrayField(TEXT("edges"), Edges);
			Inputs.Add(MakeShared<FJsonValueObject>(PinJson));
		}
		Out->SetArrayField(TEXT("inputs"), Inputs);
		TArray<TSharedPtr<FJsonValue>> Outputs;
		for (const TObjectPtr<UPCGPin>& Pin : Node->GetOutputPins())
		{
			Outputs.Add(MakeShared<FJsonValueString>(Pin->Properties.Label.ToString()));
		}
		Out->SetArrayField(TEXT("outputs"), Outputs);
		return Out;
	}
}

using namespace PyPCGTools::Private;

FString UPyPCGToolsLibrary::ExportGraphIR(UPCGGraph* Graph)
{
	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	if (!Graph)
	{
		Root->SetStringField(TEXT("error"), TEXT("null graph"));
		return Write(Root);
	}
	const TSet<FString> GraphStrip = {TEXT("Nodes"), TEXT("InputNode"), TEXT("OutputNode"), TEXT("UserParameters"),
		TEXT("UserParameterHierarchyRoot"), TEXT("CommentNodes"), TEXT("ExtraEditorNodes"), TEXT("CachedPins"),
		TEXT("LastEditedDocuments"), TEXT("EmbeddedSubgraphs")};
	Root->SetNumberField(TEXT("schema"), 1);
	Root->SetStringField(TEXT("graph"), Graph->GetPathName());
	Root->SetObjectField(TEXT("graph_props"), NonDefault(Graph, GraphStrip));
	Root->SetArrayField(TEXT("params"), ExportParams(Graph));
	Root->SetArrayField(TEXT("comment_boxes"), ExportBoxes(Graph));
	TArray<UPCGNode*> All = {Graph->GetInputNode(), Graph->GetOutputNode()};
	for (UPCGNode* Node : Graph->GetNodes())
	{
		All.Add(Node);
	}
	TArray<TSharedPtr<FJsonValue>> Nodes;
	for (UPCGNode* Node : All)
	{
		if (Node)
		{
			Nodes.Add(MakeShared<FJsonValueObject>(ExportNode(Graph, Node)));
		}
	}
	Root->SetArrayField(TEXT("nodes"), Nodes);
	return Write(Root);
}

FString UPyPCGToolsLibrary::ExportInstanceOverrides(UPCGGraphInstance* Instance)
{
	return Instance ? Write(ExportOverrides(Instance)) : FString(TEXT("{}"));
}

FString UPyPCGToolsLibrary::SetPropertiesJson(UObject* Object, const FString& Json)
{
	if (!Object)
	{
		return TEXT("null object");
	}
	FString Error;
	if (IsProtected(Object, Error))
	{
		return Error;
	}
	const TSharedPtr<FJsonObject> Parsed = ParseObject(Json, Error);
	if (!Parsed)
	{
		return Error;
	}
	Object->Modify();
	const TSharedRef<FJsonObject> Regular = MakeShared<FJsonObject>();
	for (const auto& Field : Parsed->Values)
	{
		FProperty* Property = FindFProperty<FProperty>(Object->GetClass(), *Field.Key);
		if (!Property)
		{
			return FString::Printf(TEXT("%s has no property '%s'"), *Object->GetClass()->GetName(), *Field.Key);
		}
		FString Text;
		if (Field.Value->Type == EJson::String && Field.Value->TryGetString(Text) && Text.StartsWith(TextPrefix))
		{
			if (!JsonToProperty(Field.Value, Property, Property->ContainerPtrToValuePtr<void>(Object), Object, Error))
			{
				return Error;
			}
		}
		else
		{
			Regular->SetField(Field.Key, Field.Value);
		}
	}
	FText Fail;
	// With the object as its own container, instanced subobjects are created with the object as Outer.
	if (Regular->Values.Num() > 0 && !FJsonObjectConverter::JsonObjectToUStruct(Regular, Object->GetClass(), Object, 0, 0, false, &Fail))
	{
		return FString::Printf(TEXT("JsonObjectToUStruct failed: %s"), *Fail.ToString());
	}
	RefreshNode(Object);
	return FString();
}

FString UPyPCGToolsLibrary::SetInstanceParameter(UPCGGraphInstance* Instance, FName Name, const FString& ValueJson)
{
	if (!Instance)
	{
		return TEXT("null instance");
	}
	FString Error;
	if (IsProtected(Instance, Error))
	{
		return Error;
	}
	const TSharedPtr<FJsonObject> Wrap = ParseObject(ValueJson, Error);
	if (!Wrap)
	{
		return Error;
	}
	FInstancedPropertyBag& Bag = Instance->ParametersOverrides.Parameters;
	const FPropertyBagPropertyDesc* Desc = Bag.FindPropertyDescByName(Name);
	if (!Desc || !Desc->CachedProperty)
	{
		TArray<FString> Names;
		if (const UPropertyBag* BagStruct = Bag.GetPropertyBagStruct())
		{
			for (const FPropertyBagPropertyDesc& Each : BagStruct->GetPropertyDescs())
			{
				Names.Add(Each.Name.ToString());
			}
		}
		return FString::Printf(TEXT("instance has no parameter %s; parameters: %s"), *Name.ToString(), *FString::Join(Names, TEXT(", ")));
	}
	Instance->Modify();
	void* Data = Desc->CachedProperty->ContainerPtrToValuePtr<void>(Bag.GetMutableValue().GetMemory());
	if (!JsonToProperty(Wrap->TryGetField(TEXT("v")), Desc->CachedProperty, Data, Instance, Error))
	{
		return Error;
	}
	// Mark explicitly: official graphs keep overrides whose value equals the parent default.
	Instance->UpdatePropertyOverride(Desc->CachedProperty, true);
	Instance->OnGraphParametersChanged(EPCGGraphParameterEvent::ValueModifiedLocally, Name);
	return FString();
}

FString UPyPCGToolsLibrary::SetPinDefaultValue(UPCGSettings* Settings, int32 PinIndex, const FString& TypeName, const FString& ValueJson, bool bHasValue, bool bActivated)
{
	UPCGMetadataSettingsBase* Metadata = Cast<UPCGMetadataSettingsBase>(Settings);
	IPCGSettingsDefaultValueProvider* Provider = Cast<IPCGSettingsDefaultValueProvider>(Settings);
	if (!Metadata || !Provider)
	{
		return TEXT("not a metadata node with inline pin defaults");
	}
	FString Error;
	if (IsProtected(Settings, Error))
	{
		return Error;
	}
	if (PinIndex < 0 || PinIndex > 3)
	{
		return FString::Printf(TEXT("pin index %d out of range 0..3"), PinIndex);
	}
	const FName Pin = Metadata->GetInputPinLabel(PinIndex);
	if (!Provider->IsPinDefaultValueEnabled(Pin))
	{
		return FString::Printf(TEXT("pin %d (%s) has no inline default"), PinIndex, *Pin.ToString());
	}
	Settings->Modify();
	Provider->SetPinDefaultValueIsActivated(Pin, true, true);
	if (bHasValue)
	{
		const int64 Type = StaticEnum<EPCGMetadataTypes>()->GetValueByNameString(TypeName);
		if (Type == INDEX_NONE)
		{
			return FString::Printf(TEXT("unknown metadata type %s"), *TypeName);
		}
		const EPCGMetadataTypes RequestedType = static_cast<EPCGMetadataTypes>(Type);
		if (Provider->GetPinDefaultValueType(Pin) != RequestedType)
		{
			Provider->ConvertPinDefaultValueMetadataType(Pin, RequestedType);
		}
		// The conversion is silently ignored when the pin cannot hold that type; refuse rather than
		// write the value into a property that still has the old type.
		const EPCGMetadataTypes ActualType = Provider->GetPinDefaultValueType(Pin);
		if (ActualType != RequestedType)
		{
			return FString::Printf(TEXT("pin %d (%s) cannot hold type %s; it is %s"),
				PinIndex, *Pin.ToString(),
				*StaticEnum<EPCGMetadataTypes>()->GetNameStringByValue(static_cast<int64>(RequestedType)),
				*StaticEnum<EPCGMetadataTypes>()->GetNameStringByValue(static_cast<int64>(ActualType)));
		}
		// Creates the bag property; the exact value is written below from JSON.
		Provider->SetPinDefaultValue(Pin, FString(), true);
		TSet<FName>* Activated = nullptr;
		FInstancedPropertyBag* Bag = DefaultValueBag(Settings, &Activated);
		const FName Prop = *FString::Printf(TEXT("DefaultValue%d"), PinIndex + 1);
		const FPropertyBagPropertyDesc* Desc = Bag ? Bag->FindPropertyDescByName(Prop) : nullptr;
		if (!Desc || !Desc->CachedProperty)
		{
			return FString::Printf(TEXT("%s was not created"), *Prop.ToString());
		}
		const TSharedPtr<FJsonObject> Wrap = ParseObject(ValueJson, Error);
		if (!Wrap)
		{
			return Error;
		}
		void* Data = Desc->CachedProperty->ContainerPtrToValuePtr<void>(Bag->GetMutableValue().GetMemory());
		if (!JsonToProperty(Wrap->TryGetField(TEXT("v")), Desc->CachedProperty, Data, Settings, Error))
		{
			return Error;
		}
	}
	if (!bActivated)
	{
		Provider->SetPinDefaultValueIsActivated(Pin, false, true);
	}
	RefreshNode(Settings);
	return FString();
}

FString UPyPCGToolsLibrary::SetGraphUserParameters(UPCGGraph* Graph, const FString& Json)
{
	if (!Graph)
	{
		return TEXT("null graph");
	}
	FString Error;
	if (IsProtected(Graph, Error))
	{
		return Error;
	}
	const TSharedPtr<FJsonObject> Parsed = ParseObject(Json, Error);
	if (!Parsed)
	{
		return Error;
	}
	const TArray<TSharedPtr<FJsonValue>>* Params = nullptr;
	if (!Parsed->TryGetArrayField(TEXT("params"), Params))
	{
		return TEXT("missing 'params'");
	}
	TArray<FPropertyBagPropertyDesc> Descs;
	for (const TSharedPtr<FJsonValue>& Value : *Params)
	{
		const TSharedPtr<FJsonObject> Param = Value->AsObject();
		const FString Name = Param->GetStringField(TEXT("name"));
		const int64 Type = StaticEnum<EPropertyBagPropertyType>()->GetValueByNameString(Param->GetStringField(TEXT("type")));
		const int64 Container = StaticEnum<EPropertyBagContainerType>()->GetValueByNameString(Param->GetStringField(TEXT("container")));
		if (Type == INDEX_NONE || Container == INDEX_NONE)
		{
			return FString::Printf(TEXT("param %s: unknown type or container"), *Name);
		}
		const FString TypeObjectPath = Param->GetStringField(TEXT("type_object"));
		const UObject* TypeObject = TypeObjectPath.IsEmpty() ? nullptr : LoadObject<UObject>(nullptr, *TypeObjectPath);
		if (!TypeObjectPath.IsEmpty() && !TypeObject)
		{
			return FString::Printf(TEXT("param %s: cannot load %s"), *Name, *TypeObjectPath);
		}
		FPropertyBagPropertyDesc Desc(FName(*Name), static_cast<EPropertyBagContainerType>(Container), static_cast<EPropertyBagPropertyType>(Type), TypeObject);
#if WITH_EDITOR
		const TSharedPtr<FJsonObject>* Meta = nullptr;
		if (Param->TryGetObjectField(TEXT("meta"), Meta))
		{
			for (const auto& Entry : (*Meta)->Values)
			{
				if (Entry.Key != TEXT("Category") && Entry.Key != TEXT("ToolTip"))
				{
					Desc.SetMetaData(FName(*Entry.Key), Entry.Value->AsString());
				}
			}
		}
		const FString Category = Param->GetStringField(TEXT("category"));
		const FString Tooltip = Param->GetStringField(TEXT("tooltip"));
		if (!Category.IsEmpty())
		{
			Desc.SetMetaData(TEXT("Category"), Category);
		}
		if (!Tooltip.IsEmpty())
		{
			Desc.SetMetaData(TEXT("ToolTip"), Tooltip);
		}
#endif
		Descs.Add(MoveTemp(Desc));
	}
	Graph->Modify();
	Graph->UpdateUserParametersStruct([](FInstancedPropertyBag& Bag) { Bag.Reset(); });
	if (Descs.Num() > 0)
	{
		const EPropertyBagAlterationResult Result = Graph->AddUserParameters(Descs);
		if (Result != EPropertyBagAlterationResult::Success)
		{
			return FString::Printf(TEXT("AddUserParameters failed (%d)"), static_cast<int32>(Result));
		}
	}
	FString ValueError;
	Graph->UpdateUserParametersStruct([&](FInstancedPropertyBag& Bag)
	{
		for (const TSharedPtr<FJsonValue>& Value : *Params)
		{
			const TSharedPtr<FJsonObject> Param = Value->AsObject();
			const FPropertyBagPropertyDesc* Desc = Bag.FindPropertyDescByName(FName(*Param->GetStringField(TEXT("name"))));
			if (!Desc || !Desc->CachedProperty)
			{
				ValueError = TEXT("parameter vanished after AddUserParameters");
				return;
			}
			void* Data = Desc->CachedProperty->ContainerPtrToValuePtr<void>(Bag.GetMutableValue().GetMemory());
			if (!JsonToProperty(Param->TryGetField(TEXT("value")), Desc->CachedProperty, Data, Graph, ValueError))
			{
				return;
			}
		}
	});
	if (!ValueError.IsEmpty())
	{
		return ValueError;
	}
	if (UObject* HierarchyRoot = Graph->GetUserParameterHierarchyRoot())
	{
		ClearChildren(HierarchyRoot);
		if (IPCGEditorModule* Editor = IPCGEditorModule::Get())
		{
			Editor->TransferPropertyBagMetadataIntoHierarchy(Graph);
		}
	}
	return FString();
}

FString UPyPCGToolsLibrary::BindUserParameterGetter(UPCGSettings* Getter, FName ParamName)
{
	UPCGUserParameterGetSettings* GetterSettings = Cast<UPCGUserParameterGetSettings>(Getter);
	if (!GetterSettings)
	{
		return TEXT("not a Get Graph Parameter node");
	}
	FString Error;
	if (IsProtected(GetterSettings, Error))
	{
		return Error;
	}
	const UPCGGraph* Graph = GetterSettings->GetTypedOuter<UPCGGraph>();
	const FInstancedPropertyBag* Bag = Graph ? Graph->GetUserParametersStruct() : nullptr;
	const FPropertyBagPropertyDesc* Desc = Bag ? Bag->FindPropertyDescByName(ParamName) : nullptr;
	if (!Desc)
	{
		return FString::Printf(TEXT("graph has no parameter %s"), *ParamName.ToString());
	}
	GetterSettings->Modify();
	GetterSettings->PropertyGuid = Desc->ID;
	GetterSettings->PropertyName = Desc->Name;
	RefreshNode(GetterSettings);
	return FString();
}

FString UPyPCGToolsLibrary::SetNodeComment(UPCGNode* Node, const FString& Comment, bool bBubbleVisible, bool bBubblePinned)
{
	if (!Node)
	{
		return TEXT("null node");
	}
	FString Error;
	if (IsProtected(Node, Error))
	{
		return Error;
	}
#if WITH_EDITORONLY_DATA
	Node->Modify();
	Node->NodeComment = Comment;
	Node->bCommentBubbleVisible = bBubbleVisible ? 1 : 0;
	Node->bCommentBubblePinned = bBubblePinned ? 1 : 0;
#endif
	return FString();
}

FString UPyPCGToolsLibrary::SetGraphCommentBoxes(UPCGGraph* Graph, const FString& Json)
{
	if (!Graph)
	{
		return TEXT("null graph");
	}
	FString Error;
	if (IsProtected(Graph, Error))
	{
		return Error;
	}
	const TSharedPtr<FJsonObject> Parsed = ParseObject(Json, Error);
	if (!Parsed)
	{
		return Error;
	}
	const TArray<TSharedPtr<FJsonValue>>* Boxes = nullptr;
	if (!Parsed->TryGetArrayField(TEXT("boxes"), Boxes))
	{
		return TEXT("missing 'boxes'");
	}
#if WITH_EDITOR
	UScriptStruct* Struct = CommentStruct();
	if (!Struct)
	{
		return TEXT("FPCGGraphCommentNodeData reflection not found");
	}
	TArray<FPCGGraphCommentNodeData> Out;
	for (const TSharedPtr<FJsonValue>& Value : *Boxes)
	{
		FPCGGraphCommentNodeData Box;
		FText Fail;
		if (!FJsonObjectConverter::JsonObjectToUStruct(Value->AsObject().ToSharedRef(), Struct, &Box, 0, 0, false, &Fail))
		{
			return FString::Printf(TEXT("comment box: %s"), *Fail.ToString());
		}
		Box.GUID = FGuid::NewGuid();
		Out.Add(Box);
	}
	Graph->Modify();
	Graph->SetCommentNodes(MoveTemp(Out));
#endif
	return FString();
}
