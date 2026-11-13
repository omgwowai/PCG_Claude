#include "WeatherCalendar.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherCalendar)

namespace WeatherCalendar::Private
{
	constexpr double DayS = 86400.0;         // weather_ref.calendar.DAY_S
	constexpr double LastHour = 23.999999;   // weather_ref.calendar._LAST_HOUR: hour inputs are clamped to 0..LastHour

	// Python's A // B: the quotient rounded toward minus infinity, where C++'s / rounds toward zero (-1 / 7 is 0, not -1).
	int64 FloorDiv(const int64 A, const int64 B)
	{
		const int64 Quotient = A / B;
		return (A % B != 0 && (A < 0) != (B < 0)) ? Quotient - 1 : Quotient;
	}

	// Python's A % B: the remainder takes the sign of B, so FloorMod(-1, 4) is 3 where C++'s -1 % 4 is -1.
	int64 FloorMod(const int64 A, const int64 B)
	{
		return A - FloorDiv(A, B) * B;
	}

	// weather_ref.calendar._clamp.
	template <typename T>
	T Clamp(const T X, const T Lo, const T Hi)
	{
		return FMath::Min(FMath::Max(X, Lo), Hi);
	}
}

// The three functions below follow weather_ref/calendar.py statement for statement: every // and % of the reference is
// FloorDiv / FloorMod, and every day or season count is an int64.

FWeatherCalendarState WeatherCalendar::Evaluate(double GameSeconds, const FWeatherCalendarParams& Params)
{
	using namespace WeatherCalendar::Private;
	const int64 L = Params.SeasonLengthDays;
	const double T = Params.TransitionDays;
	const int64 Start = static_cast<int64>(Params.StartSeason);

	const double Total = GameSeconds / DayS;
	const int64 DayIndex = static_cast<int64>(FMath::FloorToDouble(Total));
	const double Hour = (Total - static_cast<double>(DayIndex)) * 24.0;

	const int64 Ord = FloorDiv(DayIndex, L);
	const int64 Seq = Start + Ord;
	const int32 Season = static_cast<int32>(FloorMod(Seq, 4));
	const int32 Next = static_cast<int32>(FloorMod(Season + 1, 4));
	const int64 DayInSeason = DayIndex - Ord * L;
	const double Pos = static_cast<double>(DayInSeason) + Hour / 24.0;
	const double Fraction = Pos / static_cast<double>(L);

	const bool bInTransition = T > 0.0 && Pos >= static_cast<double>(L) - T;
	const double Progress = bInTransition ? FMath::Min(1.0, (Pos - (static_cast<double>(L) - T)) / T) : 0.0;
	FVector4 Weights(0.0, 0.0, 0.0, 0.0);
	Weights[Season] = 1.0 - Progress;
	Weights[Next] += Progress;

	const double D0 = Params.SeasonStartDoy[Season];
	double D1 = Params.SeasonStartDoy[Next];
	if (D1 <= D0)
	{
		D1 += 365.0;
	}
	double Doy = D0 + Fraction * (D1 - D0);
	int64 Year = Params.BaseYear + FloorDiv(Seq, 4);
	if (Doy >= 366.0)
	{
		Doy -= 365.0;
		Year += 1;
	}

	FWeatherCalendarState State;
	State.GameSeconds = GameSeconds;
	State.DayIndex = static_cast<int32>(DayIndex);
	State.Hour = Hour;
	State.Season = static_cast<EWeatherSeason>(Season);
	State.NextSeason = static_cast<EWeatherSeason>(Next);
	State.DayInSeason = static_cast<int32>(DayInSeason);
	State.SeasonFraction = Fraction;
	State.bInTransition = bInTransition;
	State.TransitionProgress = Progress;
	State.SeasonWeights = Weights;
	State.Year = static_cast<int32>(Year);
	State.DayOfYear = Doy;
	return State;
}

double WeatherCalendar::SecondsFor(const FWeatherCalendarParams& Params, double CurrentSeconds, EWeatherSeason Season, int32 DayInSeason, double Hour)
{
	using namespace WeatherCalendar::Private;
	const int64 L = Params.SeasonLengthDays;
	const int64 Start = static_cast<int64>(Params.StartSeason);
	const double Current = FMath::Max(0.0, CurrentSeconds);
	const int64 Cycle = FloorDiv(FloorDiv(static_cast<int64>(FMath::FloorToDouble(Current / DayS)), L), 4);
	const int64 Ord = Cycle * 4 + FloorMod(static_cast<int64>(Season) - Start, 4);
	const int64 Day = Clamp<int64>(DayInSeason, 0, L - 1);
	Hour = Clamp(Hour, 0.0, LastHour);
	return static_cast<double>(Ord * L + Day) * DayS + Hour * 3600.0;
}

double WeatherCalendar::WithHour(double CurrentSeconds, double Hour)
{
	using namespace WeatherCalendar::Private;
	return FMath::FloorToDouble(CurrentSeconds / DayS) * DayS + Clamp(Hour, 0.0, LastHour) * 3600.0;
}
