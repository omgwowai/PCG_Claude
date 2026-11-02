#if WITH_DEV_AUTOMATION_TESTS

#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "WeatherAstronomy.h"
#include "WeatherTestUtils.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherAstronomyGoldenTest, "SeasonalWeather.Astronomy.Golden",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherAstronomyGoldenTest::RunTest(const FString&)
{
	const TSharedPtr<FJsonObject> Doc = WeatherTest::LoadToolsJson(TEXT("golden/astronomy_cases.json"));
	if (!TestNotNull(TEXT("golden file"), Doc.Get()))
	{
		return false;
	}
	constexpr double Tol = 1e-8;
	TArray<FWeatherSun> Suns;
	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("sun")))
	{
		const TSharedPtr<FJsonObject> C = Value->AsObject();
		const TSharedPtr<FJsonObject> E = C->GetObjectField(TEXT("expect"));
		const FWeatherSun S = WeatherAstronomy::Sun(int32(C->GetNumberField(TEXT("year"))), C->GetNumberField(TEXT("doy")),
			C->GetNumberField(TEXT("hour")), C->GetNumberField(TEXT("lat")), C->GetNumberField(TEXT("lon")), C->GetNumberField(TEXT("tz")));
		const FString At = FString::Printf(TEXT("doy %.2f hour %.2f lat %.2f "), C->GetNumberField(TEXT("doy")),
			C->GetNumberField(TEXT("hour")), C->GetNumberField(TEXT("lat")));
		WeatherTest::Near(*this, At + TEXT("elevation"), S.ElevationDeg, E->GetNumberField(TEXT("elevation_deg")), Tol);
		WeatherTest::Near(*this, At + TEXT("azimuth"), WeatherTest::AngleDiff(S.AzimuthDeg, E->GetNumberField(TEXT("azimuth_deg"))), 0.0, Tol);
		WeatherTest::Near(*this, At + TEXT("declination"), S.DeclinationDeg, E->GetNumberField(TEXT("declination_deg")), Tol);
		WeatherTest::Near(*this, At + TEXT("eot"), S.EquationOfTimeMin, E->GetNumberField(TEXT("eot_min")), Tol);
		WeatherTest::Near(*this, At + TEXT("ra"), WeatherTest::AngleDiff(S.RightAscensionDeg, E->GetNumberField(TEXT("right_ascension_deg"))), 0.0, Tol);
		WeatherTest::Near(*this, At + TEXT("hour angle"), S.HourAngleDeg, E->GetNumberField(TEXT("hour_angle_deg")), Tol);
		WeatherTest::Near(*this, At + TEXT("lambda"), WeatherTest::AngleDiff(S.EclipticLongitudeDeg, E->GetNumberField(TEXT("ecliptic_longitude_deg"))), 0.0, Tol);
		WeatherTest::Near(*this, At + TEXT("obliquity"), S.ObliquityDeg, E->GetNumberField(TEXT("obliquity_deg")), Tol);
		Suns.Add(S);
	}
	TestEqual(TEXT("sun cases"), Suns.Num(), 160);

	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("sunrise")))
	{
		const TSharedPtr<FJsonObject> C = Value->AsObject();
		const TSharedPtr<FJsonObject> E = C->GetObjectField(TEXT("expect"));
		double Rise, Set, Length;
		WeatherAstronomy::SunriseSunset(int32(C->GetNumberField(TEXT("year"))), C->GetNumberField(TEXT("doy")), C->GetNumberField(TEXT("lat")),
			C->GetNumberField(TEXT("lon")), C->GetNumberField(TEXT("tz")), C->GetNumberField(TEXT("zenith")), Rise, Set, Length);
		WeatherTest::Near(*this, TEXT("sunrise"), Rise, E->GetNumberField(TEXT("sunrise")), Tol);
		WeatherTest::Near(*this, TEXT("sunset"), Set, E->GetNumberField(TEXT("sunset")), Tol);
		WeatherTest::Near(*this, TEXT("day length"), Length, E->GetNumberField(TEXT("day_length")), Tol);
	}

	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("moon")))
	{
		const TSharedPtr<FJsonObject> C = Value->AsObject();
		const TSharedPtr<FJsonObject> E = C->GetObjectField(TEXT("expect"));
		const FWeatherMoon M = WeatherAstronomy::Moon(C->GetNumberField(TEXT("game_days")), Suns[int32(C->GetNumberField(TEXT("sun")))],
			C->GetNumberField(TEXT("lat")), C->GetNumberField(TEXT("synodic")), C->GetNumberField(TEXT("offset")));
		const double PhaseDiff = FMath::Abs(M.Phase - E->GetNumberField(TEXT("phase")));
		WeatherTest::Near(*this, TEXT("moon phase"), FMath::Min(PhaseDiff, 1.0 - PhaseDiff), 0.0, Tol);
		WeatherTest::Near(*this, TEXT("moon illumination"), M.Illumination, E->GetNumberField(TEXT("illumination")), Tol);
		WeatherTest::Near(*this, TEXT("moon elevation"), M.ElevationDeg, E->GetNumberField(TEXT("elevation_deg")), Tol);
		WeatherTest::Near(*this, TEXT("moon azimuth"), WeatherTest::AngleDiff(M.AzimuthDeg, E->GetNumberField(TEXT("azimuth_deg"))), 0.0, Tol);
		WeatherTest::Near(*this, TEXT("moon declination"), M.DeclinationDeg, E->GetNumberField(TEXT("declination_deg")), Tol);
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherLightRotationTest, "SeasonalWeather.Astronomy.LightRotation",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherLightRotationTest::RunTest(const FString&)
{
	for (const double North : { 0.0, 15.0 })
	{
		for (const double Az : { 0.0, 90.0, 225.0 })
		{
			const FVector Forward = WeatherAstronomy::LightRotation(30.0, Az, North).Vector();
			const FVector ToBody = WeatherAstronomy::Direction(30.0, Az, North);
			TestTrue(TEXT("the light shines away from the body"), (Forward + ToBody).IsNearlyZero(1e-9));
		}
	}
	return true;
}

#endif
