#include "WeatherGpu.h"

#include "DataDrivenShaderPlatformInfo.h"
#include "GlobalShader.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "ShaderParameterStruct.h"

DECLARE_GPU_STAT_NAMED(WeatherFieldsFill, TEXT("Weather.Fields.Fill"));
DECLARE_GPU_STAT_NAMED(WeatherFieldsReadTexels, TEXT("Weather.Fields.ReadTexels"));

namespace
{
	bool SupportsSM5(const FGlobalShaderPermutationParameters& Parameters)
	{
		return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
	}
}

class FWeatherFill2DCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FWeatherFill2DCS);
	SHADER_USE_PARAMETER_STRUCT(FWeatherFill2DCS, FGlobalShader);
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(FVector4f, Value)
		SHADER_PARAMETER(FIntVector, Size)
		SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<float4>, Out2D)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return SupportsSM5(Parameters); }
};
IMPLEMENT_GLOBAL_SHADER(FWeatherFill2DCS, "/Plugin/SeasonalWeather/Private/WeatherFields.usf", "Fill2DCS", SF_Compute);

class FWeatherFill3DCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FWeatherFill3DCS);
	SHADER_USE_PARAMETER_STRUCT(FWeatherFill3DCS, FGlobalShader);
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(FVector4f, Value)
		SHADER_PARAMETER(FIntVector, Size)
		SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture3D<float4>, Out3D)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return SupportsSM5(Parameters); }
};
IMPLEMENT_GLOBAL_SHADER(FWeatherFill3DCS, "/Plugin/SeasonalWeather/Private/WeatherFields.usf", "Fill3DCS", SF_Compute);

class FWeatherRead2DCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FWeatherRead2DCS);
	SHADER_USE_PARAMETER_STRUCT(FWeatherRead2DCS, FGlobalShader);
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_RDG_TEXTURE(Texture2D<float4>, Src2D)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int4>, Coords)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, OutValues)
		SHADER_PARAMETER(uint32, NumCoords)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return SupportsSM5(Parameters); }
};
IMPLEMENT_GLOBAL_SHADER(FWeatherRead2DCS, "/Plugin/SeasonalWeather/Private/WeatherFields.usf", "Read2DCS", SF_Compute);

class FWeatherRead3DCS : public FGlobalShader
{
	DECLARE_GLOBAL_SHADER(FWeatherRead3DCS);
	SHADER_USE_PARAMETER_STRUCT(FWeatherRead3DCS, FGlobalShader);
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_RDG_TEXTURE(Texture3D<float4>, Src3D)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int4>, Coords)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, OutValues)
		SHADER_PARAMETER(uint32, NumCoords)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) { return SupportsSM5(Parameters); }
};
IMPLEMENT_GLOBAL_SHADER(FWeatherRead3DCS, "/Plugin/SeasonalWeather/Private/WeatherFields.usf", "Read3DCS", SF_Compute);

void WeatherGpu::AddFillPass(FRDGBuilder& GraphBuilder, FRDGTextureRef Texture, const FVector4f& Value)
{
	RDG_EVENT_SCOPE_STAT(GraphBuilder, WeatherFieldsFill, "Weather.Fields.Fill");
	const FRDGTextureDesc& Desc = Texture->Desc;
	FGlobalShaderMap* ShaderMap = GetGlobalShaderMap(GMaxRHIFeatureLevel);
	if (Desc.Dimension == ETextureDimension::Texture3D)
	{
		const FIntVector Size(Desc.Extent.X, Desc.Extent.Y, Desc.Depth);
		FWeatherFill3DCS::FParameters* Parameters = GraphBuilder.AllocParameters<FWeatherFill3DCS::FParameters>();
		Parameters->Value = Value;
		Parameters->Size = Size;
		Parameters->Out3D = GraphBuilder.CreateUAV(Texture);
		FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("Weather.Fields.Fill3D"), TShaderMapRef<FWeatherFill3DCS>(ShaderMap),
			Parameters, FComputeShaderUtils::GetGroupCount(Size, FIntVector(4, 4, 4)));
	}
	else
	{
		const FIntVector Size(Desc.Extent.X, Desc.Extent.Y, 1);
		FWeatherFill2DCS::FParameters* Parameters = GraphBuilder.AllocParameters<FWeatherFill2DCS::FParameters>();
		Parameters->Value = Value;
		Parameters->Size = Size;
		Parameters->Out2D = GraphBuilder.CreateUAV(Texture);
		FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("Weather.Fields.Fill2D"), TShaderMapRef<FWeatherFill2DCS>(ShaderMap),
			Parameters, FComputeShaderUtils::GetGroupCount(Size, FIntVector(8, 8, 1)));
	}
}

FRDGBufferRef WeatherGpu::AddReadTexelsPass(FRDGBuilder& GraphBuilder, FRDGTextureRef Texture, TConstArrayView<FIntVector4> Coords)
{
	check(Coords.Num() > 0);
	RDG_EVENT_SCOPE_STAT(GraphBuilder, WeatherFieldsReadTexels, "Weather.Fields.ReadTexels");
	FRDGBufferRef CoordBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("Weather.ReadTexels.Coords"), sizeof(FIntVector4),
		Coords.Num(), Coords.GetData(), sizeof(FIntVector4) * Coords.Num());
	FRDGBufferRef Out = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(FVector4f), Coords.Num()),
		TEXT("Weather.ReadTexels.Values"));
	FGlobalShaderMap* ShaderMap = GetGlobalShaderMap(GMaxRHIFeatureLevel);
	const FIntVector Groups = FComputeShaderUtils::GetGroupCount(Coords.Num(), 64);
	if (Texture->Desc.Dimension == ETextureDimension::Texture3D)
	{
		FWeatherRead3DCS::FParameters* Parameters = GraphBuilder.AllocParameters<FWeatherRead3DCS::FParameters>();
		Parameters->Src3D = Texture;
		Parameters->Coords = GraphBuilder.CreateSRV(CoordBuffer);
		Parameters->OutValues = GraphBuilder.CreateUAV(Out);
		Parameters->NumCoords = Coords.Num();
		FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("Weather.Fields.Read3D"), TShaderMapRef<FWeatherRead3DCS>(ShaderMap), Parameters, Groups);
	}
	else
	{
		FWeatherRead2DCS::FParameters* Parameters = GraphBuilder.AllocParameters<FWeatherRead2DCS::FParameters>();
		Parameters->Src2D = Texture;
		Parameters->Coords = GraphBuilder.CreateSRV(CoordBuffer);
		Parameters->OutValues = GraphBuilder.CreateUAV(Out);
		Parameters->NumCoords = Coords.Num();
		FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("Weather.Fields.Read2D"), TShaderMapRef<FWeatherRead2DCS>(ShaderMap), Parameters, Groups);
	}
	return Out;
}
