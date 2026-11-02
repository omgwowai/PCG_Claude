#if WITH_DEV_AUTOMATION_TESTS

#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "WeatherCalendar.h"
#include "WeatherTestUtils.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherCalendarGoldenTest, "SeasonalWeather.Calendar.Golden",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherCalendarGoldenTest::RunTest(const FString&)
{
	const TSharedPtr<FJsonObject> Doc = WeatherTest::LoadToolsJson(TEXT("golden/calendar_cases.json"));
	if (!TestNotNull(TEXT("golden file"), Doc.Get()))
	{
		return false;
	}
	FWeatherCalendarParams Params;
	FString Error;
	TestTrue(TEXT("params: ") + Error, FWeatherParams::ParseCalendar(*Doc->GetObjectField(TEXT("params")), Params, Error));

	int32 Cases = 0;
	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("evaluate")))
	{
		const TSharedPtr<FJsonObject> Case = Value->AsObject();
		const TSharedPtr<FJsonObject> E = Case->GetObjectField(TEXT("expect"));
		const double Seconds = Case->GetNumberField(TEXT("game_seconds"));
		const FWeatherCalendarState S = WeatherCalendar::Evaluate(Seconds, Params);
		const FString At = FString::Printf(TEXT("t=%.3f "), Seconds);
		TestEqual(At + TEXT("day_index"), S.DayIndex, int32(E->GetNumberField(TEXT("day_index"))));
		WeatherTest::Near(*this, At + TEXT("hour"), S.Hour, E->GetNumberField(TEXT("hour")), 1e-9);
		TestEqual(At + TEXT("season"), WeatherNames::Season(S.Season), E->GetStringField(TEXT("season")));
		TestEqual(At + TEXT("next_season"), WeatherNames::Season(S.NextSeason), E->GetStringField(TEXT("next_season")));
		TestEqual(At + TEXT("day_in_season"), S.DayInSeason, int32(E->GetNumberField(TEXT("day_in_season"))));
		WeatherTest::Near(*this, At + TEXT("season_fraction"), S.SeasonFraction, E->GetNumberField(TEXT("season_fraction")), 1e-12);
		TestEqual(At + TEXT("in_transition"), S.bInTransition, E->GetBoolField(TEXT("in_transition")));
		WeatherTest::Near(*this, At + TEXT("transition_progress"), S.TransitionProgress, E->GetNumberField(TEXT("transition_progress")), 1e-12);
		const TArray<TSharedPtr<FJsonValue>>& W = E->GetArrayField(TEXT("weights"));
		for (int32 Index = 0; Index < 4; ++Index)
		{
			WeatherTest::Near(*this, At + TEXT("weight"), S.SeasonWeights[Index], W[Index]->AsNumber(), 1e-12);
		}
		TestEqual(At + TEXT("year"), S.Year, int32(E->GetNumberField(TEXT("year"))));
		WeatherTest::Near(*this, At + TEXT("day_of_year"), S.DayOfYear, E->GetNumberField(TEXT("day_of_year")), 1e-9);
		++Cases;
	}
	TestEqual(TEXT("evaluate cases"), Cases, 15);

	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("seconds_for")))
	{
		const TSharedPtr<FJsonObject> Case = Value->AsObject();
		EWeatherSeason Season;
		WeatherNames::ParseSeason(Case->GetStringField(TEXT("season")), Season);
		const double Got = WeatherCalendar::SecondsFor(Params, Case->GetNumberField(TEXT("current")), Season,
			int32(Case->GetNumberField(TEXT("day"))), Case->GetNumberField(TEXT("hour")));
		WeatherTest::Near(*this, TEXT("seconds_for"), Got, Case->GetNumberField(TEXT("expect")), 1e-6);
	}
	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("with_hour")))
	{
		const TSharedPtr<FJsonObject> Case = Value->AsObject();
		WeatherTest::Near(*this, TEXT("with_hour"), WeatherCalendar::WithHour(Case->GetNumberField(TEXT("current")),
			Case->GetNumberField(TEXT("hour"))), Case->GetNumberField(TEXT("expect")), 1e-6);
	}
	return true;
}

#endif
