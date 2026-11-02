#pragma once

#include "CoreMinimal.h"
#include "WeatherTypes.h"

class FJsonObject;

/** weather_ref/params.py FORMATS ("rgba16f", "r16f", "r32f"), in order. */
enum class EWeatherFieldFormat : uint8 { RGBA16F, R16F, R32F };

/** One entry of weather_params.json "fields" (spec §1.3). */
struct SEASONALWEATHER_API FWeatherFieldDesc
{
	FName Name;
	int32 Dims = 2;
	FIntVector Size = FIntVector::ZeroValue;   // given size; all zero for a cell_m field
	double CellMeters = 0.0;                    // > 0 for a field that covers the level
	EWeatherFieldFormat Format = EWeatherFieldFormat::RGBA16F;
	TArray<FString> Channels;
	/** weather_ref.params.field_size; 2D fields return Z = 1. */
	FIntVector ResolveSize(double ExtentMeters) const;
};

/** weather_params.json "calendar"; SeasonStartDoy in EWeatherSeason order. */
struct SEASONALWEATHER_API FWeatherCalendarParams
{
	double RealSecondsPerGameDay = 3600.0;
	int32 SeasonLengthDays = 7;
	double TransitionDays = 1.0;
	EWeatherSeason StartSeason = EWeatherSeason::Spring;
	double StartHour = 9.0;
	int32 BaseYear = 2026;
	double SeasonStartDoy[4] = { 79.0, 172.0, 265.0, 355.0 };
};

/** weather_params.json "astronomy". */
struct SEASONALWEATHER_API FWeatherAstronomyParams
{
	double LatitudeDeg = 35.0, LongitudeDeg = 136.0, TimezoneHours = 9.0, NorthYawDeg = 0.0;
	double SynodicMonthGameDays = 29.530588853, MoonPhaseOffsetDays = 0.0, SunriseZenithDeg = 90.833;
};

/** weather_params.json "sky". */
struct SEASONALWEATHER_API FWeatherSkyParams
{
	double SunLux = 10.0, MoonLux = 0.3, SkyLightIntensity = 1.0, FogDensity = 0.02, FogHeightFalloff = 0.2;
	double WhiteTempK = 6500.0, CloudDimming = 0.75, StarFadeStartDeg = -3.0, StarFadeRangeDeg = 9.0, LookBlendSeconds = 3.0;
};

/** Tools/weather/weather_params.json, the file weather_ref/params.py reads (spec §2.6). */
struct SEASONALWEATHER_API FWeatherParams
{
	FWeatherCalendarParams Calendar;
	FWeatherAstronomyParams Astronomy;
	FWeatherSkyParams Sky;
	TArray<FWeatherFieldDesc> Fields;
	FWeatherOverride OverrideDefaults;
	/** "section.key" of every value read (the "fields" section is one key); compared with params_schema.json. */
	TSet<FString> ConsumedKeys;

	static FString DefaultPath();   // FPaths::ProjectDir() / "Tools/weather/weather_params.json"
	static bool LoadFromString(const FString& JsonText, FWeatherParams& Out, FString& OutError);
	static bool LoadFromFile(const FString& Path, FWeatherParams& Out, FString& OutError);
	/** Section parsers, public so the golden tests can read the params they carry. */
	static bool ParseCalendar(const FJsonObject& Section, FWeatherCalendarParams& Out, FString& OutError);
	static bool ParseSky(const FJsonObject& Section, FWeatherSkyParams& Out, FString& OutError);
	const FWeatherFieldDesc* FindField(FName Name) const;
};
