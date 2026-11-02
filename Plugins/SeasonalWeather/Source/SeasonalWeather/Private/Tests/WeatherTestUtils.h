#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

/** Helpers shared by the SeasonalWeather automation tests. */
namespace WeatherTest
{
	/** Tools/weather/<RelativePath> as a JSON object; nullptr when the file is missing or is not a JSON object. */
	inline TSharedPtr<FJsonObject> LoadToolsJson(const FString& RelativePath)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *(FPaths::ProjectDir() / TEXT("Tools/weather") / RelativePath)))
		{
			return nullptr;
		}
		TSharedPtr<FJsonObject> Object;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Object))
		{
			return nullptr;
		}
		return Object;
	}

	/** True when |Actual - Expected| <= Tol; otherwise adds the error "<What>: got %.12g, expected %.12g". */
	inline bool Near(FAutomationTestBase& Test, const FString& What, double Actual, double Expected, double Tol)
	{
		if (FMath::Abs(Actual - Expected) <= Tol)
		{
			return true;
		}
		Test.AddError(FString::Printf(TEXT("%s: got %.12g, expected %.12g"), *What, Actual, Expected));
		return false;
	}
}
