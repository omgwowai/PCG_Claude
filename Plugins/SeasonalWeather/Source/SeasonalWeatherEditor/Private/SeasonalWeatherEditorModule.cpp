#include "Framework/Application/SlateApplication.h"
#include "Framework/Docking/TabManager.h"
#include "HAL/IConsoleManager.h"
#include "Modules/ModuleManager.h"
#include "SWeatherDebugPanel.h"
#include "WeatherEditorLibrary.h"
#include "Widgets/Docking/SDockTab.h"
#include "WorkspaceMenuStructure.h"
#include "WorkspaceMenuStructureModule.h"

/** Registers the debug panel's tab (spec §1.8); weather.Panel and UWeatherEditorLibrary::OpenWeatherPanel open it. */
class FSeasonalWeatherEditorModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};

namespace SeasonalWeatherEditorModule::Private
{
	FAutoConsoleCommand CmdPanel(TEXT("weather.Panel"), TEXT("weather.Panel: open the Seasonal Weather debug panel."),
		FConsoleCommandDelegate::CreateStatic(&UWeatherEditorLibrary::OpenWeatherPanel));
}

void FSeasonalWeatherEditorModule::StartupModule()
{
	FGlobalTabmanager::Get()->RegisterNomadTabSpawner(TEXT("SeasonalWeatherPanel"), FOnSpawnTab::CreateLambda([](const FSpawnTabArgs&)
	{
		return SNew(SDockTab).TabRole(ETabRole::NomadTab)[SNew(SWeatherDebugPanel)];
	}))
	.SetDisplayName(NSLOCTEXT("SeasonalWeather", "PanelTitle", "Seasonal Weather"))
	.SetGroup(WorkspaceMenu::GetMenuStructure().GetDeveloperToolsMiscCategory());
}

void FSeasonalWeatherEditorModule::ShutdownModule()
{
	if (FSlateApplication::IsInitialized())
	{
		FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(TEXT("SeasonalWeatherPanel"));
	}
}

IMPLEMENT_MODULE(FSeasonalWeatherEditorModule, SeasonalWeatherEditor)
