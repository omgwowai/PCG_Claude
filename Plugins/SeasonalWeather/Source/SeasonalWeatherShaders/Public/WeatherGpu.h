#pragma once

#include "CoreMinimal.h"
#include "RenderGraphDefinitions.h"

class FRDGBuilder;

namespace WeatherGpu
{
	/** Writes Value into every texel of a 2D or 3D texture. GPU event "Weather.Fields.Fill". */
	SEASONALWEATHERSHADERS_API void AddFillPass(FRDGBuilder& GraphBuilder, FRDGTextureRef Texture, const FVector4f& Value);
	/** Gathers the texels at Coords (x, y, z, unused) into a float4 structured buffer. GPU event "Weather.Fields.ReadTexels". */
	SEASONALWEATHERSHADERS_API FRDGBufferRef AddReadTexelsPass(FRDGBuilder& GraphBuilder, FRDGTextureRef Texture, TConstArrayView<FIntVector4> Coords);
}
