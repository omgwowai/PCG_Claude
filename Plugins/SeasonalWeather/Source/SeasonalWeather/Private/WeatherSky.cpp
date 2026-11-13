#include "WeatherSky.h"

namespace WeatherSky::Private
{
	// weather_ref.sky._clamp.
	double Clamp(const double X, const double Lo, const double Hi)
	{
		return FMath::Min(FMath::Max(X, Lo), Hi);
	}
}

// weather_ref/sky.py rig statement for statement, with its local names, its order and its operand order; both rotations
// are WeatherAstronomy::LightRotation, the twin of astronomy.light_rotation.

FWeatherRigValues WeatherSky::Compute(const FWeatherSun& Sun, const FWeatherMoon& Moon, const FWeatherLook& Look,
	const FWeatherSkyParams& Sky, double NorthYawDeg)
{
	using namespace WeatherSky::Private;
	const double Cloud = Look.CloudCover;
	const double Dim = 1.0 - Sky.CloudDimming * Cloud;
	const double Fade = Clamp((Sky.StarFadeStartDeg - Sun.ElevationDeg) / Sky.StarFadeRangeDeg, 0.0, 1.0);

	FWeatherRigValues Out;
	Out.SunLux = Sky.SunLux * Look.SunIntensity * Dim;
	Out.MoonLux = Sky.MoonLux * Look.MoonIntensity * Moon.Illumination * (Moon.ElevationDeg > 0.0 ? 1.0 : 0.0) * Dim;
	Out.SkyLightIntensity = Sky.SkyLightIntensity * Look.SkyLight;
	Out.FogDensity = Sky.FogDensity * Look.FogDensity;
	Out.FogHeightFalloff = Sky.FogHeightFalloff * Look.FogHeightFalloff;
	Out.WhiteTemp = Sky.WhiteTempK + Look.WhiteTempOffset;
	Out.Saturation = Look.Saturation;
	Out.Contrast = Look.Contrast;
	Out.ExposureBias = Look.ExposureBias;
	Out.StarIntensity = Fade * (1.0 - Cloud);
	Out.CloudCover = Cloud;
	Out.SunRotation = WeatherAstronomy::LightRotation(Sun.ElevationDeg, Sun.AzimuthDeg, NorthYawDeg);
	Out.MoonRotation = WeatherAstronomy::LightRotation(Moon.ElevationDeg, Moon.AzimuthDeg, NorthYawDeg);
	return Out;
}
