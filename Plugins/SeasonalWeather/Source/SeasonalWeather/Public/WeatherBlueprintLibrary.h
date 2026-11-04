#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "WeatherBlueprintLibrary.generated.h"

class UWeatherSubsystem;

/** weather.py's entry point: unreal.WeatherBlueprintLibrary.get_weather_subsystem(world). */
UCLASS()
class SEASONALWEATHER_API UWeatherBlueprintLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	/** The weather of the context object's world; nullptr for a world without one (preview worlds, no world). */
	UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Weather", meta = (WorldContext = "WorldContextObject"))
	static UWeatherSubsystem* GetWeatherSubsystem(const UObject* WorldContextObject);
};
