#include "WeatherAstronomy.h"

#include <cmath>

namespace WeatherAstronomy::Private
{
	// weather_ref.astronomy._clamp.
	double Clamp(const double X, const double Lo, const double Hi)
	{
		return FMath::Min(FMath::Max(X, Lo), Hi);
	}

	// The pair weather_ref.astronomy._elevation_azimuth returns.
	struct FElevationAzimuth
	{
		double El = 0.0;
		double Az = 0.0;
	};

	// weather_ref.astronomy._elevation_azimuth: elevation and azimuth (from north, clockwise) of a body at declination Decl
	// and hour angle Ha, seen from latitude Lat.
	FElevationAzimuth ElevationAzimuth(const double Lat, const double Decl, const double Ha)
	{
		const double El = std::asin(Clamp(std::sin(Lat * Deg) * std::sin(Decl * Deg)
			+ std::cos(Lat * Deg) * std::cos(Decl * Deg) * std::cos(Ha * Deg), -1.0, 1.0)) * Rad;
		const double Az = Wrap(std::atan2(std::sin(Ha * Deg), std::cos(Ha * Deg) * std::sin(Lat * Deg)
			- std::tan(Decl * Deg) * std::cos(Lat * Deg)) * Rad + 180.0, 360.0);
		return { El, Az };
	}
}

// The functions below follow weather_ref/astronomy.py statement for statement, with its local names and its order of
// operations: angles go through std:: trigonometry on double with Deg / Rad, and squares are products, as in the NOAA
// spreadsheet.

double WeatherAstronomy::Wrap(double X, double M)
{
	return X - M * std::floor(X / M);
}

double WeatherAstronomy::JulianDay(int32 Year, int32 Month, int32 Day)
{
	if (Month <= 2)
	{
		Year -= 1;
		Month += 12;
	}
	const double A = std::floor(Year / 100.0);
	const double B = 2.0 - A + std::floor(A / 4.0);
	return std::floor(365.25 * (Year + 4716)) + std::floor(30.6001 * (Month + 1)) + Day + B - 1524.5;
}

double WeatherAstronomy::DateJulianDay(int32 Year, double DayOfYear, double TimezoneHours)
{
	return JulianDay(Year, 1, 1) + (DayOfYear - 1.0) + 0.5 - TimezoneHours / 24.0;
}

FWeatherSun WeatherAstronomy::Sun(int32 Year, double DayOfYear, double LocalHour, double LatDeg, double LonDeg, double TzHours)
{
	using namespace WeatherAstronomy::Private;
	const double Jd = DateJulianDay(Year, DayOfYear, TzHours);
	const double T = (Jd - 2451545.0) / 36525.0;

	const double L0 = Wrap(280.46646 + T * (36000.76983 + T * 0.0003032), 360.0);
	const double M = 357.52911 + T * (35999.05029 - 0.0001537 * T);
	const double E = 0.016708634 - T * (0.000042037 + 0.0000001267 * T);
	const double C = (std::sin(M * Deg) * (1.914602 - T * (0.004817 + 0.000014 * T))
		+ std::sin(2.0 * M * Deg) * (0.019993 - 0.000101 * T) + std::sin(3.0 * M * Deg) * 0.000289);
	const double Om = 125.04 - 1934.136 * T;
	const double Lam = L0 + C - 0.00569 - 0.00478 * std::sin(Om * Deg);
	const double Eps = 23.0 + (26.0 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60.0) / 60.0 + 0.00256 * std::cos(Om * Deg);

	const double Decl = std::asin(std::sin(Eps * Deg) * std::sin(Lam * Deg)) * Rad;
	const double TanHalf = std::tan(Eps / 2.0 * Deg);
	const double Y = TanHalf * TanHalf;
	const double Eot = 4.0 * Rad * (Y * std::sin(2.0 * L0 * Deg) - 2.0 * E * std::sin(M * Deg)
		+ 4.0 * E * Y * std::sin(M * Deg) * std::cos(2.0 * L0 * Deg)
		- 0.5 * Y * Y * std::sin(4.0 * L0 * Deg) - 1.25 * E * E * std::sin(2.0 * M * Deg));

	const double Tst = Wrap(LocalHour * 60.0 + Eot + 4.0 * LonDeg - 60.0 * TzHours, 1440.0);
	const double Ha = Tst / 4.0 - 180.0;
	const double Ra = Wrap(std::atan2(std::cos(Eps * Deg) * std::sin(Lam * Deg), std::cos(Lam * Deg)) * Rad, 360.0);
	const auto [El, Az] = ElevationAzimuth(LatDeg, Decl, Ha);
	return FWeatherSun{ .ElevationDeg = El, .AzimuthDeg = Az, .DeclinationDeg = Decl, .EquationOfTimeMin = Eot,
		.RightAscensionDeg = Ra, .HourAngleDeg = Ha, .EclipticLongitudeDeg = Lam, .ObliquityDeg = Eps };
}

void WeatherAstronomy::SunriseSunset(int32 Year, double DayOfYear, double LatDeg, double LonDeg, double TzHours, double ZenithDeg,
	double& OutSunrise, double& OutSunset, double& OutDayLength)
{
	using namespace WeatherAstronomy::Private;
	const FWeatherSun S = Sun(Year, DayOfYear, 12.0, LatDeg, LonDeg, TzHours);   // its declination and equation of time do not depend on the hour
	const double CosH = Clamp(std::cos(ZenithDeg * Deg) / (std::cos(LatDeg * Deg) * std::cos(S.DeclinationDeg * Deg))
		- std::tan(LatDeg * Deg) * std::tan(S.DeclinationDeg * Deg), -1.0, 1.0);
	const double H = std::acos(CosH) * Rad;
	const double Noon = (720.0 - 4.0 * LonDeg - S.EquationOfTimeMin + 60.0 * TzHours) / 60.0;
	OutSunrise = Noon - 4.0 * H / 60.0;
	OutSunset = Noon + 4.0 * H / 60.0;
	OutDayLength = 8.0 * H / 60.0;
}

FWeatherMoon WeatherAstronomy::Moon(double GameDays, const FWeatherSun& Sun, double LatDeg, double SynodicDays, double OffsetDays)
{
	using namespace WeatherAstronomy::Private;
	const double Phase = Wrap((GameDays + OffsetDays) / SynodicDays, 1.0);
	const double Illumination = (1.0 - std::cos(2.0 * UE_DOUBLE_PI * Phase)) / 2.0;   // UE_DOUBLE_PI is math.pi; UE_PI is a float
	const double Eps = Sun.ObliquityDeg;
	const double LamM = Sun.EclipticLongitudeDeg + 360.0 * Phase;
	const double DeclM = std::asin(std::sin(Eps * Deg) * std::sin(LamM * Deg)) * Rad;
	const double RaM = Wrap(std::atan2(std::cos(Eps * Deg) * std::sin(LamM * Deg), std::cos(LamM * Deg)) * Rad, 360.0);
	const double HaM = Wrap(Sun.HourAngleDeg + Sun.RightAscensionDeg - RaM + 180.0, 360.0) - 180.0;
	const auto [El, Az] = ElevationAzimuth(LatDeg, DeclM, HaM);
	return FWeatherMoon{ .Phase = Phase, .Illumination = Illumination, .ElevationDeg = El, .AzimuthDeg = Az, .DeclinationDeg = DeclM };
}

FVector WeatherAstronomy::Direction(double ElevationDeg, double AzimuthDeg, double NorthYawDeg)
{
	return FVector(std::cos(ElevationDeg * Deg) * std::cos((AzimuthDeg + NorthYawDeg) * Deg),
		std::cos(ElevationDeg * Deg) * std::sin((AzimuthDeg + NorthYawDeg) * Deg), std::sin(ElevationDeg * Deg));
}

FRotator WeatherAstronomy::LightRotation(double ElevationDeg, double AzimuthDeg, double NorthYawDeg)
{
	return FRotator(-ElevationDeg, Wrap(AzimuthDeg + NorthYawDeg + 180.0, 360.0), 0.0);
}
