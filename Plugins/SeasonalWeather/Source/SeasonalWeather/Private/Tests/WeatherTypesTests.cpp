#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "WeatherTypes.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherTypesNamesTest, "SeasonalWeather.Types.Names",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherTypesNamesTest::RunTest(const FString&)
{
	for (const EWeatherSeason Season : TEnumRange<EWeatherSeason>())
	{
		EWeatherSeason Parsed = EWeatherSeason::Count;
		TestTrue(TEXT("season round-trips"), WeatherNames::ParseSeason(WeatherNames::Season(Season), Parsed) && Parsed == Season);
	}
	for (const EWeatherType Type : TEnumRange<EWeatherType>())
	{
		EWeatherType Parsed = EWeatherType::Count;
		TestTrue(TEXT("type round-trips"), WeatherNames::ParseType(WeatherNames::Type(Type), Parsed) && Parsed == Type);
	}
	TestEqual(TEXT("weather_ref spelling"), WeatherNames::Type(EWeatherType::FairCumulus), FString(TEXT("FairCumulus")));
	EWeatherType Unused;
	TestFalse(TEXT("unknown names fail"), WeatherNames::ParseType(TEXT("Sunny"), Unused));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherOverrideWindTest, "SeasonalWeather.Types.OverrideWind",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherOverrideWindTest::RunTest(const FString&)
{
	FWeatherOverride Override;
	Override.WindDirectionDeg = 270.f;   // a west wind
	Override.WindSpeedMps = 4.f;
	const FVector3f West = Override.WindVector();
	TestTrue(TEXT("a west wind blows toward +Y"), FMath::Abs(West.X) < 1e-5f && FMath::IsNearlyEqual(West.Y, 4.f, 1e-5f) && West.Z == 0.f);
	Override.WindDirectionDeg = 0.f;     // a north wind
	TestTrue(TEXT("a north wind blows toward -X"), FMath::IsNearlyEqual(Override.WindVector().X, -4.f, 1e-5f));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherLookCombineTest, "SeasonalWeather.Types.LookCombine",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherLookCombineTest::RunTest(const FString&)
{
	FWeatherLook TypeLook;
	TypeLook.Saturation = 0.8;
	TypeLook.ExposureBias = 0.3;
	TypeLook.CloudCover = 0.9;
	FWeatherLook SeasonLook;
	SeasonLook.Saturation = 1.1;
	SeasonLook.ExposureBias = 0.2;
	SeasonLook.CloudCover = 0.5;
	const FWeatherLook Combined = FWeatherLook::Combine(TypeLook, SeasonLook);
	TestTrue(TEXT("scales multiply"), FMath::IsNearlyEqual(Combined.Saturation, 0.88, 1e-12));
	TestTrue(TEXT("offsets add"), FMath::IsNearlyEqual(Combined.ExposureBias, 0.5, 1e-12));
	TestEqual(TEXT("cloud cover comes from the type"), Combined.CloudCover, 0.9);
	TestTrue(TEXT("lerp is field by field"), FMath::IsNearlyEqual(FWeatherLook::Lerp(FWeatherLook(), TypeLook, 0.5).Saturation, 0.9, 1e-12));
	return true;
}

#endif
