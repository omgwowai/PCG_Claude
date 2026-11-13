#include "WeatherTypes.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherTypes)

namespace WeatherTypes::Private
{
	// weather_ref/params.py SEASONS and WEATHER_TYPES, in enum order.
	const TCHAR* const SeasonNames[] = { TEXT("Spring"), TEXT("Summer"), TEXT("Autumn"), TEXT("Winter") };
	const TCHAR* const TypeNames[] = {
		TEXT("Clear"), TEXT("FairCumulus"), TEXT("Overcast"), TEXT("FrontalRain"), TEXT("Thunderstorm"), TEXT("Fog"), TEXT("Snow"), TEXT("Blizzard")
	};
	static_assert(UE_ARRAY_COUNT(SeasonNames) == static_cast<SIZE_T>(EWeatherSeason::Count), "one name per season");
	static_assert(UE_ARRAY_COUNT(TypeNames) == static_cast<SIZE_T>(EWeatherType::Count), "one name per weather type");

	// The name of Value, or an empty string for a value outside the table (Count or bad data).
	template <typename EnumType, int32 N>
	FString ToName(const TCHAR* const (&Names)[N], const EnumType Value)
	{
		const int32 Index = static_cast<int32>(Value);
		return (Index >= 0 && Index < N) ? FString(Names[Index]) : FString();
	}

	// Case-sensitive, like weather_ref: "spring" is not a season. Out is left unchanged when Text matches no name.
	template <typename EnumType, int32 N>
	bool FromName(const TCHAR* const (&Names)[N], const FStringView Text, EnumType& Out)
	{
		for (int32 Index = 0; Index < N; ++Index)
		{
			if (Text.Equals(Names[Index], ESearchCase::CaseSensitive))
			{
				Out = static_cast<EnumType>(Index);
				return true;
			}
		}
		return false;
	}

	// weather_ref/sky.py LOOK_FIELDS, in order.
	constexpr double FWeatherLook::* const LookFields[] = {
		&FWeatherLook::SunIntensity, &FWeatherLook::MoonIntensity, &FWeatherLook::SkyLight, &FWeatherLook::FogDensity,
		&FWeatherLook::FogHeightFalloff, &FWeatherLook::WhiteTempOffset, &FWeatherLook::Saturation, &FWeatherLook::Contrast,
		&FWeatherLook::ExposureBias, &FWeatherLook::CloudCover
	};
}

FString WeatherNames::Season(EWeatherSeason Season)
{
	return WeatherTypes::Private::ToName(WeatherTypes::Private::SeasonNames, Season);
}

FString WeatherNames::Type(EWeatherType Type)
{
	return WeatherTypes::Private::ToName(WeatherTypes::Private::TypeNames, Type);
}

bool WeatherNames::ParseSeason(const FString& Name, EWeatherSeason& Out)
{
	return WeatherTypes::Private::FromName(WeatherTypes::Private::SeasonNames, Name, Out);
}

bool WeatherNames::ParseType(const FString& Name, EWeatherType& Out)
{
	return WeatherTypes::Private::FromName(WeatherTypes::Private::TypeNames, Name, Out);
}

FVector3f FWeatherOverride::WindVector() const
{
	constexpr double Deg = 0.017453292519943295;   // weather_ref.astronomy.DEG
	const double Direction = static_cast<double>(WindDirectionDeg) * Deg;
	const double Speed = WindSpeedMps;
	return FVector3f(static_cast<float>(-FMath::Cos(Direction) * Speed), static_cast<float>(-FMath::Sin(Direction) * Speed), 0.f);
}

FWeatherLook FWeatherLook::Lerp(const FWeatherLook& A, const FWeatherLook& B, double T)
{
	FWeatherLook Out;
	for (double FWeatherLook::* const Field : WeatherTypes::Private::LookFields)
	{
		Out.*Field = A.*Field + (B.*Field - A.*Field) * T;
	}
	return Out;
}

FWeatherLook FWeatherLook::Combine(const FWeatherLook& TypeLook, const FWeatherLook& SeasonLook)
{
	FWeatherLook Out;
	Out.SunIntensity = TypeLook.SunIntensity * SeasonLook.SunIntensity;
	Out.MoonIntensity = TypeLook.MoonIntensity * SeasonLook.MoonIntensity;
	Out.SkyLight = TypeLook.SkyLight * SeasonLook.SkyLight;
	Out.FogDensity = TypeLook.FogDensity * SeasonLook.FogDensity;
	Out.FogHeightFalloff = TypeLook.FogHeightFalloff * SeasonLook.FogHeightFalloff;
	Out.WhiteTempOffset = TypeLook.WhiteTempOffset + SeasonLook.WhiteTempOffset;
	Out.Saturation = TypeLook.Saturation * SeasonLook.Saturation;
	Out.Contrast = TypeLook.Contrast * SeasonLook.Contrast;
	Out.ExposureBias = TypeLook.ExposureBias + SeasonLook.ExposureBias;
	Out.CloudCover = TypeLook.CloudCover;
	return Out;
}
