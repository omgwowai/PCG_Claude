#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "WeatherSubsystem.h"

// The weather.* console commands (spec §1.8). Each one that changes something ends in ApplyNow(), so the change shows at
// once, in the editor world too. A bad name or number logs one "weather: ..." line and changes nothing.

namespace WeatherConsole::Private
{
	void Say(const FString& Message)
	{
		UE_LOG(LogSeasonalWeather, Display, TEXT("weather: %s"), *Message);
	}

	UWeatherSubsystem* WeatherOf(UWorld* World)
	{
		UWeatherSubsystem* Weather = World ? World->GetSubsystem<UWeatherSubsystem>() : nullptr;
		if (!Weather)
		{
			Say(TEXT("this world has no weather"));
		}
		return Weather;
	}

	bool HasArgs(const TArray<FString>& Args, const int32 Needed, const TCHAR* Usage)
	{
		if (Args.Num() >= Needed)
		{
			return true;
		}
		Say(FString::Printf(TEXT("usage: %s"), Usage));
		return false;
	}

	bool ToNumber(const FString& Text, float& Out)
	{
		if (LexTryParseString(Out, *Text) && FMath::IsFinite(Out))
		{
			return true;
		}
		Say(FString::Printf(TEXT("not a number: '%s'"), *Text));
		return false;
	}

	bool ToInteger(const FString& Text, int32& Out)
	{
		if (LexTryParseString(Out, *Text))
		{
			return true;
		}
		Say(FString::Printf(TEXT("not a whole number: '%s'"), *Text));
		return false;
	}

	bool ToSwitch(const FString& Text, bool& Out)
	{
		if (Text == TEXT("0") || Text == TEXT("1"))
		{
			Out = Text == TEXT("1");
			return true;
		}
		Say(FString::Printf(TEXT("expected 0 or 1, got '%s'"), *Text));
		return false;
	}

	// A WeatherNames name, ignoring case: console input is typed by hand (weather_ref's names are case-sensitive).
	template <typename EnumType>
	bool ToName(const FString& Text, FString (*NameOf)(EnumType), const TCHAR* What, EnumType& Out)
	{
		TArray<FString> Known;
		for (const EnumType Each : TEnumRange<EnumType>())
		{
			const FString Name = NameOf(Each);
			if (Name.Equals(Text, ESearchCase::IgnoreCase))
			{
				Out = Each;
				return true;
			}
			Known.Add(Name);
		}
		Say(FString::Printf(TEXT("unknown %s '%s' (%s)"), What, *Text, *FString::Join(Known, TEXT(", "))));
		return false;
	}

	struct FOverrideField
	{
		const TCHAR* Name;
		float FWeatherOverride::* Member;
	};

	const FOverrideField OverrideFields[] = {
		{ TEXT("precip"), &FWeatherOverride::PrecipMmPerHour },
		{ TEXT("snow"), &FWeatherOverride::SnowFraction },
		{ TEXT("temp"), &FWeatherOverride::TemperatureC },
		{ TEXT("humidity"), &FWeatherOverride::Humidity },
		{ TEXT("winddir"), &FWeatherOverride::WindDirectionDeg },
		{ TEXT("windspeed"), &FWeatherOverride::WindSpeedMps },
		{ TEXT("thunder"), &FWeatherOverride::ThunderPotential },
		{ TEXT("cloud"), &FWeatherOverride::CloudCover },
	};

	void RunSeason(const TArray<FString>& Args, UWorld* World)
	{
		EWeatherSeason Season = EWeatherSeason::Spring;
		int32 Day = 0;
		if (!HasArgs(Args, 1, TEXT("weather.Season <Name> [Day]")) || !ToName(Args[0], &WeatherNames::Season, TEXT("season"), Season)
			|| (Args.Num() > 1 && !ToInteger(Args[1], Day)))
		{
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->SetSeason(Season, Day);
			Weather->ApplyNow();
		}
	}

	void RunType(const TArray<FString>& Args, UWorld* World)
	{
		EWeatherType Type = EWeatherType::Clear;
		if (!HasArgs(Args, 1, TEXT("weather.Type <Name> [noblend]")) || !ToName(Args[0], &WeatherNames::Type, TEXT("weather type"), Type))
		{
			return;
		}
		const bool bNoBlend = Args.Num() > 1 && Args[1].Equals(TEXT("noblend"), ESearchCase::IgnoreCase);
		if (Args.Num() > 1 && !bNoBlend)
		{
			Say(FString::Printf(TEXT("unknown option '%s' (noblend)"), *Args[1]));
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->SetWeatherType(Type, !bNoBlend);
			Weather->ApplyNow();
		}
	}

	void RunTime(const TArray<FString>& Args, UWorld* World)
	{
		float Hour = 0.f;
		if (!HasArgs(Args, 1, TEXT("weather.Time <Hour>")) || !ToNumber(Args[0], Hour))
		{
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->SetTimeOfDay(Hour);
			Weather->ApplyNow();
		}
	}

	void RunAdvance(const TArray<FString>& Args, UWorld* World)
	{
		float Hours = 0.f;
		if (!HasArgs(Args, 1, TEXT("weather.Advance <GameHours>")) || !ToNumber(Args[0], Hours))
		{
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->AdvanceGameTime(Hours);
			Weather->ApplyNow();
		}
	}

	void RunTimeScale(const TArray<FString>& Args, UWorld* World)
	{
		float Scale = 0.f;
		if (!HasArgs(Args, 1, TEXT("weather.TimeScale <GameSecondsPerRealSecond>")) || !ToNumber(Args[0], Scale))
		{
			return;
		}
		if (Scale < 0.f)
		{
			Say(TEXT("the time scale cannot be negative"));
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->SetTimeScale(Scale);
			Weather->ApplyNow();
		}
	}

	void RunPause(const TArray<FString>& Args, UWorld* World)
	{
		bool bPaused = false;
		if (!HasArgs(Args, 1, TEXT("weather.Pause <0|1>")) || !ToSwitch(Args[0], bPaused))
		{
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->SetPaused(bPaused);
			Weather->ApplyNow();
		}
	}

	void RunRunInEditor(const TArray<FString>& Args, UWorld* World)
	{
		bool bRun = false;
		if (!HasArgs(Args, 1, TEXT("weather.RunInEditor <0|1>")) || !ToSwitch(Args[0], bRun))
		{
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			Weather->SetRunInEditor(bRun);
			Weather->ApplyNow();
		}
	}

	void RunOverride(const TArray<FString>& Args, UWorld* World)
	{
		float Value = 0.f;
		if (!HasArgs(Args, 2, TEXT("weather.Override <precip|snow|temp|humidity|winddir|windspeed|thunder|cloud> <Value>")))
		{
			return;
		}
		const FOverrideField* Field = nullptr;
		for (const FOverrideField& Each : OverrideFields)
		{
			if (Args[0].Equals(Each.Name, ESearchCase::IgnoreCase))
			{
				Field = &Each;
				break;
			}
		}
		if (!Field)
		{
			Say(FString::Printf(TEXT("unknown override field '%s' (precip, snow, temp, humidity, winddir, windspeed, thunder, cloud)"), *Args[0]));
			return;
		}
		if (!ToNumber(Args[1], Value))
		{
			return;
		}
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			FWeatherOverride Override = Weather->GetOverride();
			Override.*(Field->Member) = Value;
			Weather->SetOverride(Override);
			Weather->ApplyNow();
		}
	}

	void RunState(const TArray<FString>& Args, UWorld* World)
	{
		if (UWeatherSubsystem* Weather = WeatherOf(World))
		{
			UE_LOG(LogSeasonalWeather, Display, TEXT("%s"), *Weather->GetStateJson());
		}
	}

	FAutoConsoleCommandWithWorldAndArgs CmdSeason(TEXT("weather.Season"),
		TEXT("weather.Season <Spring|Summer|Autumn|Winter> [Day]: go to day Day (default 0) of the season, keeping the hour."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunSeason));
	FAutoConsoleCommandWithWorldAndArgs CmdType(TEXT("weather.Type"),
		TEXT("weather.Type <Clear|FairCumulus|Overcast|FrontalRain|Thunderstorm|Fog|Snow|Blizzard> [noblend]: request a weather type."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunType));
	FAutoConsoleCommandWithWorldAndArgs CmdTime(TEXT("weather.Time"),
		TEXT("weather.Time <Hour>: the hour of the current game day, 0 to 24."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunTime));
	FAutoConsoleCommandWithWorldAndArgs CmdAdvance(TEXT("weather.Advance"),
		TEXT("weather.Advance <GameHours>: move the clock on (or back, never before day 0)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunAdvance));
	FAutoConsoleCommandWithWorldAndArgs CmdTimeScale(TEXT("weather.TimeScale"),
		TEXT("weather.TimeScale <x>: game seconds per real second (24 is one game day per real hour)."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunTimeScale));
	FAutoConsoleCommandWithWorldAndArgs CmdPause(TEXT("weather.Pause"),
		TEXT("weather.Pause <0|1>: stop or restart the clock."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunPause));
	FAutoConsoleCommandWithWorldAndArgs CmdRunInEditor(TEXT("weather.RunInEditor"),
		TEXT("weather.RunInEditor <0|1>: let the clock run in the editor world."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunRunInEditor));
	FAutoConsoleCommandWithWorldAndArgs CmdOverride(TEXT("weather.Override"),
		TEXT("weather.Override <precip|snow|temp|humidity|winddir|windspeed|thunder|cloud> <Value>: set one value of the manual override."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunOverride));
	FAutoConsoleCommandWithWorldAndArgs CmdState(TEXT("weather.State"),
		TEXT("weather.State: log the weather state as JSON."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RunState));
}
