#include "WeatherDomain.h"

#include "Components/SceneComponent.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherDomain)

AWeatherDomain::AWeatherDomain()
{
	PrimaryActorTick.bCanEverTick = false;   // the subsystem does the work
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}
