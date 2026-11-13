#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "WeatherTypes.h"
#include "WeatherDataAssets.generated.h"

/** The look of one weather type (spec §1.5 DA_WeatherType), /SeasonalWeather/Data/DA_WeatherType_<Type>. Its CloudCover
 *  is the one the sky uses (FWeatherLook::Combine). */
UCLASS(BlueprintType)
class SEASONALWEATHER_API UWeatherTypeAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weather") EWeatherType Type = EWeatherType::Clear;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weather") FWeatherLook Look;
};

/** The look of one season (spec §1.5 DA_SeasonLook), /SeasonalWeather/Data/DA_SeasonLook_<Season>. Combine ignores its
 *  CloudCover. */
UCLASS(BlueprintType)
class SEASONALWEATHER_API USeasonLookAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weather") EWeatherSeason Season = EWeatherSeason::Spring;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weather") FWeatherLook Look;
};
