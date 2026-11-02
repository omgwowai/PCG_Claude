#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "StateTree.h"
#include "WeatherEditorLibrary.h"
#include "WeatherOrchestrator.h"

namespace
{
	/** A transition may land one tick later; three ticks is the most a state change may take. */
	void Settle(UWeatherOrchestratorState& State, const UStateTree& Tree, FStateTreeInstanceData& Data)
	{
		for (int32 Pass = 0; Pass < 3; ++Pass)
		{
			WeatherOrchestrator::Tick(State, Tree, Data, State, 0.1f);
		}
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherOrchestratorTypeTest, "SeasonalWeather.Orchestrator.WeatherType",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherOrchestratorTypeTest::RunTest(const FString&)
{
	UStateTree* Tree = NewObject<UStateTree>(GetTransientPackage());
	FString Errors;
	if (!TestTrue(TEXT("compiles: ") + Errors, UWeatherEditorLibrary::BuildWeatherTypeTree(*Tree, Errors)))
	{
		return false;
	}
	UWeatherOrchestratorState* State = NewObject<UWeatherOrchestratorState>();
	FStateTreeInstanceData Data;
	State->RequestedType = EWeatherType::Clear;
	TestTrue(TEXT("starts"), WeatherOrchestrator::Start(*State, *Tree, Data, *State));
	TestEqual(TEXT("enters the requested state"), State->ActiveType, EWeatherType::Clear);
	for (const EWeatherType Type : TEnumRange<EWeatherType>())
	{
		const int32 Before = State->TypeStatesEntered;
		State->RequestedType = Type;
		Settle(*State, *Tree, Data);
		TestEqual(*(TEXT("switches to ") + WeatherNames::Type(Type)), State->ActiveType, Type);
		TestEqual(TEXT("one entry per change, none when unchanged"), State->TypeStatesEntered - Before, Type == EWeatherType::Clear ? 0 : 1);
	}
	WeatherOrchestrator::Stop(*State, *Tree, Data, *State);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherOrchestratorSeasonTest, "SeasonalWeather.Orchestrator.Season",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherOrchestratorSeasonTest::RunTest(const FString&)
{
	UStateTree* Tree = NewObject<UStateTree>(GetTransientPackage());
	FString Errors;
	if (!TestTrue(TEXT("compiles: ") + Errors, UWeatherEditorLibrary::BuildSeasonTree(*Tree, Errors)))
	{
		return false;
	}
	UWeatherOrchestratorState* State = NewObject<UWeatherOrchestratorState>();
	FStateTreeInstanceData Data;
	TestTrue(TEXT("starts in spring"), WeatherOrchestrator::Start(*State, *Tree, Data, *State));
	for (int32 Step = 0; Step < 8; ++Step)   // a year: each season, then its transition
	{
		State->CalendarSeason = EWeatherSeason(Step / 2);
		State->bCalendarInTransition = (Step % 2) == 1;
		Settle(*State, *Tree, Data);
		TestEqual(TEXT("season"), State->ActiveSeason, EWeatherSeason(Step / 2));
		TestEqual(TEXT("transition flag"), State->bActiveTransition, (Step % 2) == 1);
	}
	const int32 Entered = State->SeasonStatesEntered;
	Settle(*State, *Tree, Data);
	TestEqual(TEXT("no re-entry while the calendar holds"), State->SeasonStatesEntered, Entered);
	TestEqual(TEXT("eight states over the year"), Entered, 8);
	State->CalendarSeason = EWeatherSeason::Spring;
	State->bCalendarInTransition = false;
	Settle(*State, *Tree, Data);
	TestEqual(TEXT("winter hands over to spring"), State->ActiveSeason, EWeatherSeason::Spring);
	WeatherOrchestrator::Stop(*State, *Tree, Data, *State);
	return true;
}

#endif
