#include "WeatherOrchestrator.h"

#include "StateTree.h"
#include "StateTreeExecutionContext.h"
#include "StateTreeLinker.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherOrchestrator)

namespace
{
	FOnCollectStateTreeExternalData CollectFor(UWeatherOrchestratorState& State)
	{
		return FOnCollectStateTreeExternalData::CreateLambda(
			[&State](const FStateTreeExecutionContext&, const UStateTree*, TArrayView<const FStateTreeExternalDataDesc> Descs, TArrayView<FStateTreeDataView> OutViews)
			{
				for (int32 Index = 0; Index < Descs.Num(); ++Index)
				{
					if (Descs[Index].Struct && Descs[Index].Struct->IsChildOf(UWeatherOrchestratorState::StaticClass()))
					{
						OutViews[Index] = FStateTreeDataView(&State);
					}
				}
				return true;
			});
	}

	/** The season state a node stands for is the calendar's: same season and same transition flag. */
	bool CalendarMatches(const UWeatherOrchestratorState& State, const EWeatherSeason Season, const bool bTransition)
	{
		return State.CalendarSeason == Season && State.bCalendarInTransition == bTransition;
	}
}

bool UWeatherStateTreeSchema::IsStructAllowed(const UScriptStruct* InScriptStruct) const
{
	return InScriptStruct->IsChildOf(FStateTreeConditionCommonBase::StaticStruct())
		|| InScriptStruct->IsChildOf(FStateTreeTaskCommonBase::StaticStruct());
}

bool UWeatherStateTreeSchema::IsExternalItemAllowed(const UStruct& InStruct) const
{
	return InStruct.IsChildOf(UWeatherOrchestratorState::StaticClass());
}

bool FWeatherTypeRequestedCondition::Link(FStateTreeLinker& Linker)
{
	Linker.LinkExternalData(StateHandle);
	return true;
}

bool FWeatherTypeRequestedCondition::TestCondition(FStateTreeExecutionContext& Context) const
{
	return Context.GetExternalData(StateHandle).RequestedType == Type;
}

bool FWeatherTypeStateTask::Link(FStateTreeLinker& Linker)
{
	Linker.LinkExternalData(StateHandle);
	return true;
}

EStateTreeRunStatus FWeatherTypeStateTask::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	UWeatherOrchestratorState& State = Context.GetExternalData(StateHandle);
	State.ActiveType = Type;
	++State.TypeStatesEntered;
	return EStateTreeRunStatus::Running;
}

EStateTreeRunStatus FWeatherTypeStateTask::Tick(FStateTreeExecutionContext& Context, const float DeltaTime) const
{
	return Context.GetExternalData(StateHandle).RequestedType == Type ? EStateTreeRunStatus::Running : EStateTreeRunStatus::Succeeded;
}

bool FWeatherSeasonIsCondition::Link(FStateTreeLinker& Linker)
{
	Linker.LinkExternalData(StateHandle);
	return true;
}

bool FWeatherSeasonIsCondition::TestCondition(FStateTreeExecutionContext& Context) const
{
	return CalendarMatches(Context.GetExternalData(StateHandle), Season, bTransition);
}

bool FWeatherSeasonStateTask::Link(FStateTreeLinker& Linker)
{
	Linker.LinkExternalData(StateHandle);
	return true;
}

EStateTreeRunStatus FWeatherSeasonStateTask::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	UWeatherOrchestratorState& State = Context.GetExternalData(StateHandle);
	State.ActiveSeason = Season;
	State.bActiveTransition = bTransition;
	++State.SeasonStatesEntered;
	return EStateTreeRunStatus::Running;
}

EStateTreeRunStatus FWeatherSeasonStateTask::Tick(FStateTreeExecutionContext& Context, const float DeltaTime) const
{
	return CalendarMatches(Context.GetExternalData(StateHandle), Season, bTransition) ? EStateTreeRunStatus::Running : EStateTreeRunStatus::Succeeded;
}

bool WeatherOrchestrator::Start(UObject& Owner, const UStateTree& Tree, FStateTreeInstanceData& InstanceData, UWeatherOrchestratorState& State)
{
	FStateTreeExecutionContext Context(Owner, Tree, InstanceData, CollectFor(State));
	return Context.IsValid() && Context.Start() == EStateTreeRunStatus::Running;
}

EStateTreeRunStatus WeatherOrchestrator::Tick(UObject& Owner, const UStateTree& Tree, FStateTreeInstanceData& InstanceData, UWeatherOrchestratorState& State, float DeltaSeconds)
{
	FStateTreeExecutionContext Context(Owner, Tree, InstanceData, CollectFor(State));
	return Context.IsValid() ? Context.Tick(DeltaSeconds) : EStateTreeRunStatus::Failed;
}

void WeatherOrchestrator::Stop(UObject& Owner, const UStateTree& Tree, FStateTreeInstanceData& InstanceData, UWeatherOrchestratorState& State)
{
	FStateTreeExecutionContext Context(Owner, Tree, InstanceData, CollectFor(State));
	if (Context.IsValid())
	{
		Context.Stop();
	}
}
