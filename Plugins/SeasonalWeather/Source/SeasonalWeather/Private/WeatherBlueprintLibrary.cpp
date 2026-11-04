#include "WeatherBlueprintLibrary.h"

#include "Engine/Engine.h"
#include "Engine/World.h"
#include "WeatherSubsystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherBlueprintLibrary)

UWeatherSubsystem* UWeatherBlueprintLibrary::GetWeatherSubsystem(const UObject* WorldContextObject)
{
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	return World ? World->GetSubsystem<UWeatherSubsystem>() : nullptr;
}
