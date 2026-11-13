#pragma once

#include "CoreMinimal.h"

/** weather_ref.astronomy.Sun: the sun at one moment (spec §6.1); angles in degrees, the equation of time in minutes. */
struct SEASONALWEATHER_API FWeatherSun
{
	double ElevationDeg = 0.0, AzimuthDeg = 0.0, DeclinationDeg = 0.0, EquationOfTimeMin = 0.0;
	double RightAscensionDeg = 0.0, HourAngleDeg = 0.0, EclipticLongitudeDeg = 0.0, ObliquityDeg = 23.44;
};

/** weather_ref.astronomy.Moon: Phase 0 is new and 0.5 full, Illumination the lit fraction of the disc; angles in degrees. */
struct SEASONALWEATHER_API FWeatherMoon
{
	double Phase = 0.0, Illumination = 0.0, ElevationDeg = 0.0, AzimuthDeg = 0.0, DeclinationDeg = 0.0;
};

/** weather_ref/astronomy.py, operation for operation: the NOAA solar-position algorithm (after Meeus), sunrise and sunset,
 *  the moon placed from its phase, and the rotation of a light that shines away from a body. Angles are in degrees; the
 *  trigonometry is std:: on double through Deg / Rad, never FMath::DegreesToRadians. */
namespace WeatherAstronomy
{
	inline constexpr double Deg = 0.017453292519943295;   // == Python math.pi / 180
	inline constexpr double Rad = 57.29577951308232;      // == Python 180 / math.pi
	/** weather_ref.astronomy.wrap: X - M * floor(X / M), X brought into [0, M) for M > 0. */
	SEASONALWEATHER_API double Wrap(double X, double M);
	/** weather_ref.astronomy.julian_day: the Julian day at 00:00 UTC of a Gregorian date (Meeus ch. 7). */
	SEASONALWEATHER_API double JulianDay(int32 Year, int32 Month, int32 Day);
	/** weather_ref.astronomy.date_jd: the Julian day of local noon of day DayOfYear (1 = 1 January, may be fractional) in
	 *  zone TimezoneHours (hours east of UTC). */
	SEASONALWEATHER_API double DateJulianDay(int32 Year, double DayOfYear, double TimezoneHours);
	/** weather_ref.astronomy.sun: the sun at LocalHour (zone time) of day DayOfYear, seen from LatDeg, LonDeg (east positive)
	 *  in zone TzHours. The orbital elements, declination and equation of time are those of the day's local noon. */
	SEASONALWEATHER_API FWeatherSun Sun(int32 Year, double DayOfYear, double LocalHour, double LatDeg, double LonDeg, double TzHours);
	/** weather_ref.astronomy.sunrise_sunset: sunrise, sunset and day length in hours of zone time, not wrapped into 0..24.
	 *  The clamp gives polar day noon -/+ 12 h (24 h) and polar night both at noon (0 h). */
	SEASONALWEATHER_API void SunriseSunset(int32 Year, double DayOfYear, double LatDeg, double LonDeg, double TzHours, double ZenithDeg,
		double& OutSunrise, double& OutSunset, double& OutDayLength);
	/** weather_ref.astronomy.moon: the phase counts GameDays (SynodicDays a cycle, shifted by OffsetDays; plan ruling P2),
	 *  and the moon stands on the ecliptic 360 x Phase degrees east of Sun (the sun of the same moment), seen from LatDeg. */
	SEASONALWEATHER_API FWeatherMoon Moon(double GameDays, const FWeatherSun& Sun, double LatDeg, double SynodicDays, double OffsetDays);
	/** weather_ref.astronomy.direction: the unit vector towards a body; world +X is north and +Y east, turned by NorthYawDeg. */
	SEASONALWEATHER_API FVector Direction(double ElevationDeg, double AzimuthDeg, double NorthYawDeg);
	/** weather_ref.astronomy.light_rotation: a directional light that shines away from the body, along -Direction:
	 *  pitch -elevation, yaw Wrap(azimuth + north + 180, 360), roll 0. */
	SEASONALWEATHER_API FRotator LightRotation(double ElevationDeg, double AzimuthDeg, double NorthYawDeg);
}
