#if WITH_DEV_AUTOMATION_TESTS

#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "WeatherSky.h"
#include "WeatherTestUtils.h"

namespace WeatherSkyTests
{
	// A key of weather_ref/sky.py LOOK_FIELDS and the FWeatherLook member it names.
	struct FLookKey
	{
		const TCHAR* Key;
		double FWeatherLook::* Field;
	};

	// LOOK_FIELDS, in order.
	constexpr FLookKey LookKeys[] = {
		{ TEXT("sun_intensity"), &FWeatherLook::SunIntensity }, { TEXT("moon_intensity"), &FWeatherLook::MoonIntensity },
		{ TEXT("sky_light"), &FWeatherLook::SkyLight }, { TEXT("fog_density"), &FWeatherLook::FogDensity },
		{ TEXT("fog_height_falloff"), &FWeatherLook::FogHeightFalloff }, { TEXT("white_temp_offset"), &FWeatherLook::WhiteTempOffset },
		{ TEXT("saturation"), &FWeatherLook::Saturation }, { TEXT("contrast"), &FWeatherLook::Contrast },
		{ TEXT("exposure_bias"), &FWeatherLook::ExposureBias }, { TEXT("cloud_cover"), &FWeatherLook::CloudCover }
	};

	// A look of sky_cases.json, its 10 snake_case keys onto the struct fields.
	FWeatherLook LookFrom(const FJsonObject& Object)
	{
		FWeatherLook Look;
		for (const FLookKey& Each : LookKeys)
		{
			Look.*(Each.Field) = Object.GetNumberField(Each.Key);
		}
		return Look;
	}

	// All 10 fields of Actual against Expected, each error named "<At><key>".
	void NearLook(FAutomationTestBase& Test, const FString& At, const FWeatherLook& Actual, const FWeatherLook& Expected, double Tol)
	{
		for (const FLookKey& Each : LookKeys)
		{
			WeatherTest::Near(Test, At + Each.Key, Actual.*(Each.Field), Expected.*(Each.Field), Tol);
		}
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWeatherSkyGoldenTest, "SeasonalWeather.Sky.Golden",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWeatherSkyGoldenTest::RunTest(const FString&)
{
	using namespace WeatherSkyTests;
	const TSharedPtr<FJsonObject> Doc = WeatherTest::LoadToolsJson(TEXT("golden/sky_cases.json"));
	if (!TestNotNull(TEXT("golden file"), Doc.Get()))
	{
		return false;
	}
	FWeatherSkyParams Sky;
	FString Error;
	const bool bSkyParsed = FWeatherParams::ParseSky(*Doc->GetObjectField(TEXT("sky")), Sky, Error);
	if (!TestTrue(TEXT("sky section parses: ") + Error, bSkyParsed))
	{
		return false;
	}
	constexpr double Tol = 1e-12;
	constexpr double AngleTol = 1e-9;

	const TArray<TSharedPtr<FJsonValue>>& Combines = Doc->GetArrayField(TEXT("combine"));
	for (int32 Index = 0; Index < Combines.Num(); ++Index)
	{
		const TSharedPtr<FJsonObject> C = Combines[Index]->AsObject();
		const FWeatherLook Got = FWeatherLook::Combine(LookFrom(*C->GetObjectField(TEXT("type"))), LookFrom(*C->GetObjectField(TEXT("season"))));
		NearLook(*this, FString::Printf(TEXT("combine %d "), Index), Got, LookFrom(*C->GetObjectField(TEXT("expect"))), Tol);
	}

	const TArray<TSharedPtr<FJsonValue>>& Lerps = Doc->GetArrayField(TEXT("lerp"));
	for (int32 Index = 0; Index < Lerps.Num(); ++Index)
	{
		const TSharedPtr<FJsonObject> C = Lerps[Index]->AsObject();
		const FWeatherLook Got = FWeatherLook::Lerp(LookFrom(*C->GetObjectField(TEXT("a"))), LookFrom(*C->GetObjectField(TEXT("b"))),
			C->GetNumberField(TEXT("t")));
		NearLook(*this, FString::Printf(TEXT("lerp %d "), Index), Got, LookFrom(*C->GetObjectField(TEXT("expect"))), Tol);
	}

	int32 Count = 0;
	for (const TSharedPtr<FJsonValue>& Value : Doc->GetArrayField(TEXT("rig")))
	{
		const TSharedPtr<FJsonObject> C = Value->AsObject();
		const TSharedPtr<FJsonObject> E = C->GetObjectField(TEXT("expect"));
		const FWeatherSun Sun{ .ElevationDeg = C->GetNumberField(TEXT("sun_el")), .AzimuthDeg = C->GetNumberField(TEXT("sun_az")) };
		const FWeatherMoon Moon{ .Illumination = C->GetNumberField(TEXT("moon_illum")), .ElevationDeg = C->GetNumberField(TEXT("moon_el")),
			.AzimuthDeg = C->GetNumberField(TEXT("moon_az")) };
		const FWeatherRigValues Rig = WeatherSky::Compute(Sun, Moon, LookFrom(*C->GetObjectField(TEXT("look"))), Sky,
			C->GetNumberField(TEXT("north_yaw")));
		const FString At = FString::Printf(TEXT("rig %d "), Count);

		const TPair<const TCHAR*, double> Scalars[] = {
			{ TEXT("sun_lux"), Rig.SunLux }, { TEXT("moon_lux"), Rig.MoonLux }, { TEXT("sky_light_intensity"), Rig.SkyLightIntensity },
			{ TEXT("fog_density"), Rig.FogDensity }, { TEXT("fog_height_falloff"), Rig.FogHeightFalloff }, { TEXT("white_temp"), Rig.WhiteTemp },
			{ TEXT("saturation"), Rig.Saturation }, { TEXT("contrast"), Rig.Contrast }, { TEXT("exposure_bias"), Rig.ExposureBias },
			{ TEXT("star_intensity"), Rig.StarIntensity }, { TEXT("cloud_cover"), Rig.CloudCover }
		};
		for (const TPair<const TCHAR*, double>& Scalar : Scalars)
		{
			WeatherTest::Near(*this, At + Scalar.Key, Scalar.Value, E->GetNumberField(Scalar.Key), Tol);
		}

		const TPair<const TCHAR*, FRotator> Rotations[] = { { TEXT("sun_rotation"), Rig.SunRotation }, { TEXT("moon_rotation"), Rig.MoonRotation } };
		for (const TPair<const TCHAR*, FRotator>& Rotation : Rotations)
		{
			const TArray<TSharedPtr<FJsonValue>>& Angles = E->GetArrayField(Rotation.Key);   // light_rotation's (pitch, yaw, roll)
			const FString What = At + Rotation.Key;
			WeatherTest::Near(*this, What + TEXT(" pitch"), Rotation.Value.Pitch, Angles[0]->AsNumber(), AngleTol);
			WeatherTest::Near(*this, What + TEXT(" yaw"), WeatherTest::AngleDiff(Rotation.Value.Yaw, Angles[1]->AsNumber()), 0.0, AngleTol);
			WeatherTest::Near(*this, What + TEXT(" roll"), Rotation.Value.Roll, Angles[2]->AsNumber(), AngleTol);
		}
		++Count;
	}
	TestEqual(TEXT("rig cases"), Count, 40);
	return true;
}

#endif
