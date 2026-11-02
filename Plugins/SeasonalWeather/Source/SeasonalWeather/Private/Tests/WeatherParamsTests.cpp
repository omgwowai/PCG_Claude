#if WITH_DEV_AUTOMATION_TESTS

#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "WeatherParams.h"
#include "WeatherTestUtils.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherParamsLoadTest, "SeasonalWeather.Params.Load",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherParamsLoadTest::RunTest(const FString&)
{
	FWeatherParams Params;
	FString Error;
	TestTrue(TEXT("default file loads: ") + Error, FWeatherParams::LoadFromFile(FWeatherParams::DefaultPath(), Params, Error));
	TestEqual(TEXT("12 fields (spec 1.3)"), Params.Fields.Num(), 12);
	TestEqual(TEXT("7-day seasons"), Params.Calendar.SeasonLengthDays, 7);
	TestEqual(TEXT("starts in spring"), Params.Calendar.StartSeason, EWeatherSeason::Spring);
	TestEqual(TEXT("35 N"), Params.Astronomy.LatitudeDeg, 35.0);
	TestEqual(TEXT("override wind from the west"), Params.OverrideDefaults.WindDirectionDeg, 270.f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherParamsSchemaKeysTest, "SeasonalWeather.Params.SchemaKeys",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherParamsSchemaKeysTest::RunTest(const FString&)
{
	const TSharedPtr<FJsonObject> Schema = WeatherTest::LoadToolsJson(TEXT("params_schema.json"));
	if (!TestNotNull(TEXT("schema"), Schema.Get()))
	{
		return false;
	}
	TSet<FString> Expected;
	for (const TPair<FString, TSharedPtr<FJsonValue>>& Section : Schema->Values)
	{
		if (Section.Value->Type == EJson::Object)
		{
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Key : Section.Value->AsObject()->Values)
			{
				Expected.Add(Section.Key + TEXT(".") + Key.Key);
			}
		}
		else
		{
			Expected.Add(Section.Key);
		}
	}
	FWeatherParams Params;
	FString Error;
	FWeatherParams::LoadFromFile(FWeatherParams::DefaultPath(), Params, Error);
	TestEqual(TEXT("33 keys"), Expected.Num(), 33);
	for (const FString& Key : Expected)
	{
		TestTrue(TEXT("C++ reads ") + Key, Params.ConsumedKeys.Contains(Key));
	}
	for (const FString& Key : Params.ConsumedKeys)
	{
		TestTrue(TEXT("schema lists ") + Key, Expected.Contains(Key));
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherParamsFieldSizesTest, "SeasonalWeather.Params.FieldSizes",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherParamsFieldSizesTest::RunTest(const FString&)
{
	FWeatherParams Params;
	FString Error;
	FWeatherParams::LoadFromFile(FWeatherParams::DefaultPath(), Params, Error);
	TestEqual(TEXT("atmos"), Params.FindField(TEXT("atmos_volume"))->ResolveSize(300.0), FIntVector(128, 128, 32));
	TestEqual(TEXT("surface at 300 m"), Params.FindField(TEXT("surface_state"))->ResolveSize(300.0), FIntVector(304, 304, 1));
	TestEqual(TEXT("canopy at 300 m"), Params.FindField(TEXT("canopy_state"))->ResolveSize(300.0), FIntVector(80, 80, 1));
	TestEqual(TEXT("gust at 2 m"), Params.FindField(TEXT("gust_map"))->ResolveSize(2.0), FIntVector(8, 8, 1));
	TestNull(TEXT("unknown field"), Params.FindField(TEXT("nope")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherParamsErrorsTest, "SeasonalWeather.Params.Errors",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherParamsErrorsTest::RunTest(const FString&)
{
	FString Text;
	FFileHelper::LoadFileToString(Text, *FWeatherParams::DefaultPath());
	FWeatherParams Params;
	FString Error;
	TestFalse(TEXT("missing sky"), FWeatherParams::LoadFromString(Text.Replace(TEXT("\"sky\""), TEXT("\"skx\"")), Params, Error));
	TestTrue(TEXT("names the section: ") + Error, Error.Contains(TEXT("sky")));
	TestFalse(TEXT("bad format"), FWeatherParams::LoadFromString(Text.Replace(TEXT("\"r32f\""), TEXT("\"r8\"")), Params, Error));
	TestTrue(TEXT("names the field: ") + Error, Error.Contains(TEXT("near_ground_height")));
	return true;
}

#endif
