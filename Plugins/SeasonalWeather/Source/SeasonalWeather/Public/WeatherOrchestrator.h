#pragma once

#include "CoreMinimal.h"
#include "StateTreeConditionBase.h"
#include "StateTreeExecutionTypes.h"
#include "StateTreeInstanceData.h"
#include "StateTreeSchema.h"
#include "StateTreeTaskBase.h"
#include "WeatherTypes.h"
#include "WeatherOrchestrator.generated.h"

class UStateTree;

/** What both StateTrees read (inputs, set by the subsystem before a tick) and write (outputs). */
UCLASS(BlueprintType)
class SEASONALWEATHER_API UWeatherOrchestratorState : public UObject
{
	GENERATED_BODY()
public:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Input") EWeatherType RequestedType = EWeatherType::Clear;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Input") EWeatherSeason CalendarSeason = EWeatherSeason::Spring;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Input") bool bCalendarInTransition = false;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Output") EWeatherType ActiveType = EWeatherType::Clear;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Output") EWeatherSeason ActiveSeason = EWeatherSeason::Spring;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Output") bool bActiveTransition = false;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Output") int32 TypeStatesEntered = 0;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Output") int32 SeasonStatesEntered = 0;
};

UCLASS(BlueprintType, EditInlineNew, CollapseCategories, meta = (DisplayName = "Seasonal Weather"))
class SEASONALWEATHER_API UWeatherStateTreeSchema : public UStateTreeSchema
{
	GENERATED_BODY()
public:
	virtual bool IsStructAllowed(const UScriptStruct* InScriptStruct) const override;   // common task / condition bases
	virtual bool IsClassAllowed(const UClass* InClass) const override { return false; }
	virtual bool IsExternalItemAllowed(const UStruct& InStruct) const override;          // UWeatherOrchestratorState
};

/** The nodes below keep no per-instance data, but the StateTree compiler rejects a node without an instance struct
 *  ("Malformed task, missing instance value."), so they share this empty one, as the engine's stateless nodes do. */
USTRUCT()
struct FWeatherOrchestratorNodeInstanceData
{
	GENERATED_BODY()
};

USTRUCT(meta = (DisplayName = "Weather Type Requested"))
struct SEASONALWEATHER_API FWeatherTypeRequestedCondition : public FStateTreeConditionCommonBase
{
	GENERATED_BODY()
	using FInstanceDataType = FWeatherOrchestratorNodeInstanceData;
	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	UPROPERTY(EditAnywhere, Category = "Weather") EWeatherType Type = EWeatherType::Clear;
	virtual bool Link(FStateTreeLinker& Linker) override;
	virtual bool TestCondition(FStateTreeExecutionContext& Context) const override;     // RequestedType == Type
	TStateTreeExternalDataHandle<UWeatherOrchestratorState> StateHandle;
};

USTRUCT(meta = (DisplayName = "Weather Type State"))
struct SEASONALWEATHER_API FWeatherTypeStateTask : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()
	using FInstanceDataType = FWeatherOrchestratorNodeInstanceData;
	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	UPROPERTY(EditAnywhere, Category = "Weather") EWeatherType Type = EWeatherType::Clear;
	virtual bool Link(FStateTreeLinker& Linker) override;
	/** ActiveType = Type, ++TypeStatesEntered, Running. */
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
	/** Running while RequestedType == Type, else Succeeded (the state's transition goes back to the root). */
	virtual EStateTreeRunStatus Tick(FStateTreeExecutionContext& Context, const float DeltaTime) const override;
	TStateTreeExternalDataHandle<UWeatherOrchestratorState> StateHandle;
};

USTRUCT(meta = (DisplayName = "Season Is"))
struct SEASONALWEATHER_API FWeatherSeasonIsCondition : public FStateTreeConditionCommonBase
{
	GENERATED_BODY()
	using FInstanceDataType = FWeatherOrchestratorNodeInstanceData;
	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	UPROPERTY(EditAnywhere, Category = "Weather") EWeatherSeason Season = EWeatherSeason::Spring;
	UPROPERTY(EditAnywhere, Category = "Weather") bool bTransition = false;
	virtual bool Link(FStateTreeLinker& Linker) override;
	virtual bool TestCondition(FStateTreeExecutionContext& Context) const override;     // CalendarSeason / bCalendarInTransition match
	TStateTreeExternalDataHandle<UWeatherOrchestratorState> StateHandle;
};

USTRUCT(meta = (DisplayName = "Season State"))
struct SEASONALWEATHER_API FWeatherSeasonStateTask : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()
	using FInstanceDataType = FWeatherOrchestratorNodeInstanceData;
	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	UPROPERTY(EditAnywhere, Category = "Weather") EWeatherSeason Season = EWeatherSeason::Spring;
	UPROPERTY(EditAnywhere, Category = "Weather") bool bTransition = false;
	virtual bool Link(FStateTreeLinker& Linker) override;
	/** ActiveSeason = Season, bActiveTransition = bTransition, ++SeasonStatesEntered, Running. */
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
	/** Running while the calendar still matches, else Succeeded. */
	virtual EStateTreeRunStatus Tick(FStateTreeExecutionContext& Context, const float DeltaTime) const override;
	TStateTreeExternalDataHandle<UWeatherOrchestratorState> StateHandle;
};

namespace WeatherOrchestrator
{
	SEASONALWEATHER_API bool Start(UObject& Owner, const UStateTree& Tree, FStateTreeInstanceData& InstanceData, UWeatherOrchestratorState& State);
	SEASONALWEATHER_API EStateTreeRunStatus Tick(UObject& Owner, const UStateTree& Tree, FStateTreeInstanceData& InstanceData, UWeatherOrchestratorState& State, float DeltaSeconds);
	SEASONALWEATHER_API void Stop(UObject& Owner, const UStateTree& Tree, FStateTreeInstanceData& InstanceData, UWeatherOrchestratorState& State);
}
