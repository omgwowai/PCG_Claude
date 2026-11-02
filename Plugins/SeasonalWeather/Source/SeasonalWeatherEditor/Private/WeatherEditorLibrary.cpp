#include "WeatherEditorLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Logging/TokenizedMessage.h"
#include "Misc/PackageName.h"
#include "StateTree.h"
#include "StateTreeCompiler.h"
#include "StateTreeCompilerLog.h"
#include "StateTreeEditorData.h"
#include "StateTreeState.h"
#include "UObject/Package.h"
#include "WeatherOrchestrator.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherEditorLibrary)

namespace
{
	UStateTreeEditorData& ResetEditorData(UStateTree& Tree)
	{
		UStateTreeEditorData* EditorData = NewObject<UStateTreeEditorData>(&Tree, NAME_None, RF_Transactional);
		EditorData->Schema = NewObject<UWeatherStateTreeSchema>(EditorData);
		Tree.EditorData = EditorData;
		return *EditorData;
	}

	bool Compile(UStateTree& Tree, FString& OutErrors)
	{
		FStateTreeCompilerLog Log;
		FStateTreeCompiler Compiler(Log);
		const bool bCompiled = Compiler.Compile(Tree);
		for (const TSharedRef<FTokenizedMessage>& Message : Log.ToTokenizedMessages())
		{
			if (Message->GetSeverity() == EMessageSeverity::Error)
			{
				OutErrors += Message->ToText().ToString() + TEXT("\n");
			}
		}
		return bCompiled && Tree.IsReadyToRun();
	}
}

bool UWeatherEditorLibrary::BuildWeatherTypeTree(UStateTree& Tree, FString& OutErrors)
{
	UStateTreeEditorData& EditorData = ResetEditorData(Tree);
	UStateTreeState& Root = EditorData.AddSubTree(FName(TEXT("Weather")));
	for (const EWeatherType Type : TEnumRange<EWeatherType>())
	{
		UStateTreeState& State = Root.AddChildState(FName(*WeatherNames::Type(Type)));
		State.AddEnterCondition<FWeatherTypeRequestedCondition>().GetNode().Type = Type;
		State.AddTask<FWeatherTypeStateTask>().GetNode().Type = Type;
		State.AddTransition(EStateTreeTransitionTrigger::OnStateCompleted, EStateTreeTransitionType::GotoState, &Root);
	}
	return Compile(Tree, OutErrors);
}

bool UWeatherEditorLibrary::BuildSeasonTree(UStateTree& Tree, FString& OutErrors)
{
	UStateTreeEditorData& EditorData = ResetEditorData(Tree);
	UStateTreeState& Root = EditorData.AddSubTree(FName(TEXT("Season")));
	for (const EWeatherSeason Season : TEnumRange<EWeatherSeason>())
	{
		for (const bool bTransition : { false, true })
		{
			const EWeatherSeason Next = EWeatherSeason((int32(Season) + 1) % 4);
			const FString Name = bTransition ? WeatherNames::Season(Season) + TEXT("To") + WeatherNames::Season(Next) : WeatherNames::Season(Season);
			UStateTreeState& State = Root.AddChildState(FName(*Name));
			FWeatherSeasonIsCondition& Condition = State.AddEnterCondition<FWeatherSeasonIsCondition>().GetNode();
			Condition.Season = Season;
			Condition.bTransition = bTransition;
			FWeatherSeasonStateTask& Task = State.AddTask<FWeatherSeasonStateTask>().GetNode();
			Task.Season = Season;
			Task.bTransition = bTransition;
			State.AddTransition(EStateTreeTransitionTrigger::OnStateCompleted, EStateTreeTransitionType::GotoState, &Root);
		}
	}
	return Compile(Tree, OutErrors);
}

FString UWeatherEditorLibrary::BuildOrchestratorStateTrees(const FString& Folder)
{
	FString Errors;
	auto Build = [&Errors, &Folder](const TCHAR* AssetName, bool (*Builder)(UStateTree&, FString&))
	{
		const FString PackageName = Folder / AssetName;
		UPackage* Package = FPackageName::DoesPackageExist(PackageName) ? LoadPackage(nullptr, *PackageName, LOAD_None) : CreatePackage(*PackageName);
		UStateTree* Tree = FindObject<UStateTree>(Package, AssetName);
		if (!Tree)
		{
			Tree = NewObject<UStateTree>(Package, FName(AssetName), RF_Public | RF_Standalone | RF_Transactional);
			FAssetRegistryModule::AssetCreated(Tree);
		}
		FString TreeErrors;
		if (!Builder(*Tree, TreeErrors))
		{
			Errors += FString::Printf(TEXT("%s: %s"), AssetName, *TreeErrors);
		}
		Package->MarkPackageDirty();
	};
	Build(TEXT("ST_WeatherType"), &UWeatherEditorLibrary::BuildWeatherTypeTree);
	Build(TEXT("ST_Season"), &UWeatherEditorLibrary::BuildSeasonTree);
	return Errors;
}

void UWeatherEditorLibrary::OpenWeatherPanel()
{
	// Task 15 opens the debug panel here.
}
