#include "WeatherSubsystem.h"

#include "Components/ExponentialHeightFogComponent.h"
#include "Components/LightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "StateTree.h"
#include "WeatherDataAssets.h"
#include "WeatherDomain.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(WeatherSubsystem)

namespace WeatherSubsystem::Private
{
	constexpr double DayS = 86400.0;

	// Game time stays finite and in [0, MaxGameSeconds] (Ruling 20): WeatherCalendar casts the day count to int64 and the
	// day, season day and year to int32. A NaN gives 0.
	constexpr double MaxGameSeconds = DayS * 1.0e8;

	double ClampGameSeconds(const double Seconds)
	{
		return Seconds > 0.0 ? FMath::Min(Seconds, MaxGameSeconds) : 0.0;
	}

	// The ranges WeatherCalendar and WeatherAstronomy::Moon divide by (Ruling 20); empty when the params are usable. The
	// comparisons are written so that a NaN fails them.
	FString RangeProblem(const FWeatherParams& Params)
	{
		const FWeatherCalendarParams& Calendar = Params.Calendar;
		if (!(Calendar.RealSecondsPerGameDay > 0.0))
		{
			return FString::Printf(TEXT("calendar.real_seconds_per_game_day must be > 0, got %g"), Calendar.RealSecondsPerGameDay);
		}
		if (Calendar.SeasonLengthDays < 1)
		{
			return FString::Printf(TEXT("calendar.season_length_days must be >= 1, got %d"), Calendar.SeasonLengthDays);
		}
		if (!(Calendar.TransitionDays >= 0.0 && Calendar.TransitionDays <= Calendar.SeasonLengthDays))
		{
			return FString::Printf(TEXT("calendar.transition_days must be in 0..season_length_days (%d), got %g"), Calendar.SeasonLengthDays, Calendar.TransitionDays);
		}
		if (!(Params.Astronomy.SynodicMonthGameDays > 0.0))
		{
			return FString::Printf(TEXT("astronomy.synodic_month_game_days must be > 0, got %g"), Params.Astronomy.SynodicMonthGameDays);
		}
		return FString();
	}

	// The asset of a package that exists, else nullptr without a word: the plugin assets come from `weather.py assets`
	// and may not be generated yet (plan Review Focus 2).
	template <typename T>
	T* LoadIfExists(const FString& PackageName)
	{
		if (!FPackageName::DoesPackageExist(PackageName))
		{
			return nullptr;
		}
		return LoadObject<T>(nullptr, *FString::Printf(TEXT("%s.%s"), *PackageName, *FPackageName::GetShortName(PackageName)));
	}

	// A tree that is not ready to run counts as missing: every execution context made for it logs a warning.
	bool IsReady(const UStateTree* Tree)
	{
		return Tree && Tree->IsReadyToRun();
	}

	TArray<TSharedPtr<FJsonValue>> Numbers(std::initializer_list<double> Values)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const double Value : Values)
		{
			Out.Add(MakeShared<FJsonValueNumber>(Value));
		}
		return Out;
	}

	TArray<TSharedPtr<FJsonValue>> RotationJson(const FRotator& Rotation)
	{
		return Numbers({ Rotation.Pitch, Rotation.Yaw, Rotation.Roll });
	}
}

void UWeatherSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	using namespace WeatherSubsystem::Private;
	Super::Initialize(Collection);
	FieldRegistry = NewObject<UWeatherFieldRegistry>(this);
	Orchestrator = NewObject<UWeatherOrchestratorState>(this);

	const FString Path = FWeatherParams::DefaultPath();
	FString Error;
	if (FWeatherParams::LoadFromFile(Path, Params, Error))
	{
		Error = RangeProblem(Params);
	}
	if (!Error.IsEmpty())
	{
		// The one line an inert world writes; the setters refuse to touch the clock from now on.
		Params = FWeatherParams();
		UE_LOG(LogSeasonalWeather, Error, TEXT("Weather stays off in %s: %s (%s)"), *GetNameSafe(GetWorld()), *Error, *FPaths::ConvertRelativePathToFull(Path));
		return;
	}
	bParamsLoaded = true;
	TimeScale = DayS / Params.Calendar.RealSecondsPerGameDay;
	GameSeconds = ClampGameSeconds(Params.Calendar.StartHour * 3600.0);
	Override = Params.OverrideDefaults;
	Calendar = WeatherCalendar::Evaluate(GameSeconds, Params.Calendar);
}

void UWeatherSubsystem::Deinitialize()
{
	using namespace WeatherSubsystem::Private;
	if (bTreesRunning && IsReady(TypeTree) && IsReady(SeasonTree))
	{
		WeatherOrchestrator::Stop(*this, *TypeTree, TypeTreeData, *Orchestrator);
		WeatherOrchestrator::Stop(*this, *SeasonTree, SeasonTreeData, *Orchestrator);
	}
	bTreesRunning = false;
	Super::Deinitialize();
}

void UWeatherSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	UpdateNow(DeltaTime);
}

TStatId UWeatherSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UWeatherSubsystem, STATGROUP_Tickables);
}

bool UWeatherSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE || WorldType == EWorldType::Editor;
}

void UWeatherSubsystem::UpdateNow(float RealDeltaSeconds)
{
	using namespace WeatherSubsystem::Private;
	const double Dt = FMath::IsFinite(RealDeltaSeconds) ? FMath::Max(0.0, double(RealDeltaSeconds)) : 0.0;
	DomainCheckCooldown = FMath::Max(0.0, DomainCheckCooldown - Dt);
	if (!bParamsLoaded || !EnsureDomain())
	{
		return;
	}
	const UWorld* World = GetWorld();
	const bool bEditorWorld = World && World->WorldType == EWorldType::Editor;
	if (!bPaused && (!bEditorWorld || bRunInEditor))
	{
		GameSeconds = ClampGameSeconds(GameSeconds + Dt * TimeScale);
	}
	Calendar = WeatherCalendar::Evaluate(GameSeconds, Params.Calendar);
	TickOrchestrator(float(Dt));
	const FWeatherAstronomyParams& Astronomy = Params.Astronomy;
	SunState = WeatherAstronomy::Sun(Calendar.Year, Calendar.DayOfYear, Calendar.Hour, Astronomy.LatitudeDeg, Astronomy.LongitudeDeg, Astronomy.TimezoneHours);
	MoonState = WeatherAstronomy::Moon(GameSeconds / DayS, SunState, Astronomy.LatitudeDeg, Astronomy.SynodicMonthGameDays, Astronomy.MoonPhaseOffsetDays);
	UpdateLook(float(Dt));
	Rig = WeatherSky::Compute(SunState, MoonState, CurrentLook, Params.Sky, Astronomy.NorthYawDeg);
	ApplyRig();
	WriteMpc();
	if (bFieldsDirty)
	{
		WriteFields();
	}
}

void UWeatherSubsystem::SetSeason(EWeatherSeason Season, int32 DayInSeason)
{
	using namespace WeatherSubsystem::Private;
	if (!bParamsLoaded || Season >= EWeatherSeason::Count)
	{
		return;
	}
	GameSeconds = ClampGameSeconds(WeatherCalendar::SecondsFor(Params.Calendar, GameSeconds, Season, DayInSeason, Calendar.Hour));
	Calendar = WeatherCalendar::Evaluate(GameSeconds, Params.Calendar);
}

void UWeatherSubsystem::SetTimeOfDay(float Hour)
{
	using namespace WeatherSubsystem::Private;
	if (!bParamsLoaded || !FMath::IsFinite(Hour))
	{
		return;
	}
	GameSeconds = ClampGameSeconds(WeatherCalendar::WithHour(GameSeconds, Hour));
	Calendar = WeatherCalendar::Evaluate(GameSeconds, Params.Calendar);
}

void UWeatherSubsystem::AdvanceGameTime(float GameHours)
{
	using namespace WeatherSubsystem::Private;
	if (!bParamsLoaded || !FMath::IsFinite(GameHours))
	{
		return;
	}
	GameSeconds = ClampGameSeconds(GameSeconds + double(GameHours) * 3600.0);
	Calendar = WeatherCalendar::Evaluate(GameSeconds, Params.Calendar);
}

void UWeatherSubsystem::SetTimeScale(float GameSecondsPerRealSecond)
{
	if (FMath::IsFinite(GameSecondsPerRealSecond) && GameSecondsPerRealSecond >= 0.f)
	{
		TimeScale = GameSecondsPerRealSecond;
	}
}

void UWeatherSubsystem::SetPaused(bool bInPaused)
{
	bPaused = bInPaused;
}

void UWeatherSubsystem::SetRunInEditor(bool bRun)
{
	bRunInEditor = bRun;
}

void UWeatherSubsystem::SetWeatherType(EWeatherType Type, bool bBlend)
{
	if (Type >= EWeatherType::Count)
	{
		return;   // no state of the type tree would match it
	}
	RequestedType = Type;
	bBlendNext = bBlend;
}

void UWeatherSubsystem::SetTypeLook(EWeatherType Type, const FWeatherLook& Look)
{
	RuntimeTypeLooks.Add(Type, Look);
}

void UWeatherSubsystem::SetOverride(const FWeatherOverride& InOverride)
{
	Override = InOverride;
	bFieldsDirty = true;
}

void UWeatherSubsystem::ClearOverride()
{
	Override = Params.OverrideDefaults;
	bFieldsDirty = true;
}

void UWeatherSubsystem::ApplyNow()
{
	if (!bParamsLoaded)
	{
		return;
	}
	DomainCheckCooldown = 0.0;   // scripts call ApplyNow right after spawning a domain; the cooldown only throttles Tick
	if (!EnsureDomain())
	{
		return;
	}
	TickOrchestrator(0.f);
	TickOrchestrator(0.f);
	UpdateNow(0.f);
}

FWeatherCalendarState UWeatherSubsystem::GetCalendar() const
{
	return Calendar;
}

EWeatherType UWeatherSubsystem::GetActiveWeatherType() const
{
	return Orchestrator ? Orchestrator->ActiveType : EWeatherType::Clear;
}

bool UWeatherSubsystem::IsActive() const
{
	return bParamsLoaded && Domain.IsValid();
}

FString UWeatherSubsystem::GetStateJson() const
{
	using namespace WeatherSubsystem::Private;
	const UWeatherOrchestratorState& State = Orchestrator ? *Orchestrator : *GetDefault<UWeatherOrchestratorState>();

	const TSharedRef<FJsonObject> CalendarJson = MakeShared<FJsonObject>();
	CalendarJson->SetNumberField(TEXT("game_seconds"), Calendar.GameSeconds);
	CalendarJson->SetNumberField(TEXT("day_index"), Calendar.DayIndex);
	CalendarJson->SetNumberField(TEXT("hour"), Calendar.Hour);
	CalendarJson->SetStringField(TEXT("season"), WeatherNames::Season(Calendar.Season));
	CalendarJson->SetStringField(TEXT("next_season"), WeatherNames::Season(Calendar.NextSeason));
	CalendarJson->SetNumberField(TEXT("day_in_season"), Calendar.DayInSeason);
	CalendarJson->SetNumberField(TEXT("season_fraction"), Calendar.SeasonFraction);
	CalendarJson->SetBoolField(TEXT("in_transition"), Calendar.bInTransition);
	CalendarJson->SetNumberField(TEXT("transition_progress"), Calendar.TransitionProgress);
	const FVector4& Weights = Calendar.SeasonWeights;
	CalendarJson->SetArrayField(TEXT("season_weights"), Numbers({ Weights.X, Weights.Y, Weights.Z, Weights.W }));
	CalendarJson->SetNumberField(TEXT("year"), Calendar.Year);
	CalendarJson->SetNumberField(TEXT("day_of_year"), Calendar.DayOfYear);

	const TSharedRef<FJsonObject> SunJson = MakeShared<FJsonObject>();
	SunJson->SetNumberField(TEXT("elevation_deg"), SunState.ElevationDeg);
	SunJson->SetNumberField(TEXT("azimuth_deg"), SunState.AzimuthDeg);
	SunJson->SetNumberField(TEXT("declination_deg"), SunState.DeclinationDeg);

	const TSharedRef<FJsonObject> MoonJson = MakeShared<FJsonObject>();
	MoonJson->SetNumberField(TEXT("phase"), MoonState.Phase);
	MoonJson->SetNumberField(TEXT("illumination"), MoonState.Illumination);
	MoonJson->SetNumberField(TEXT("elevation_deg"), MoonState.ElevationDeg);
	MoonJson->SetNumberField(TEXT("azimuth_deg"), MoonState.AzimuthDeg);

	// weather_ref.sky.LOOK_FIELDS.
	const TSharedRef<FJsonObject> LookJson = MakeShared<FJsonObject>();
	LookJson->SetNumberField(TEXT("sun_intensity"), CurrentLook.SunIntensity);
	LookJson->SetNumberField(TEXT("moon_intensity"), CurrentLook.MoonIntensity);
	LookJson->SetNumberField(TEXT("sky_light"), CurrentLook.SkyLight);
	LookJson->SetNumberField(TEXT("fog_density"), CurrentLook.FogDensity);
	LookJson->SetNumberField(TEXT("fog_height_falloff"), CurrentLook.FogHeightFalloff);
	LookJson->SetNumberField(TEXT("white_temp_offset"), CurrentLook.WhiteTempOffset);
	LookJson->SetNumberField(TEXT("saturation"), CurrentLook.Saturation);
	LookJson->SetNumberField(TEXT("contrast"), CurrentLook.Contrast);
	LookJson->SetNumberField(TEXT("exposure_bias"), CurrentLook.ExposureBias);
	LookJson->SetNumberField(TEXT("cloud_cover"), CurrentLook.CloudCover);

	const TSharedRef<FJsonObject> RigJson = MakeShared<FJsonObject>();
	RigJson->SetNumberField(TEXT("sun_lux"), Rig.SunLux);
	RigJson->SetNumberField(TEXT("moon_lux"), Rig.MoonLux);
	RigJson->SetNumberField(TEXT("sky_light_intensity"), Rig.SkyLightIntensity);
	RigJson->SetNumberField(TEXT("fog_density"), Rig.FogDensity);
	RigJson->SetNumberField(TEXT("fog_height_falloff"), Rig.FogHeightFalloff);
	RigJson->SetNumberField(TEXT("white_temp"), Rig.WhiteTemp);
	RigJson->SetNumberField(TEXT("saturation"), Rig.Saturation);
	RigJson->SetNumberField(TEXT("contrast"), Rig.Contrast);
	RigJson->SetNumberField(TEXT("exposure_bias"), Rig.ExposureBias);
	RigJson->SetNumberField(TEXT("star_intensity"), Rig.StarIntensity);
	RigJson->SetNumberField(TEXT("cloud_cover"), Rig.CloudCover);
	RigJson->SetArrayField(TEXT("sun_rotation"), RotationJson(Rig.SunRotation));
	RigJson->SetArrayField(TEXT("moon_rotation"), RotationJson(Rig.MoonRotation));

	const TSharedRef<FJsonObject> OrchestratorJson = MakeShared<FJsonObject>();
	OrchestratorJson->SetStringField(TEXT("requested_type"), WeatherNames::Type(RequestedType));
	OrchestratorJson->SetStringField(TEXT("active_type"), WeatherNames::Type(State.ActiveType));
	OrchestratorJson->SetStringField(TEXT("active_season"), WeatherNames::Season(State.ActiveSeason));
	OrchestratorJson->SetBoolField(TEXT("active_transition"), State.bActiveTransition);
	OrchestratorJson->SetBoolField(TEXT("trees_running"), bTreesRunning);

	// weather_params.json "override_defaults" names.
	const TSharedRef<FJsonObject> OverrideJson = MakeShared<FJsonObject>();
	OverrideJson->SetNumberField(TEXT("precip_mm_h"), Override.PrecipMmPerHour);
	OverrideJson->SetNumberField(TEXT("snow_fraction"), Override.SnowFraction);
	OverrideJson->SetNumberField(TEXT("temperature_c"), Override.TemperatureC);
	OverrideJson->SetNumberField(TEXT("humidity"), Override.Humidity);
	OverrideJson->SetNumberField(TEXT("wind_dir_deg"), Override.WindDirectionDeg);
	OverrideJson->SetNumberField(TEXT("wind_speed_m_s"), Override.WindSpeedMps);
	OverrideJson->SetNumberField(TEXT("thunder_potential"), Override.ThunderPotential);
	OverrideJson->SetNumberField(TEXT("cloud_cover"), Override.CloudCover);

	// The render targets created so far, with their sizes.
	const TSharedRef<FJsonObject> FieldsJson = MakeShared<FJsonObject>();
	if (FieldRegistry)
	{
		for (const FName& Name : FieldRegistry->GetFieldNames())
		{
			const FIntVector Size = FieldRegistry->GetFieldSize(Name);
			FieldsJson->SetArrayField(Name.ToString(), Numbers({ double(Size.X), double(Size.Y), double(Size.Z) }));
		}
	}

	const TSharedRef<FJsonObject> AssetsJson = MakeShared<FJsonObject>();
	AssetsJson->SetBoolField(TEXT("mpc"), Mpc != nullptr);
	AssetsJson->SetNumberField(TEXT("type_looks"), TypeAssets.Num());
	AssetsJson->SetNumberField(TEXT("season_looks"), SeasonAssets.Num());
	AssetsJson->SetBoolField(TEXT("trees"), TypeTree != nullptr && SeasonTree != nullptr);

	const TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetObjectField(TEXT("calendar"), CalendarJson);
	Root->SetObjectField(TEXT("sun"), SunJson);
	Root->SetObjectField(TEXT("moon"), MoonJson);
	Root->SetObjectField(TEXT("look"), LookJson);
	Root->SetObjectField(TEXT("rig"), RigJson);
	Root->SetObjectField(TEXT("orchestrator"), OrchestratorJson);
	Root->SetObjectField(TEXT("override"), OverrideJson);
	Root->SetObjectField(TEXT("fields"), FieldsJson);
	if (const AWeatherDomain* D = Domain.Get())
	{
		const TSharedRef<FJsonObject> DomainJson = MakeShared<FJsonObject>();
		DomainJson->SetStringField(TEXT("name"), D->GetActorNameOrLabel());
		DomainJson->SetNumberField(TEXT("extent_m"), D->ExtentMeters);
		Root->SetObjectField(TEXT("domain"), DomainJson);
	}
	else
	{
		Root->SetField(TEXT("domain"), MakeShared<FJsonValueNull>());
	}
	Root->SetBoolField(TEXT("active"), IsActive());
	Root->SetNumberField(TEXT("time_scale"), TimeScale);
	Root->SetBoolField(TEXT("paused"), bPaused);
	Root->SetBoolField(TEXT("run_in_editor"), bRunInEditor);
	Root->SetObjectField(TEXT("assets"), AssetsJson);

	FString Out;
	FJsonSerializer::Serialize(Root, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out));
	return Out;
}

UTexture* UWeatherSubsystem::GetField(FName Name)
{
	return IsActive() ? FieldRegistry->GetOrCreateField(Name) : nullptr;
}

int32 UWeatherSubsystem::RegisterProbe(FVector WorldLocation)
{
	return Probes.Add(WorldLocation);
}

FVector UWeatherSubsystem::GetProbeWind(int32 Probe) const
{
	return IsActive() && Probes.IsValidIndex(Probe) ? FVector(Override.WindVector()) : FVector::ZeroVector;
}

bool UWeatherSubsystem::EnsureDomain()
{
	if (!Domain.IsValid())
	{
		if (DomainCheckCooldown > 0.0)
		{
			return false;
		}
		DomainCheckCooldown = 1.0;
		TActorIterator<AWeatherDomain> It(GetWorld());
		if (!It)
		{
			return false;
		}
		Domain = *It;
	}
	// The registry sizes the level-wide fields by the extent, and a new extent drops every render target (Ruling 11). A
	// non-finite extent counts as 0 (the smallest fields), so that a NaN does not re-initialize the registry every update.
	const double Extent = FMath::IsFinite(Domain->ExtentMeters) ? double(Domain->ExtentMeters) : 0.0;
	if (!bDomainSeen || Extent != FieldExtentMeters)
	{
		FieldExtentMeters = Extent;
		FieldRegistry->Initialize(Params.Fields, Extent);
		bFieldsDirty = true;
	}
	if (!bDomainSeen)
	{
		bDomainSeen = true;
		LoadAssets();
		BlendTargetType = RequestedType;
		DisplayedTypeLook = TypeLook(RequestedType);
	}
	return true;
}

void UWeatherSubsystem::LoadAssets()
{
	using namespace WeatherSubsystem::Private;
	Mpc = LoadIfExists<UMaterialParameterCollection>(TEXT("/SeasonalWeather/Materials/MPC_Weather"));
	for (const EWeatherType Type : TEnumRange<EWeatherType>())
	{
		if (UWeatherTypeAsset* Asset = LoadIfExists<UWeatherTypeAsset>(TEXT("/SeasonalWeather/Data/DA_WeatherType_") + WeatherNames::Type(Type)))
		{
			TypeAssets.Add(Type, Asset);
		}
	}
	for (const EWeatherSeason Season : TEnumRange<EWeatherSeason>())
	{
		if (USeasonLookAsset* Asset = LoadIfExists<USeasonLookAsset>(TEXT("/SeasonalWeather/Data/DA_SeasonLook_") + WeatherNames::Season(Season)))
		{
			SeasonAssets.Add(Season, Asset);
		}
	}
	TypeTree = LoadIfExists<UStateTree>(TEXT("/SeasonalWeather/Orchestrator/ST_WeatherType"));
	SeasonTree = LoadIfExists<UStateTree>(TEXT("/SeasonalWeather/Orchestrator/ST_Season"));
}

void UWeatherSubsystem::TickOrchestrator(float DeltaSeconds)
{
	using namespace WeatherSubsystem::Private;
	Orchestrator->RequestedType = RequestedType;
	Orchestrator->CalendarSeason = Calendar.Season;
	Orchestrator->bCalendarInTransition = Calendar.bInTransition;
	if (IsReady(TypeTree) && IsReady(SeasonTree))
	{
		if (!bTreesRunning)
		{
			bTreesRunning = WeatherOrchestrator::Start(*this, *TypeTree, TypeTreeData, *Orchestrator)
				&& WeatherOrchestrator::Start(*this, *SeasonTree, SeasonTreeData, *Orchestrator);
		}
		if (bTreesRunning)
		{
			const EStateTreeRunStatus TypeStatus = WeatherOrchestrator::Tick(*this, *TypeTree, TypeTreeData, *Orchestrator, DeltaSeconds);
			const EStateTreeRunStatus SeasonStatus = WeatherOrchestrator::Tick(*this, *SeasonTree, SeasonTreeData, *Orchestrator, DeltaSeconds);
			if (TypeStatus == EStateTreeRunStatus::Running && SeasonStatus == EStateTreeRunStatus::Running)
			{
				return;
			}
		}
		// A fault (a start that failed, or a tree that finished): StateTree never ticks a stopped tree again, so stop both,
		// fall back for this update and start them again on the next one.
		WeatherOrchestrator::Stop(*this, *TypeTree, TypeTreeData, *Orchestrator);
		WeatherOrchestrator::Stop(*this, *SeasonTree, SeasonTreeData, *Orchestrator);
		bTreesRunning = false;
	}
	else if (bTreesRunning)
	{
		// A tree went out of date while running (recompiled in the editor): drop its instance data, start over once it is
		// ready again.
		TypeTreeData.Reset();
		SeasonTreeData.Reset();
		bTreesRunning = false;
	}
	Orchestrator->ActiveType = RequestedType;   // the trees are not generated yet (Review Focus 2)
	Orchestrator->ActiveSeason = Calendar.Season;
	Orchestrator->bActiveTransition = Calendar.bInTransition;
}

void UWeatherSubsystem::UpdateLook(float RealDeltaSeconds)
{
	const EWeatherType Active = Orchestrator->ActiveType;
	if (Active != BlendTargetType)
	{
		BlendFromLook = DisplayedTypeLook;   // start from what is on screen (Review Focus 5)
		BlendTargetType = Active;
		BlendElapsed = 0.0;
		BlendDuration = bBlendNext ? Params.Sky.LookBlendSeconds : 0.0;
	}
	BlendElapsed += RealDeltaSeconds;
	const double Alpha = BlendDuration > 0.0 ? FMath::Clamp(BlendElapsed / BlendDuration, 0.0, 1.0) : 1.0;
	DisplayedTypeLook = FWeatherLook::Lerp(BlendFromLook, TypeLook(Active), Alpha);
	const FWeatherLook Season = FWeatherLook::Lerp(SeasonLook(Calendar.Season), SeasonLook(Calendar.NextSeason), Calendar.TransitionProgress);
	CurrentLook = FWeatherLook::Combine(DisplayedTypeLook, Season);
}

void UWeatherSubsystem::ApplyRig() const
{
	AWeatherDomain* D = Domain.Get();
	if (!D)
	{
		return;
	}
	auto Place = [](ADirectionalLight* Light, const FRotator& Rotation, double Lux)
	{
		if (!Light)
		{
			return;
		}
		USceneComponent* Root = Light->GetRootComponent();
		if (Root && Root->Mobility != EComponentMobility::Movable)
		{
			Root->SetMobility(EComponentMobility::Movable);   // a stationary light refuses SetActorRotation
		}
		Light->SetActorRotation(Rotation);
		Light->GetLightComponent()->SetIntensity(float(Lux));
	};
	Place(D->Sun, Rig.SunRotation, Rig.SunLux);
	Place(D->Moon, Rig.MoonRotation, Rig.MoonLux);
	if (D->SkyLight)
	{
		D->SkyLight->GetLightComponent()->SetIntensity(float(Rig.SkyLightIntensity));
	}
	if (D->HeightFog)
	{
		UExponentialHeightFogComponent* Fog = D->HeightFog->GetComponent();
		Fog->SetFogDensity(float(Rig.FogDensity));
		Fog->SetFogHeightFalloff(float(Rig.FogHeightFalloff));
	}
	if (D->PostProcess)
	{
		FPostProcessSettings& S = D->PostProcess->Settings;
		S.bOverride_WhiteTemp = true;
		S.WhiteTemp = float(Rig.WhiteTemp);
		S.bOverride_ColorSaturation = true;
		S.ColorSaturation = FVector4(Rig.Saturation, Rig.Saturation, Rig.Saturation, 1.0);
		S.bOverride_ColorContrast = true;
		S.ColorContrast = FVector4(Rig.Contrast, Rig.Contrast, Rig.Contrast, 1.0);
		S.bOverride_AutoExposureBias = true;
		S.AutoExposureBias = float(Rig.ExposureBias);
	}
}

void UWeatherSubsystem::WriteMpc() const
{
	UWorld* World = GetWorld();
	UMaterialParameterCollectionInstance* Instance = Mpc && World ? World->GetParameterCollectionInstance(Mpc) : nullptr;
	if (!Instance)
	{
		return;
	}
	// Directions point towards the body; a parameter the collection lacks is skipped silently by the instance.
	const double North = Params.Astronomy.NorthYawDeg;
	const FVector SunDirection = WeatherAstronomy::Direction(SunState.ElevationDeg, SunState.AzimuthDeg, North);
	const FVector MoonDirection = WeatherAstronomy::Direction(MoonState.ElevationDeg, MoonState.AzimuthDeg, North);
	const FVector3f Wind = Override.WindVector();
	Instance->SetVectorParameterValue(TEXT("SeasonWeights"), Calendar.SeasonWeights);
	Instance->SetVectorParameterValue(TEXT("SunDirection"), FVector4(SunDirection, 0.0));
	Instance->SetVectorParameterValue(TEXT("MoonDirection"), FVector4(MoonDirection, 0.0));
	Instance->SetVectorParameterValue(TEXT("CameraWind"), FLinearColor(Wind.X, Wind.Y, Wind.Z, Override.WindSpeedMps));
	Instance->SetVectorParameterValue(TEXT("CameraWeather"), FLinearColor(Override.PrecipMmPerHour, Override.SnowFraction, Override.TemperatureC, Override.Humidity));
	Instance->SetScalarParameterValue(TEXT("TimeOfDay"), float(Calendar.Hour));
	Instance->SetScalarParameterValue(TEXT("MoonIllumination"), float(MoonState.Illumination));
	Instance->SetScalarParameterValue(TEXT("StarIntensity"), float(Rig.StarIntensity));
	Instance->SetScalarParameterValue(TEXT("CloudCover"), float(Rig.CloudCover));
}

void UWeatherSubsystem::WriteFields()
{
	// Plan ruling P3: in M0 the override is the only weather source and fills these fields uniformly. Written once per
	// change; a field that cannot be filled (no RHI, or a params file without it) is not retried every update.
	const FVector3f Wind = Override.WindVector();
	FieldRegistry->FillUniform(TEXT("ground_a"), FLinearColor(Override.PrecipMmPerHour, Override.SnowFraction, Override.TemperatureC, Override.Humidity));
	FieldRegistry->FillUniform(TEXT("ground_b"), FLinearColor(Wind.X, Wind.Y, Override.ThunderPotential, Override.CloudCover));
	FieldRegistry->FillUniform(TEXT("coarse_wind"), FLinearColor(Wind.X, Wind.Y, 0.f, 0.f));
	FieldRegistry->FillUniform(TEXT("atmos_volume"), FLinearColor(0.f, 0.f, 0.f, 0.f));
	bFieldsDirty = false;
}

FWeatherLook UWeatherSubsystem::TypeLook(EWeatherType Type) const
{
	if (const FWeatherLook* Runtime = RuntimeTypeLooks.Find(Type))
	{
		return *Runtime;
	}
	const TObjectPtr<UWeatherTypeAsset>* Asset = TypeAssets.Find(Type);
	return Asset && *Asset ? (*Asset)->Look : FWeatherLook();   // neutral until the assets exist (Review Focus 2)
}

FWeatherLook UWeatherSubsystem::SeasonLook(EWeatherSeason Season) const
{
	const TObjectPtr<USeasonLookAsset>* Asset = SeasonAssets.Find(Season);
	return Asset && *Asset ? (*Asset)->Look : FWeatherLook();
}
