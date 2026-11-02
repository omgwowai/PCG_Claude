#pragma once

#include "CoreMinimal.h"
#include "WeatherAstronomy.h"
#include "WeatherParams.h"
#include "WeatherTypes.h"

/** weather_ref.sky.rig's result: the values of the sky actors (spec §1.5 parameter mapping, §6.1). Rotations in degrees. */
struct SEASONALWEATHER_API FWeatherRigValues
{
	double SunLux = 0.0, MoonLux = 0.0, SkyLightIntensity = 1.0, FogDensity = 0.02, FogHeightFalloff = 0.2;
	double WhiteTemp = 6500.0, Saturation = 1.0, Contrast = 1.0, ExposureBias = 0.0, StarIntensity = 0.0, CloudCover = 0.0;
	FRotator SunRotation = FRotator::ZeroRotator;
	FRotator MoonRotation = FRotator::ZeroRotator;
};

/** weather_ref/sky.py rig, operation for operation. The look's CloudCover dims both lights and hides the stars, which fade
 *  in over Sky.StarFadeRangeDeg as the sun sinks below Sky.StarFadeStartDeg; the moon lights only above the horizon, and
 *  the sun is not gated, as in the reference. */
namespace WeatherSky
{
	/** weather_ref.sky.rig, using Sun.ElevationDeg/AzimuthDeg and Moon.ElevationDeg/AzimuthDeg/Illumination. */
	SEASONALWEATHER_API FWeatherRigValues Compute(const FWeatherSun& Sun, const FWeatherMoon& Moon, const FWeatherLook& Look,
		const FWeatherSkyParams& Sky, double NorthYawDeg);
}
