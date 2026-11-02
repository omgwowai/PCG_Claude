#if WITH_DEV_AUTOMATION_TESTS

#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "Serialization/JsonSerializer.h"
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

	// The file's values equal the C++ defaults, so move every one: the k-th number of the schema to 100.25 + k (an integer
	// to 100 + k; both exact as floats), the season and the four days by hand. Each value is then off its default and off
	// every other value, and a key read into the wrong member, or not read, fails naming the key.
	const TSharedPtr<FJsonObject> Doc = WeatherTest::LoadToolsJson(TEXT("weather_params.json"));
	const TSharedPtr<FJsonObject> Schema = WeatherTest::LoadToolsJson(TEXT("params_schema.json"));
	if (!TestNotNull(TEXT("params file"), Doc.Get()) || !TestNotNull(TEXT("schema"), Schema.Get()))
	{
		return false;
	}
	TMap<FString, double> Written;
	for (const TPair<FString, TSharedPtr<FJsonValue>>& Section : Schema->Values)
	{
		if (Section.Value->Type != EJson::Object)
		{
			continue;
		}
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Key : Section.Value->AsObject()->Values)
		{
			const FString Type = Key.Value->AsString();
			if (Type == TEXT("number") || Type == TEXT("integer"))
			{
				const double Value = (Type == TEXT("integer") ? 100.0 : 100.25) + Written.Num();
				Doc->GetObjectField(Section.Key)->SetNumberField(Key.Key, Value);
				Written.Add(Section.Key + TEXT(".") + Key.Key, Value);
			}
		}
	}
	const TSharedPtr<FJsonObject> Calendar = Doc->GetObjectField(TEXT("calendar"));
	const TSharedPtr<FJsonObject> Days = Calendar->GetObjectField(TEXT("season_start_doy"));
	Calendar->SetStringField(TEXT("start_season"), TEXT("Autumn"));
	const double Doy[] = { 80.0, 170.0, 266.0, 350.0 };
	for (const EWeatherSeason Season : TEnumRange<EWeatherSeason>())
	{
		Days->SetNumberField(WeatherNames::Season(Season), Doy[static_cast<int32>(Season)]);
	}
	FString Text;
	FJsonSerializer::Serialize(Doc, TJsonWriterFactory<>::Create(&Text));
	FWeatherParams Moved;
	const bool bMovedLoads = FWeatherParams::LoadFromString(Text, Moved, Error);
	if (!TestTrue(TEXT("moved file loads: ") + Error, bMovedLoads))
	{
		return false;
	}
	const TArray<TPair<FString, double>> Members = {
		{ TEXT("calendar.real_seconds_per_game_day"), Moved.Calendar.RealSecondsPerGameDay },
		{ TEXT("calendar.season_length_days"), Moved.Calendar.SeasonLengthDays },
		{ TEXT("calendar.transition_days"), Moved.Calendar.TransitionDays },
		{ TEXT("calendar.start_hour"), Moved.Calendar.StartHour },
		{ TEXT("calendar.base_year"), Moved.Calendar.BaseYear },
		{ TEXT("astronomy.latitude_deg"), Moved.Astronomy.LatitudeDeg },
		{ TEXT("astronomy.longitude_deg"), Moved.Astronomy.LongitudeDeg },
		{ TEXT("astronomy.timezone_hours"), Moved.Astronomy.TimezoneHours },
		{ TEXT("astronomy.north_yaw_deg"), Moved.Astronomy.NorthYawDeg },
		{ TEXT("astronomy.synodic_month_game_days"), Moved.Astronomy.SynodicMonthGameDays },
		{ TEXT("astronomy.moon_phase_offset_days"), Moved.Astronomy.MoonPhaseOffsetDays },
		{ TEXT("astronomy.sunrise_zenith_deg"), Moved.Astronomy.SunriseZenithDeg },
		{ TEXT("sky.sun_lux"), Moved.Sky.SunLux },
		{ TEXT("sky.moon_lux"), Moved.Sky.MoonLux },
		{ TEXT("sky.sky_light_intensity"), Moved.Sky.SkyLightIntensity },
		{ TEXT("sky.fog_density"), Moved.Sky.FogDensity },
		{ TEXT("sky.fog_height_falloff"), Moved.Sky.FogHeightFalloff },
		{ TEXT("sky.white_temp_k"), Moved.Sky.WhiteTempK },
		{ TEXT("sky.cloud_dimming"), Moved.Sky.CloudDimming },
		{ TEXT("sky.star_fade_start_deg"), Moved.Sky.StarFadeStartDeg },
		{ TEXT("sky.star_fade_range_deg"), Moved.Sky.StarFadeRangeDeg },
		{ TEXT("sky.look_blend_seconds"), Moved.Sky.LookBlendSeconds },
		{ TEXT("override_defaults.precip_mm_h"), Moved.OverrideDefaults.PrecipMmPerHour },
		{ TEXT("override_defaults.snow_fraction"), Moved.OverrideDefaults.SnowFraction },
		{ TEXT("override_defaults.temperature_c"), Moved.OverrideDefaults.TemperatureC },
		{ TEXT("override_defaults.humidity"), Moved.OverrideDefaults.Humidity },
		{ TEXT("override_defaults.wind_dir_deg"), Moved.OverrideDefaults.WindDirectionDeg },
		{ TEXT("override_defaults.wind_speed_m_s"), Moved.OverrideDefaults.WindSpeedMps },
		{ TEXT("override_defaults.thunder_potential"), Moved.OverrideDefaults.ThunderPotential },
		{ TEXT("override_defaults.cloud_cover"), Moved.OverrideDefaults.CloudCover }
	};
	TestEqual(TEXT("30 numbers moved"), Written.Num(), 30);
	TestEqual(TEXT("one member per moved number"), Members.Num(), Written.Num());
	for (const TPair<FString, double>& Number : Written)
	{
		const TPair<FString, double>* Member = Members.FindByPredicate(
			[&Number](const TPair<FString, double>& Row) { return Row.Key == Number.Key; });
		if (TestNotNull(*(Number.Key + TEXT(" has a member")), Member))
		{
			WeatherTest::Near(*this, Number.Key, Member->Value, Number.Value, 0.0);
		}
	}
	TestEqual(TEXT("calendar.start_season"), Moved.Calendar.StartSeason, EWeatherSeason::Autumn);
	for (const EWeatherSeason Season : TEnumRange<EWeatherSeason>())
	{
		const int32 Index = static_cast<int32>(Season);
		const FString What = TEXT("calendar.season_start_doy.") + WeatherNames::Season(Season);
		WeatherTest::Near(*this, What, Moved.Calendar.SeasonStartDoy[Index], Doy[Index], 0.0);
	}
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
