#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "WeatherAstronomy.h"
#include "WeatherCalendar.h"
#include "WeatherFieldRegistry.h"
#include "WeatherOrchestrator.h"
#include "WeatherParams.h"
#include "WeatherSky.h"
#include "WeatherTypes.h"
#include "WeatherSubsystem.generated.h"

class AWeatherDomain;
class UMaterialParameterCollection;
class USeasonLookAsset;
class UStateTree;
class UTexture;
class UWeatherTypeAsset;

/** The weather of one world (spec §1.2, §9.1): the clock and calendar, the sun and moon, the two orchestrator StateTrees,
 *  and what they drive: the sky actors of the level's AWeatherDomain, MPC_Weather and the uniform override fields. It runs
 *  in game, PIE and Simulate worlds; in the editor world the clock stands still unless SetRunInEditor(true), and scripts
 *  call ApplyNow() after every set. A world without a domain keeps it inert: no fields, no assets, no output. */
UCLASS(BlueprintType)
class SEASONALWEATHER_API UWeatherSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;   // loads weather_params.json
	virtual void Deinitialize() override;                                       // stops the trees
	virtual void Tick(float DeltaTime) override;                                 // UpdateNow(DeltaTime)
	virtual TStatId GetStatId() const override;
	virtual bool IsTickableInEditor() const override { return true; }

	/** Advances the clock by RealDeltaSeconds * TimeScale (editor worlds only when RunInEditor), then updates everything. */
	void UpdateNow(float RealDeltaSeconds);

	UFUNCTION(BlueprintCallable, Category = "Weather") void SetSeason(EWeatherSeason Season, int32 DayInSeason = 0);   // keeps the hour
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetTimeOfDay(float Hour);
	UFUNCTION(BlueprintCallable, Category = "Weather") void AdvanceGameTime(float GameHours);                          // never below 0
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetTimeScale(float GameSecondsPerRealSecond);
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetPaused(bool bInPaused);
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetRunInEditor(bool bRun);
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetWeatherType(EWeatherType Type, bool bBlend = true);
	/** Replaces a type's look at run time (tuning, tests); wins over DA_WeatherType_<Type>. */
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetTypeLook(EWeatherType Type, const FWeatherLook& Look);
	UFUNCTION(BlueprintCallable, Category = "Weather") void SetOverride(const FWeatherOverride& InOverride);
	UFUNCTION(BlueprintCallable, Category = "Weather") void ClearOverride();   // back to override_defaults
	/** Settles the orchestrator and applies sky, MPC and fields now; scripts call it after any Set. */
	UFUNCTION(BlueprintCallable, Category = "Weather") void ApplyNow();
	UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Weather") FWeatherCalendarState GetCalendar() const;
	UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Weather") EWeatherType GetActiveWeatherType() const;
	UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Weather") bool IsActive() const;   // a domain was found
	UFUNCTION(BlueprintCallable, Category = "Weather") FString GetStateJson() const;
	UFUNCTION(BlueprintCallable, Category = "Weather") UTexture* GetField(FName Name);
	UFUNCTION(BlueprintCallable, Category = "Weather") int32 RegisterProbe(FVector WorldLocation);
	/** M0: the override's wind (spec §9.1). */
	UFUNCTION(BlueprintCallable, BlueprintPure, Category = "Weather") FVector GetProbeWind(int32 Probe) const;

	const FWeatherParams& GetParams() const { return Params; }
	const FWeatherRigValues& GetRig() const { return Rig; }
	const FWeatherLook& GetLook() const { return CurrentLook; }
	const FWeatherSun& GetSun() const { return SunState; }
	const FWeatherMoon& GetMoon() const { return MoonState; }
	UWeatherFieldRegistry* GetFieldRegistry() const { return FieldRegistry; }
	const FWeatherOverride& GetOverride() const { return Override; }
	double GetTimeScale() const { return TimeScale; }
	bool IsPaused() const { return bPaused; }
	bool GetRunInEditor() const { return bRunInEditor; }

protected:
	/** Game, PIE and editor worlds only: preview, thumbnail and inactive worlds would each read the params file. */
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:
	bool EnsureDomain();               // finds the first AWeatherDomain, at most once a second while none exists
	void LoadAssets();                 // MPC, DA_WeatherType_*, DA_SeasonLook_*, ST_* (only those that exist)
	void TickOrchestrator(float DeltaSeconds);
	void UpdateLook(float RealDeltaSeconds);
	void ApplyRig() const;
	void WriteMpc() const;
	void WriteFields();
	FWeatherLook TypeLook(EWeatherType Type) const;
	FWeatherLook SeasonLook(EWeatherSeason Season) const;

	FWeatherParams Params;
	bool bParamsLoaded = false;
	double GameSeconds = 0.0;
	double TimeScale = 24.0;
	bool bPaused = false;
	bool bRunInEditor = false;
	double DomainCheckCooldown = 0.0;
	FWeatherOverride Override;
	EWeatherType RequestedType = EWeatherType::Clear;
	bool bBlendNext = true;
	FWeatherCalendarState Calendar;
	FWeatherSun SunState;
	FWeatherMoon MoonState;
	EWeatherType BlendTargetType = EWeatherType::Clear;
	FWeatherLook BlendFromLook;
	FWeatherLook DisplayedTypeLook;
	double BlendElapsed = 0.0;
	double BlendDuration = 0.0;
	FWeatherLook CurrentLook;
	FWeatherRigValues Rig;
	bool bFieldsDirty = true;
	TArray<FVector> Probes;
	TMap<EWeatherType, FWeatherLook> RuntimeTypeLooks;
	bool bTreesRunning = false;
	bool bDomainSeen = false;          // the first domain loaded the assets and set the first look
	double FieldExtentMeters = 0.0;    // the extent FieldRegistry was last initialized with

	UPROPERTY(Transient) TWeakObjectPtr<AWeatherDomain> Domain;
	UPROPERTY(Transient) TObjectPtr<UWeatherFieldRegistry> FieldRegistry;
	UPROPERTY(Transient) TObjectPtr<UMaterialParameterCollection> Mpc;
	UPROPERTY(Transient) TMap<EWeatherType, TObjectPtr<UWeatherTypeAsset>> TypeAssets;
	UPROPERTY(Transient) TMap<EWeatherSeason, TObjectPtr<USeasonLookAsset>> SeasonAssets;
	UPROPERTY(Transient) TObjectPtr<UWeatherOrchestratorState> Orchestrator;
	UPROPERTY(Transient) TObjectPtr<UStateTree> TypeTree;
	UPROPERTY(Transient) TObjectPtr<UStateTree> SeasonTree;
	UPROPERTY(Transient) FStateTreeInstanceData TypeTreeData;
	UPROPERTY(Transient) FStateTreeInstanceData SeasonTreeData;
};
