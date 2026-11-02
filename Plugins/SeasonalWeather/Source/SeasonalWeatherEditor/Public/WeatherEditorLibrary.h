#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "WeatherEditorLibrary.generated.h"

class UStateTree;

/** The weather system's editor entry points: the orchestrator StateTrees (spec §1.5) and the debug panel. */
UCLASS()
class SEASONALWEATHEREDITOR_API UWeatherEditorLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	/** Creates or rebuilds <Folder>/ST_WeatherType and <Folder>/ST_Season (marked dirty, not saved); "" or the compiler errors. */
	UFUNCTION(BlueprintCallable, Category = "Weather|Editor")
	static FString BuildOrchestratorStateTrees(const FString& Folder = TEXT("/SeasonalWeather/Orchestrator"));
	/** Opens the debug panel (Task 15). */
	UFUNCTION(BlueprintCallable, Category = "Weather|Editor")
	static void OpenWeatherPanel();
	/** Root "Weather": one child per EWeatherType (enter condition + task, OnStateCompleted -> root). */
	static bool BuildWeatherTypeTree(UStateTree& Tree, FString& OutErrors);
	/** Root "Season": Spring, SpringToSummer, Summer, ..., WinterToSpring; same shape. */
	static bool BuildSeasonTree(UStateTree& Tree, FString& OutErrors);
};
