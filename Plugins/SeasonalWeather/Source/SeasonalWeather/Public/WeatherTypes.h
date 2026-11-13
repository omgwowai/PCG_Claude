#pragma once

#include "CoreMinimal.h"
#include "Misc/EnumRange.h"
#include "WeatherTypes.generated.h"

SEASONALWEATHER_API DECLARE_LOG_CATEGORY_EXTERN(LogSeasonalWeather, Log, All);

UENUM(BlueprintType)
enum class EWeatherSeason : uint8 { Spring, Summer, Autumn, Winter, Count UMETA(Hidden) };
ENUM_RANGE_BY_COUNT(EWeatherSeason, EWeatherSeason::Count);

UENUM(BlueprintType)
enum class EWeatherType : uint8
{
	Clear, FairCumulus, Overcast, FrontalRain, Thunderstorm, Fog, Snow, Blizzard, Count UMETA(Hidden)
};
ENUM_RANGE_BY_COUNT(EWeatherType, EWeatherType::Count);

/** The names weather_ref and weather.py use ("Spring", "FairCumulus", ...). */
namespace WeatherNames
{
	SEASONALWEATHER_API FString Season(EWeatherSeason Season);
	SEASONALWEATHER_API FString Type(EWeatherType Type);
	SEASONALWEATHER_API bool ParseSeason(const FString& Name, EWeatherSeason& Out);
	SEASONALWEATHER_API bool ParseType(const FString& Name, EWeatherType& Out);
}

/** The manual override (spec §1.5, plan ruling P3): uniform values for the ground maps and the coarse wind. */
USTRUCT(BlueprintType)
struct SEASONALWEATHER_API FWeatherOverride
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float PrecipMmPerHour = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float SnowFraction = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float TemperatureC = 15.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float Humidity = 0.6f;
	/** Where the wind comes FROM, degrees clockwise from north. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float WindDirectionDeg = 270.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float WindSpeedMps = 3.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float ThunderPotential = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float CloudCover = 0.1f;

	/** Velocity in m/s, world X north and Y east: -(cos d, sin d, 0) * speed. */
	FVector3f WindVector() const;
};

/** Scales and offsets on the base sky values of weather_params.json "sky"; weather_ref/sky.py LOOK_FIELDS in order. */
USTRUCT(BlueprintType)
struct SEASONALWEATHER_API FWeatherLook
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double SunIntensity = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double MoonIntensity = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double SkyLight = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double FogDensity = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double FogHeightFalloff = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double WhiteTempOffset = 0.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double Saturation = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double Contrast = 1.0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double ExposureBias = 0.0;
	/** Set by weather-type looks only; Combine keeps the type's. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look") double CloudCover = 0.0;

	static FWeatherLook Lerp(const FWeatherLook& A, const FWeatherLook& B, double T);
	/** Scales multiply, WhiteTempOffset and ExposureBias add, CloudCover comes from TypeLook (weather_ref.sky.combine). */
	static FWeatherLook Combine(const FWeatherLook& TypeLook, const FWeatherLook& SeasonLook);
};
