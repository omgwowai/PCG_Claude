#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "SWeatherDebugPanel.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherPanelBuildsTest, "SeasonalWeather.Editor.PanelBuilds",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherPanelBuildsTest::RunTest(const FString&)
{
	TSharedRef<SWeatherDebugPanel> Panel = SNew(SWeatherDebugPanel);
	TestFalse(TEXT("status text is never empty"), Panel->StatusText().IsEmpty());
	TestTrue(TEXT("the panel tab is registered"), FGlobalTabmanager::Get()->HasTabSpawner(FName(TEXT("SeasonalWeatherPanel"))));
	return true;
}

#endif
