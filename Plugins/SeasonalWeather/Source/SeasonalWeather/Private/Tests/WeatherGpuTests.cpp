#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/App.h"
#include "Misc/AutomationTest.h"
#include "RHIGlobals.h"
#include "WeatherFieldRegistry.h"
#include "WeatherParams.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherGpuFieldsTest, "SeasonalWeather.Gpu.Fields",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherGpuFieldsTest::RunTest(const FString&)
{
	if (GUsingNullRHI || !FApp::CanEverRender())
	{
		AddError(TEXT("needs a GPU: run with -RenderOffScreen, not -nullrhi"));
		return false;
	}
	FWeatherParams Params;
	FString Error;
	if (!TestTrue(TEXT("params: ") + Error, FWeatherParams::LoadFromFile(FWeatherParams::DefaultPath(), Params, Error)))
	{
		return false;
	}
	UWeatherFieldRegistry* Registry = NewObject<UWeatherFieldRegistry>();
	Registry->Initialize(Params.Fields, 64.0);
	const FLinearColor Value(0.25f, -1.5f, 3.0f, 0.5f);
	for (const FWeatherFieldDesc& Desc : Params.Fields)
	{
		const FString Name = Desc.Name.ToString();
		if (!TestNotNull(*(Name + TEXT(" allocated")), Registry->GetOrCreateField(Desc.Name)))
		{
			continue;
		}
		const FIntVector Size = Registry->GetFieldSize(Desc.Name);
		TestEqual(*(Name + TEXT(" size")), Size, Desc.ResolveSize(64.0));
		TestTrue(*(Name + TEXT(" fill queued")), Registry->FillUniform(Desc.Name, Value));
		const TArray<FIntVector> Coords = { FIntVector(0, 0, 0), Size - FIntVector(1, 1, 1), FIntVector(Size.X / 2, Size.Y / 2, Size.Z / 2) };
		const TArray<FLinearColor> Got = Registry->ReadTexelsBlocking(Desc.Name, Coords);
		if (!TestEqual(*(Name + TEXT(" values")), Got.Num(), Coords.Num()))
		{
			continue;
		}
		const bool bOneChannel = Desc.Format != EWeatherFieldFormat::RGBA16F;
		for (const FLinearColor& Texel : Got)
		{
			TestTrue(*(Name + TEXT(" R")), FMath::IsNearlyEqual(Texel.R, Value.R, 1e-3f));
			if (!bOneChannel)
			{
				TestTrue(*(Name + TEXT(" GBA")), FMath::IsNearlyEqual(Texel.G, Value.G, 1e-3f)
					&& FMath::IsNearlyEqual(Texel.B, Value.B, 1e-3f) && FMath::IsNearlyEqual(Texel.A, Value.A, 1e-3f));
			}
		}
	}
	TestEqual(TEXT("every field of spec 1.3 allocated"), Registry->GetFieldNames().Num(), 12);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherGpuUnknownFieldTest, "SeasonalWeather.Gpu.UnknownField",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherGpuUnknownFieldTest::RunTest(const FString&)
{
	FWeatherParams Params;
	FString Error;
	FWeatherParams::LoadFromFile(FWeatherParams::DefaultPath(), Params, Error);
	UWeatherFieldRegistry* Registry = NewObject<UWeatherFieldRegistry>();
	Registry->Initialize(Params.Fields, 64.0);
	TestNull(TEXT("unknown name"), Registry->GetOrCreateField(TEXT("nope")));
	TestFalse(TEXT("cannot fill it"), Registry->FillUniform(TEXT("nope"), FLinearColor::White));
	TestEqual(TEXT("nothing allocated"), Registry->GetFieldNames().Num(), 0);
	return true;
}

#endif
