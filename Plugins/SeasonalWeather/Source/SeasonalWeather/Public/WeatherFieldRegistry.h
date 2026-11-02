#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "WeatherParams.h"
#include "WeatherFieldRegistry.generated.h"

class UTexture;

/** The GPU weather fields of spec §1.3, one render target per weather_params.json "fields" entry: 2D fields are
 *  UTextureRenderTarget2D, 3D fields UTextureRenderTargetVolume, both with a UAV. A render target is created on first
 *  use (plan ruling P1); Initialize allocates nothing. */
UCLASS()
class SEASONALWEATHER_API UWeatherFieldRegistry : public UObject
{
	GENERATED_BODY()
public:
	/** Forgets existing render targets when the extent changes. */
	void Initialize(const TArray<FWeatherFieldDesc>& InDescs, double InExtentMeters);
	UTexture* GetOrCreateField(FName Name);           // nullptr for an unknown name (plan ruling P1)
	UTexture* FindField(FName Name) const;             // nullptr until created
	TArray<FName> GetFieldNames() const;               // created fields only
	FIntVector GetFieldSize(FName Name) const;         // the resolved size, ZeroValue if unknown
	bool FillUniform(FName Name, const FLinearColor& Value);   // render thread, next frame
	/** Flushes rendering and waits for the GPU: tests and debugging only. */
	TArray<FLinearColor> ReadTexelsBlocking(FName Name, TConstArrayView<FIntVector> Coords);
private:
	const FWeatherFieldDesc* FindDesc(FName Name) const;
	TArray<FWeatherFieldDesc> Descs;
	double ExtentMeters = 512.0;
	UPROPERTY(Transient) TMap<FName, TObjectPtr<UTexture>> Fields;
};
