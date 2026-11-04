#include "WeatherEditorLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Framework/Application/SlateApplication.h"
#include "Framework/Docking/TabManager.h"
#include "Logging/TokenizedMessage.h"
#include "Misc/PackageName.h"
#include "StateTree.h"
#include "StateTreeCompilerLog.h"
#include "StateTreeEditingSubsystem.h"
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

	/** Through the editing subsystem, like the StateTree editor: the same compiler, plus the editor data hash, so a built
	 *  asset does not read as needing a recompile. */
	bool Compile(UStateTree& Tree, FString& OutErrors)
	{
		FStateTreeCompilerLog Log;
		const bool bCompiled = UStateTreeEditingSubsystem::CompileStateTree(&Tree, Log);
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
	// Python reaches this over the bridge: a bad input must end in an error line here, never in an engine fatal error
	// (CreatePackage on a malformed name, NewObject without a package or over an object of another class).
	auto Build = [&Errors, &Folder](const TCHAR* AssetName, bool (*Builder)(UStateTree&, FString&))
	{
		const FString PackageName = Folder / AssetName;
		FPackageName::EErrorCode Reason = FPackageName::EErrorCode::PackageNameUnknown;
		if (!FPackageName::IsValidLongPackageName(PackageName, false, &Reason))
		{
			Errors += FString::Printf(TEXT("%s: %s\n"), AssetName, *FPackageName::FormatErrorAsString(PackageName, Reason));
			return;
		}
		UPackage* Package = FPackageName::DoesPackageExist(PackageName) ? LoadPackage(nullptr, *PackageName, LOAD_None) : CreatePackage(*PackageName);
		if (!Package)
		{
			Errors += FString::Printf(TEXT("%s: package '%s' could not be loaded or created\n"), AssetName, *PackageName);
			return;
		}
		UStateTree* Tree = FindObject<UStateTree>(Package, AssetName);
		if (!Tree)
		{
			if (const UObject* Existing = StaticFindObject(UObject::StaticClass(), Package, AssetName))
			{
				Errors += FString::Printf(TEXT("%s: '%s' is an object of class %s, not a StateTree\n"), AssetName, *Existing->GetPathName(), *Existing->GetClass()->GetName());
				return;
			}
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
	// Python and Blueprints reach this too; without Slate (a commandlet) there is no tab to open, and spawning one would
	// assert in FSlateApplication::Get().
	if (FSlateApplication::IsInitialized())
	{
		FGlobalTabmanager::Get()->TryInvokeTab(FTabId(TEXT("SeasonalWeatherPanel")));
	}
}
