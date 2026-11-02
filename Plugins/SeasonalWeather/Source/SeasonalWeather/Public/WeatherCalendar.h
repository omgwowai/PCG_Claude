#pragma once

#include "CoreMinimal.h"
#include "WeatherParams.h"
#include "WeatherTypes.h"
#include "WeatherCalendar.generated.h"

/** weather_ref.calendar.CalendarState: the calendar at one game time (spec §6.1). */
USTRUCT(BlueprintType)
struct SEASONALWEATHER_API FWeatherCalendarState
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") double GameSeconds = 0.0;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") int32 DayIndex = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") double Hour = 0.0;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") EWeatherSeason Season = EWeatherSeason::Spring;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") EWeatherSeason NextSeason = EWeatherSeason::Summer;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") int32 DayInSeason = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") double SeasonFraction = 0.0;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") bool bInTransition = false;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") double TransitionProgress = 0.0;
	/** Spring, Summer, Autumn, Winter. */
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") FVector4 SeasonWeights = FVector4(1.0, 0.0, 0.0, 0.0);
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") int32 Year = 2026;
	UPROPERTY(BlueprintReadOnly, Category = "Calendar") double DayOfYear = 79.0;
};

/** weather_ref/calendar.py, operation for operation. Game second 0 is midnight of day 0, the first day of StartSeason. */
namespace WeatherCalendar
{
	/** weather_ref.calendar.evaluate: over the last TransitionDays of a season the weights cross-fade into the next one. */
	SEASONALWEATHER_API FWeatherCalendarState Evaluate(double GameSeconds, const FWeatherCalendarParams& Params);
	/** weather_ref.calendar.seconds_for: Hour on day DayInSeason of Season, in the cycle of four seasons that holds
	 *  CurrentSeconds (a negative time counts as 0); day and hour are clamped to the season and the day. */
	SEASONALWEATHER_API double SecondsFor(const FWeatherCalendarParams& Params, double CurrentSeconds, EWeatherSeason Season, int32 DayInSeason, double Hour);
	/** weather_ref.calendar.with_hour: the same game day at Hour, clamped to 0..23.999999. */
	SEASONALWEATHER_API double WithHour(double CurrentSeconds, double Hour);
}
