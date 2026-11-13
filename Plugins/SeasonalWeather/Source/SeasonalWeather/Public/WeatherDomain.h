#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WeatherDomain.generated.h"

class ADirectionalLight;
class AExponentialHeightFog;
class APostProcessVolume;
class ASkyLight;

/** The level's weather settings and the sky actors the weather drives. One per level: a world without one keeps
 *  UWeatherSubsystem inert, with no fields, no assets and no output (plan Review Focus 1). */
UCLASS(meta = (DisplayName = "Weather Domain"))
class SEASONALWEATHER_API AWeatherDomain : public AActor
{
	GENERATED_BODY()
public:
	AWeatherDomain();   // RootComponent = a USceneComponent
	/** Side of the square the level-wide fields cover, metres (spec §1.3). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather") float ExtentMeters = 512.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather|Sky") TObjectPtr<ADirectionalLight> Sun;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather|Sky") TObjectPtr<ADirectionalLight> Moon;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather|Sky") TObjectPtr<ASkyLight> SkyLight;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather|Sky") TObjectPtr<AExponentialHeightFog> HeightFog;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather|Sky") TObjectPtr<APostProcessVolume> PostProcess;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Weather|Sky") TObjectPtr<AActor> Stars;
};
