#include "WeatherFieldRegistry.h"

#include "Engine/TextureRenderTarget2D.h"
#include "Engine/TextureRenderTargetVolume.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderingThread.h"
#include "RHIGPUReadback.h"
#include "TextureResource.h"
#include "WeatherGpu.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherFieldRegistry)

namespace WeatherFieldRegistry::Private
{
	EPixelFormat PixelFormat(const EWeatherFieldFormat Format)
	{
		switch (Format)
		{
		case EWeatherFieldFormat::R16F:
			return PF_R16F;
		case EWeatherFieldFormat::R32F:
			return PF_R32_FLOAT;
		case EWeatherFieldFormat::RGBA16F:
		default:
			return PF_FloatRGBA;
		}
	}
}

void UWeatherFieldRegistry::Initialize(const TArray<FWeatherFieldDesc>& InDescs, double InExtentMeters)
{
	Descs = InDescs;
	if (InExtentMeters != ExtentMeters)
	{
		// Unreferenced now, the old render targets go with the next garbage collection.
		Fields.Empty();
		ExtentMeters = InExtentMeters;
	}
}

UTexture* UWeatherFieldRegistry::GetOrCreateField(FName Name)
{
	if (UTexture* Existing = FindField(Name))
	{
		return Existing;
	}
	const FWeatherFieldDesc* Desc = FindDesc(Name);
	if (!Desc)
	{
		return nullptr;
	}
	const FIntVector Size = Desc->ResolveSize(ExtentMeters);
	const EPixelFormat Format = WeatherFieldRegistry::Private::PixelFormat(Desc->Format);
	const FName BaseName(*FString::Printf(TEXT("RT_Weather_%s"), *Name.ToString()));
	UTexture* Field = nullptr;
	if (Desc->Dims == 3)
	{
		UTextureRenderTargetVolume* Volume = NewObject<UTextureRenderTargetVolume>(this,
			MakeUniqueObjectName(this, UTextureRenderTargetVolume::StaticClass(), BaseName));
		Volume->bSupportsUAV = true;
		Volume->ClearColor = FLinearColor::Transparent;
		Volume->Init(Size.X, Size.Y, Size.Z, Format);
		Volume->UpdateResourceImmediate(true);
		Field = Volume;
	}
	else
	{
		UTextureRenderTarget2D* Target = NewObject<UTextureRenderTarget2D>(this,
			MakeUniqueObjectName(this, UTextureRenderTarget2D::StaticClass(), BaseName));
		Target->bSupportsUAV = true;
		Target->ClearColor = FLinearColor::Transparent;
		Target->InitCustomFormat(Size.X, Size.Y, Format, true);
		Target->UpdateResourceImmediate(true);
		Field = Target;
	}
	Fields.Add(Name, Field);
	return Field;
}

UTexture* UWeatherFieldRegistry::FindField(FName Name) const
{
	const TObjectPtr<UTexture>* Found = Fields.Find(Name);
	return Found ? Found->Get() : nullptr;
}

TArray<FName> UWeatherFieldRegistry::GetFieldNames() const
{
	TArray<FName> Names;
	Fields.GetKeys(Names);
	return Names;
}

FIntVector UWeatherFieldRegistry::GetFieldSize(FName Name) const
{
	const FWeatherFieldDesc* Desc = FindDesc(Name);
	return Desc ? Desc->ResolveSize(ExtentMeters) : FIntVector::ZeroValue;
}

bool UWeatherFieldRegistry::FillUniform(FName Name, const FLinearColor& Value)
{
	UTextureRenderTarget* Target = Cast<UTextureRenderTarget>(GetOrCreateField(Name));
	FTextureRenderTargetResource* Resource = Target ? Target->GameThread_GetRenderTargetResource() : nullptr;
	if (!Resource)
	{
		return false;
	}
	const FVector4f V(Value.R, Value.G, Value.B, Value.A);
	ENQUEUE_RENDER_COMMAND(WeatherFillField)([Resource, V](FRHICommandListImmediate& RHICmdList)
	{
		FRDGBuilder GraphBuilder(RHICmdList);
		FRDGTextureRef Texture = Resource->GetRenderTargetTexture(GraphBuilder);
		WeatherGpu::AddFillPass(GraphBuilder, Texture, V);
		GraphBuilder.UseExternalAccessMode(Texture, ERHIAccess::SRVMask);
		GraphBuilder.Execute();
	});
	return true;
}

TArray<FLinearColor> UWeatherFieldRegistry::ReadTexelsBlocking(FName Name, TConstArrayView<FIntVector> Coords)
{
	TArray<FLinearColor> Result;
	UTextureRenderTarget* Target = Cast<UTextureRenderTarget>(FindField(Name));
	FTextureRenderTargetResource* Resource = Target ? Target->GameThread_GetRenderTargetResource() : nullptr;
	if (!Resource || Coords.Num() == 0)
	{
		return Result;
	}
	TArray<FIntVector4> Packed;
	for (const FIntVector& C : Coords)
	{
		Packed.Add(FIntVector4(C.X, C.Y, C.Z, 0));
	}
	TArray<FVector4f> Values;
	Values.SetNumZeroed(Packed.Num());
	FRHIGPUBufferReadback Readback(TEXT("Weather.ReadTexels"));
	ENQUEUE_RENDER_COMMAND(WeatherReadTexels)([Resource, &Packed, &Values, &Readback](FRHICommandListImmediate& RHICmdList)
	{
		const uint32 Bytes = Packed.Num() * sizeof(FVector4f);
		FRDGBuilder GraphBuilder(RHICmdList);
		FRDGTextureRef Texture = Resource->GetRenderTargetTexture(GraphBuilder);
		FRDGBufferRef Out = WeatherGpu::AddReadTexelsPass(GraphBuilder, Texture, Packed);
		AddEnqueueCopyPass(GraphBuilder, &Readback, Out, Bytes);
		GraphBuilder.UseExternalAccessMode(Texture, ERHIAccess::SRVMask);
		GraphBuilder.Execute();
		RHICmdList.SubmitAndBlockUntilGPUIdle();
		FMemory::Memcpy(Values.GetData(), Readback.Lock(Bytes), Bytes);
		Readback.Unlock();
	});
	FlushRenderingCommands();
	for (const FVector4f& V : Values)
	{
		Result.Add(FLinearColor(V.X, V.Y, V.Z, V.W));
	}
	return Result;
}

const FWeatherFieldDesc* UWeatherFieldRegistry::FindDesc(FName Name) const
{
	return Descs.FindByPredicate([Name](const FWeatherFieldDesc& Desc) { return Desc.Name == Name; });
}
