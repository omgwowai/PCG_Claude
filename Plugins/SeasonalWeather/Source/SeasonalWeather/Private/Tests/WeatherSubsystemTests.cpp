#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ExponentialHeightFogComponent.h"
#include "Components/LightComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "GameFramework/PlayerState.h"
#include "GameFramework/WorldSettings.h"
#include "Misc/AutomationTest.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Tests/AutomationCommon.h"
#include "WeatherDomain.h"
#include "WeatherFieldRegistry.h"
#include "WeatherSubsystem.h"

namespace
{
	struct FRig
	{
		AWeatherDomain* Domain = nullptr;
		ADirectionalLight* Sun = nullptr;
		AExponentialHeightFog* Fog = nullptr;
		APostProcessVolume* Post = nullptr;
	};

	FRig SpawnRig(UWorld& World)
	{
		FRig Rig;
		Rig.Sun = World.SpawnActor<ADirectionalLight>();
		Rig.Fog = World.SpawnActor<AExponentialHeightFog>();
		Rig.Post = World.SpawnActor<APostProcessVolume>();
		Rig.Domain = World.SpawnActor<AWeatherDomain>();
		Rig.Domain->ExtentMeters = 64.f;
		Rig.Domain->Sun = Rig.Sun;
		Rig.Domain->Moon = World.SpawnActor<ADirectionalLight>();
		Rig.Domain->SkyLight = World.SpawnActor<ASkyLight>();
		Rig.Domain->HeightFog = Rig.Fog;
		Rig.Domain->PostProcess = Rig.Post;
		return Rig;
	}

	UWeatherSubsystem* MakeWorld(FTestWorldWrapper& Wrapper, FAutomationTestBase& Test)
	{
		if (!Wrapper.CreateTestWorld(EWorldType::Game) || !Wrapper.BeginPlayInTestWorld())
		{
			Test.AddError(TEXT("could not create a test world"));
			return nullptr;
		}
		return Wrapper.GetTestWorld()->GetSubsystem<UWeatherSubsystem>();
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSubsystemNoDomainTest, "SeasonalWeather.Subsystem.NoDomain",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSubsystemNoDomainTest::RunTest(const FString&)
{
	FTestWorldWrapper Wrapper;
	UWeatherSubsystem* Weather = MakeWorld(Wrapper, *this);
	if (!Weather)
	{
		return false;
	}
	Weather->UpdateNow(0.1f);
	Weather->ApplyNow();
	TestFalse(TEXT("inert without a domain"), Weather->IsActive());
	TestEqual(TEXT("no render targets"), Weather->GetFieldRegistry()->GetFieldNames().Num(), 0);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSubsystemApplySkyTest, "SeasonalWeather.Subsystem.ApplySky",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSubsystemApplySkyTest::RunTest(const FString&)
{
	FTestWorldWrapper Wrapper;
	UWeatherSubsystem* Weather = MakeWorld(Wrapper, *this);
	if (!Weather)
	{
		return false;
	}
	const FRig Rig = SpawnRig(*Wrapper.GetTestWorld());
	Weather->SetSeason(EWeatherSeason::Summer, 0);
	Weather->SetTimeOfDay(12.f);
	Weather->SetWeatherType(EWeatherType::Clear, false);
	Weather->ApplyNow();
	TestTrue(TEXT("active with a domain"), Weather->IsActive());
	TestTrue(TEXT("summer noon sun near 78.4 deg"), FMath::Abs(Weather->GetSun().ElevationDeg - 78.4) < 1.0);
	const FWeatherRigValues& Values = Weather->GetRig();
	TestTrue(TEXT("sun rotated"), FMath::IsNearlyEqual(Rig.Sun->GetActorRotation().Pitch, Values.SunRotation.Pitch, 1e-3));
	TestTrue(TEXT("sun intensity"), FMath::IsNearlyEqual(Rig.Sun->GetLightComponent()->Intensity, float(Values.SunLux), 1e-3f));
	TestTrue(TEXT("fog density"), FMath::IsNearlyEqual(Rig.Fog->GetComponent()->FogDensity, float(Values.FogDensity), 1e-6f));
	TestTrue(TEXT("grading"), Rig.Post->Settings.bOverride_ColorSaturation && FMath::IsNearlyEqual(Rig.Post->Settings.ColorSaturation.X, Values.Saturation, 1e-6));
	Weather->SetTimeOfDay(0.f);
	Weather->ApplyNow();
	TestTrue(TEXT("stars at midnight"), Weather->GetRig().StarIntensity > 0.5);
	Weather->SetTimeOfDay(12.f);
	Weather->SetWeatherType(EWeatherType::Overcast, false);
	Weather->ApplyNow();
	TestEqual(TEXT("type switches with or without the generated trees"), Weather->GetActiveWeatherType(), EWeatherType::Overcast);
	TSharedPtr<FJsonObject> State;
	FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Weather->GetStateJson()), State);
	if (TestNotNull(TEXT("state json"), State.Get()))
	{
		TestEqual(TEXT("json active type"), State->GetObjectField(TEXT("orchestrator"))->GetStringField(TEXT("active_type")), FString(TEXT("Overcast")));
		TestTrue(TEXT("json rig"), FMath::IsNearlyEqual(State->GetObjectField(TEXT("rig"))->GetNumberField(TEXT("star_intensity")), Weather->GetRig().StarIntensity, 1e-9));
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSubsystemBlendRestartTest, "SeasonalWeather.Subsystem.BlendRestart",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSubsystemBlendRestartTest::RunTest(const FString&)
{
	FTestWorldWrapper Wrapper;
	UWeatherSubsystem* Weather = MakeWorld(Wrapper, *this);
	if (!Weather)
	{
		return false;
	}
	SpawnRig(*Wrapper.GetTestWorld());
	FWeatherLook Clear, Overcast, Fog;
	Overcast.SunIntensity = 0.2;
	Fog.SunIntensity = 0.5;
	Weather->SetTypeLook(EWeatherType::Clear, Clear);
	Weather->SetTypeLook(EWeatherType::Overcast, Overcast);
	Weather->SetTypeLook(EWeatherType::Fog, Fog);
	Weather->SetWeatherType(EWeatherType::Clear, false);
	Weather->ApplyNow();
	const float Half = float(Weather->GetParams().Sky.LookBlendSeconds * 0.5);
	Weather->SetWeatherType(EWeatherType::Overcast, true);
	Weather->UpdateNow(0.f);
	Weather->UpdateNow(Half);
	const double Mid = Weather->GetLook().SunIntensity;
	TestTrue(TEXT("half way to overcast"), Mid < 0.95 && Mid > 0.25);
	Weather->SetWeatherType(EWeatherType::Fog, true);
	Weather->UpdateNow(0.0001f);
	TestTrue(TEXT("restart from the screen, no jump"), FMath::Abs(Weather->GetLook().SunIntensity - Mid) < 0.01);
	Weather->UpdateNow(2.f * Half);
	Weather->UpdateNow(2.f * Half);
	TestTrue(TEXT("arrives at fog"), FMath::IsNearlyEqual(Weather->GetLook().SunIntensity, 0.5, 1e-9));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSubsystemFieldsTest, "SeasonalWeather.Subsystem.Fields",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSubsystemFieldsTest::RunTest(const FString&)
{
	FTestWorldWrapper Wrapper;
	UWeatherSubsystem* Weather = MakeWorld(Wrapper, *this);
	if (!Weather)
	{
		return false;
	}
	SpawnRig(*Wrapper.GetTestWorld());
	FWeatherOverride Override;
	Override.PrecipMmPerHour = 5.f;
	Override.TemperatureC = -2.f;
	Override.WindDirectionDeg = 270.f;
	Override.WindSpeedMps = 4.f;
	Override.CloudCover = 0.7f;
	Weather->SetOverride(Override);
	Weather->ApplyNow();
	UWeatherFieldRegistry* Fields = Weather->GetFieldRegistry();
	const FLinearColor A = Fields->ReadTexelsBlocking(TEXT("ground_a"), { FIntVector(5, 7, 0) })[0];
	const FLinearColor B = Fields->ReadTexelsBlocking(TEXT("ground_b"), { FIntVector(5, 7, 0) })[0];
	const FLinearColor W = Fields->ReadTexelsBlocking(TEXT("coarse_wind"), { FIntVector(64, 64, 3) })[0];
	TestTrue(TEXT("precip"), FMath::IsNearlyEqual(A.R, 5.f, 1e-2f));
	TestTrue(TEXT("temperature"), FMath::IsNearlyEqual(A.B, -2.f, 1e-2f));
	TestTrue(TEXT("west wind in the ground map"), FMath::Abs(B.R) < 1e-2f && FMath::IsNearlyEqual(B.G, 4.f, 1e-2f));
	TestTrue(TEXT("cloud cover"), FMath::IsNearlyEqual(B.A, 0.7f, 1e-2f));
	TestTrue(TEXT("coarse wind"), FMath::IsNearlyEqual(W.G, 4.f, 1e-2f));
	TestEqual(TEXT("probe = override wind"), Weather->GetProbeWind(Weather->RegisterProbe(FVector::ZeroVector)), FVector(Override.WindVector()));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSubsystemClockTest, "SeasonalWeather.Subsystem.ClockClamps",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSubsystemClockTest::RunTest(const FString&)
{
	FTestWorldWrapper Wrapper;
	UWeatherSubsystem* Weather = MakeWorld(Wrapper, *this);
	if (!Weather)
	{
		return false;
	}
	SpawnRig(*Wrapper.GetTestWorld());
	Weather->SetSeason(EWeatherSeason::Spring, 0);
	Weather->SetTimeOfDay(1.f);
	Weather->AdvanceGameTime(-5.f);
	TestTrue(TEXT("never before day 0"), Weather->GetCalendar().GameSeconds >= 0.0);
	Weather->SetTimeOfDay(25.f);
	TestTrue(TEXT("hour stays below 24"), Weather->GetCalendar().Hour < 24.0);
	Weather->SetSeason(EWeatherSeason::Autumn, 99);
	TestEqual(TEXT("day clamps to the season"), Weather->GetCalendar().DayInSeason, 6);
	Weather->SetTimeScale(3600.f);
	const double Before = Weather->GetCalendar().GameSeconds;
	Weather->UpdateNow(1.f);
	TestTrue(TEXT("scale 3600: one second is one game hour"), FMath::IsNearlyEqual(Weather->GetCalendar().GameSeconds - Before, 3600.0, 1e-6));
	Weather->SetPaused(true);
	Weather->UpdateNow(1.f);
	TestTrue(TEXT("paused"), FMath::IsNearlyEqual(Weather->GetCalendar().GameSeconds - Before, 3600.0, 1e-6));
	// A paused world stops it too: the subsystem ticks even then (IsTickableInEditor). A pauser player state is how
	// AGameModeBase::SetPause pauses a world, and it needs no player controller.
	Weather->SetPaused(false);
	UWorld* World = Wrapper.GetTestWorld();
	World->GetWorldSettings()->SetPauserPlayerState(World->SpawnActor<APlayerState>());
	TestTrue(TEXT("the world is paused"), World->IsPaused());
	Weather->UpdateNow(1.f);
	TestTrue(TEXT("a paused world"), FMath::IsNearlyEqual(Weather->GetCalendar().GameSeconds - Before, 3600.0, 1e-6));
	World->GetWorldSettings()->SetPauserPlayerState(nullptr);
	Weather->UpdateNow(1.f);
	TestTrue(TEXT("runs again with the world"), FMath::IsNearlyEqual(Weather->GetCalendar().GameSeconds - Before, 7200.0, 1e-6));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSubsystemConsoleTest, "SeasonalWeather.Subsystem.Console",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSubsystemConsoleTest::RunTest(const FString&)
{
	FTestWorldWrapper Wrapper;
	UWeatherSubsystem* Weather = MakeWorld(Wrapper, *this);
	if (!Weather)
	{
		return false;
	}
	SpawnRig(*Wrapper.GetTestWorld());
	UWorld* World = Wrapper.GetTestWorld();
	GEngine->Exec(World, TEXT("weather.Type Fog noblend"));
	TestEqual(TEXT("weather.Type"), Weather->GetActiveWeatherType(), EWeatherType::Fog);
	GEngine->Exec(World, TEXT("weather.Season Winter 2"));
	TestEqual(TEXT("weather.Season"), Weather->GetCalendar().Season, EWeatherSeason::Winter);
	TestEqual(TEXT("weather.Season day"), Weather->GetCalendar().DayInSeason, 2);
	GEngine->Exec(World, TEXT("weather.Type Sunny"));
	TestEqual(TEXT("an unknown name changes nothing"), Weather->GetActiveWeatherType(), EWeatherType::Fog);
	return true;
}

#endif
