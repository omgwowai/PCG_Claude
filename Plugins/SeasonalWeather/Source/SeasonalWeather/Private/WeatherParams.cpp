#include "WeatherParams.h"

#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace WeatherParams::Private
{
	// weather_ref/params.py FORMATS in EWeatherFieldFormat order, and that tuple as Python prints it in field_problems.
	const TCHAR* const FormatNames[] = { TEXT("rgba16f"), TEXT("r16f"), TEXT("r32f") };
	const TCHAR* const FormatTuple = TEXT("('rgba16f', 'r16f', 'r32f')");
	static_assert(UE_ARRAY_COUNT(FormatNames) == static_cast<SIZE_T>(EWeatherFieldFormat::R32F) + 1, "one name per format");

	bool IsNumber(const TSharedPtr<FJsonValue>& Value)
	{
		return Value.IsValid() && Value->Type == EJson::Number;
	}

	bool IsString(const TSharedPtr<FJsonValue>& Value)
	{
		return Value.IsValid() && Value->Type == EJson::String;
	}

	// weather_ref's integer: a JSON number equal to its rounded value (UE reads every JSON number as a double, so 7 and 7.0
	// are one value here), within int32 range.
	bool AsInt32(const TSharedPtr<FJsonValue>& Value, int32& Out)
	{
		if (!IsNumber(Value))
		{
			return false;
		}
		const double Number = Value->AsNumber();
		if (Number != FMath::RoundToDouble(Number) || Number < TNumericLimits<int32>::Lowest() || Number > TNumericLimits<int32>::Max())
		{
			return false;
		}
		Out = static_cast<int32>(Number);
		return true;
	}

	// Case-sensitive, like Python's `fmt in FORMATS`. Out is left unchanged when Value names no format.
	bool AsFormat(const TSharedPtr<FJsonValue>& Value, EWeatherFieldFormat& Out)
	{
		if (!IsString(Value))
		{
			return false;
		}
		const FString Name = Value->AsString();
		int32 Index = 0;
		for (const TCHAR* const Format : FormatNames)
		{
			if (Name.Equals(Format, ESearchCase::CaseSensitive))
			{
				Out = static_cast<EWeatherFieldFormat>(Index);
				return true;
			}
			++Index;
		}
		return false;
	}

	// Reads the values of one section in order. Each value read adds "<section>.<key>" to Consumed when the caller tracks
	// keys; a missing or mistyped value writes the error and returns false.
	class FSectionReader
	{
	public:
		FSectionReader(const FJsonObject& InSection, const TCHAR* InName, TSet<FString>* InConsumed, FString& InError)
			: Section(InSection), Name(InName), Consumed(InConsumed), Error(InError)
		{
		}

		bool Number(const TCHAR* Key, double& Out)
		{
			const TSharedPtr<FJsonValue> Value = Section.TryGetField(Key);
			if (!IsNumber(Value))
			{
				return Missing(TEXT("number"), Key);
			}
			Out = Value->AsNumber();
			return Record(Key);
		}

		bool Number(const TCHAR* Key, float& Out)
		{
			double Value = 0.0;
			if (!Number(Key, Value))
			{
				return false;
			}
			Out = static_cast<float>(Value);
			return true;
		}

		bool Integer(const TCHAR* Key, int32& Out)
		{
			if (!AsInt32(Section.TryGetField(Key), Out))
			{
				return Missing(TEXT("integer"), Key);
			}
			return Record(Key);
		}

		// One of the WeatherNames season names (case-sensitive); anything else, missing included, is a bad season.
		bool Season(const TCHAR* Key, EWeatherSeason& Out)
		{
			FString Value;
			Section.TryGetStringField(Key, Value);
			if (!WeatherNames::ParseSeason(Value, Out))
			{
				Error = FString::Printf(TEXT("bad season '%s' in %s.%s"), *Value, Name, Key);
				return false;
			}
			return Record(Key);
		}

		// A number per season, kept in EWeatherSeason order; the map is one key.
		bool SeasonDoyMap(const TCHAR* Key, double (&Out)[4])
		{
			const TSharedPtr<FJsonObject>* Map = nullptr;
			const bool bIsObject = Section.TryGetObjectField(Key, Map);
			for (const EWeatherSeason Each : TEnumRange<EWeatherSeason>())
			{
				const FString SeasonName = WeatherNames::Season(Each);
				const TSharedPtr<FJsonValue> Value = bIsObject ? (*Map)->TryGetField(SeasonName) : TSharedPtr<FJsonValue>();
				if (!IsNumber(Value))
				{
					return Missing(TEXT("number"), *FString::Printf(TEXT("%s.%s"), Key, *SeasonName));
				}
				Out[static_cast<int32>(Each)] = Value->AsNumber();
			}
			return Record(Key);
		}

	private:
		bool Missing(const TCHAR* What, const TCHAR* Key)
		{
			Error = FString::Printf(TEXT("missing %s %s.%s"), What, Name, Key);
			return false;
		}

		bool Record(const TCHAR* Key)
		{
			if (Consumed)
			{
				Consumed->Add(FString::Printf(TEXT("%s.%s"), Name, Key));
			}
			return true;
		}

		const FJsonObject& Section;
		const TCHAR* Name;
		TSet<FString>* Consumed;
		FString& Error;
	};

	// The section readers take their keys in params_schema.json order. Consumed may be null.
	bool ReadCalendar(const FJsonObject& Section, FWeatherCalendarParams& Out, TSet<FString>* Consumed, FString& OutError)
	{
		FSectionReader Read(Section, TEXT("calendar"), Consumed, OutError);
		return Read.Number(TEXT("real_seconds_per_game_day"), Out.RealSecondsPerGameDay)
			&& Read.Integer(TEXT("season_length_days"), Out.SeasonLengthDays)
			&& Read.Number(TEXT("transition_days"), Out.TransitionDays)
			&& Read.Season(TEXT("start_season"), Out.StartSeason)
			&& Read.Number(TEXT("start_hour"), Out.StartHour)
			&& Read.Integer(TEXT("base_year"), Out.BaseYear)
			&& Read.SeasonDoyMap(TEXT("season_start_doy"), Out.SeasonStartDoy);
	}

	bool ReadAstronomy(const FJsonObject& Section, FWeatherAstronomyParams& Out, TSet<FString>* Consumed, FString& OutError)
	{
		FSectionReader Read(Section, TEXT("astronomy"), Consumed, OutError);
		return Read.Number(TEXT("latitude_deg"), Out.LatitudeDeg)
			&& Read.Number(TEXT("longitude_deg"), Out.LongitudeDeg)
			&& Read.Number(TEXT("timezone_hours"), Out.TimezoneHours)
			&& Read.Number(TEXT("north_yaw_deg"), Out.NorthYawDeg)
			&& Read.Number(TEXT("synodic_month_game_days"), Out.SynodicMonthGameDays)
			&& Read.Number(TEXT("moon_phase_offset_days"), Out.MoonPhaseOffsetDays)
			&& Read.Number(TEXT("sunrise_zenith_deg"), Out.SunriseZenithDeg);
	}

	bool ReadSky(const FJsonObject& Section, FWeatherSkyParams& Out, TSet<FString>* Consumed, FString& OutError)
	{
		FSectionReader Read(Section, TEXT("sky"), Consumed, OutError);
		return Read.Number(TEXT("sun_lux"), Out.SunLux)
			&& Read.Number(TEXT("moon_lux"), Out.MoonLux)
			&& Read.Number(TEXT("sky_light_intensity"), Out.SkyLightIntensity)
			&& Read.Number(TEXT("fog_density"), Out.FogDensity)
			&& Read.Number(TEXT("fog_height_falloff"), Out.FogHeightFalloff)
			&& Read.Number(TEXT("white_temp_k"), Out.WhiteTempK)
			&& Read.Number(TEXT("cloud_dimming"), Out.CloudDimming)
			&& Read.Number(TEXT("star_fade_start_deg"), Out.StarFadeStartDeg)
			&& Read.Number(TEXT("star_fade_range_deg"), Out.StarFadeRangeDeg)
			&& Read.Number(TEXT("look_blend_seconds"), Out.LookBlendSeconds);
	}

	bool ReadOverride(const FJsonObject& Section, FWeatherOverride& Out, TSet<FString>* Consumed, FString& OutError)
	{
		FSectionReader Read(Section, TEXT("override_defaults"), Consumed, OutError);
		return Read.Number(TEXT("precip_mm_h"), Out.PrecipMmPerHour)
			&& Read.Number(TEXT("snow_fraction"), Out.SnowFraction)
			&& Read.Number(TEXT("temperature_c"), Out.TemperatureC)
			&& Read.Number(TEXT("humidity"), Out.Humidity)
			&& Read.Number(TEXT("wind_dir_deg"), Out.WindDirectionDeg)
			&& Read.Number(TEXT("wind_speed_m_s"), Out.WindSpeedMps)
			&& Read.Number(TEXT("thunder_potential"), Out.ThunderPotential)
			&& Read.Number(TEXT("cloud_cover"), Out.CloudCover);
	}

	// weather_ref.params.field_problems in the same order, stopping at the first problem, so the message is the first one
	// Python lists. Its gating comes with stopping: the size check runs only once dims is valid and the channel check only
	// once the format is.
	bool ReadField(const FString& Name, const FJsonObject& Desc, FWeatherFieldDesc& Out, FString& OutError)
	{
		const auto Fail = [&Name, &OutError](const FString& Problem)
		{
			OutError = FString::Printf(TEXT("field %s: %s"), *Name, *Problem);
			return false;
		};
		Out.Name = FName(*Name);

		if (!AsInt32(Desc.TryGetField(TEXT("dims")), Out.Dims) || (Out.Dims != 2 && Out.Dims != 3))
		{
			return Fail(TEXT("dims must be 2 or 3"));
		}
		if (!AsFormat(Desc.TryGetField(TEXT("format")), Out.Format))
		{
			return Fail(FString::Printf(TEXT("format must be one of %s"), FormatTuple));
		}
		const bool bHasSize = Desc.HasField(TEXT("size"));
		if (bHasSize == Desc.HasField(TEXT("cell_m")))
		{
			return Fail(TEXT("give exactly one of size and cell_m"));
		}
		if (bHasSize)
		{
			const TArray<TSharedPtr<FJsonValue>>* Size = nullptr;
			int32 Texels[3] = { 1, 1, 1 };   // a 2D field keeps Z = 1
			bool bSizeOk = Desc.TryGetArrayField(TEXT("size"), Size) && Size->Num() == Out.Dims;
			for (int32 Axis = 0; bSizeOk && Axis < Out.Dims; ++Axis)
			{
				bSizeOk = AsInt32((*Size)[Axis], Texels[Axis]) && Texels[Axis] > 0;
			}
			if (!bSizeOk)
			{
				return Fail(FString::Printf(TEXT("size must be %d positive integers"), Out.Dims));
			}
			Out.Size = FIntVector(Texels[0], Texels[1], Texels[2]);
		}
		else
		{
			const TSharedPtr<FJsonValue> Cell = Desc.TryGetField(TEXT("cell_m"));
			if (Out.Dims != 2 || !IsNumber(Cell) || !(Cell->AsNumber() > 0.0))
			{
				return Fail(TEXT("cell_m needs dims 2 and a positive number"));
			}
			Out.CellMeters = Cell->AsNumber();
		}
		const int32 Want = Out.Format == EWeatherFieldFormat::RGBA16F ? 4 : 1;
		const TArray<TSharedPtr<FJsonValue>>* Channels = nullptr;
		bool bChannelsOk = Desc.TryGetArrayField(TEXT("channels"), Channels) && Channels->Num() == Want;
		for (int32 Index = 0; bChannelsOk && Index < Want; ++Index)
		{
			bChannelsOk = IsString((*Channels)[Index]);
			if (bChannelsOk)
			{
				Out.Channels.Add((*Channels)[Index]->AsString());
			}
		}
		if (!bChannelsOk)
		{
			return Fail(FString::Printf(TEXT("%d channel names expected"), Want));
		}
		return true;
	}

	// Every descriptor in file order; the section is one key.
	bool ReadFields(const FJsonObject& Section, TArray<FWeatherFieldDesc>& Out, TSet<FString>* Consumed, FString& OutError)
	{
		const FJsonObject NotAnObject{};   // stands in for a descriptor that is not an object: it has no dims
		for (const TPair<FJsonObject::FStringType, TSharedPtr<FJsonValue>>& Entry : Section.Values)
		{
			const bool bIsObject = Entry.Value.IsValid() && Entry.Value->Type == EJson::Object;
			FWeatherFieldDesc Field;
			if (!ReadField(FString(*Entry.Key), bIsObject ? *Entry.Value->AsObject() : NotAnObject, Field, OutError))
			{
				return false;
			}
			Out.Add(MoveTemp(Field));
		}
		if (Consumed)
		{
			Consumed->Add(TEXT("fields"));
		}
		return true;
	}

	bool FindSection(const FJsonObject& Root, const TCHAR* Name, const FJsonObject*& OutSection, FString& OutError)
	{
		const TSharedPtr<FJsonObject>* Section = nullptr;
		if (!Root.TryGetObjectField(Name, Section))
		{
			OutError = FString::Printf(TEXT("missing section %s"), Name);
			return false;
		}
		OutSection = Section->Get();
		return true;
	}
}

FIntVector FWeatherFieldDesc::ResolveSize(double ExtentMeters) const
{
	if (CellMeters <= 0.0)
	{
		return Size;
	}
	int32 N = FMath::CeilToInt32(ExtentMeters / CellMeters);
	N = FMath::Max(8, ((N + 7) / 8) * 8);
	return FIntVector(N, N, 1);
}

FString FWeatherParams::DefaultPath()
{
	return FPaths::ProjectDir() / TEXT("Tools/weather/weather_params.json");
}

bool FWeatherParams::LoadFromString(const FString& JsonText, FWeatherParams& Out, FString& OutError)
{
	using namespace WeatherParams::Private;
	Out = FWeatherParams();

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		const FString& Detail = Reader->GetErrorMessage();
		OutError = Detail.IsEmpty() ? FString(TEXT("not a JSON object")) : FString::Printf(TEXT("bad JSON: %s"), *Detail);
		return false;
	}

	// Schema order; the first problem stops the load.
	TSet<FString>* const Consumed = &Out.ConsumedKeys;
	const FJsonObject* Section = nullptr;
	return FindSection(*Root, TEXT("calendar"), Section, OutError) && ReadCalendar(*Section, Out.Calendar, Consumed, OutError)
		&& FindSection(*Root, TEXT("astronomy"), Section, OutError) && ReadAstronomy(*Section, Out.Astronomy, Consumed, OutError)
		&& FindSection(*Root, TEXT("sky"), Section, OutError) && ReadSky(*Section, Out.Sky, Consumed, OutError)
		&& FindSection(*Root, TEXT("fields"), Section, OutError) && ReadFields(*Section, Out.Fields, Consumed, OutError)
		&& FindSection(*Root, TEXT("override_defaults"), Section, OutError)
		&& ReadOverride(*Section, Out.OverrideDefaults, Consumed, OutError);
}

bool FWeatherParams::LoadFromFile(const FString& Path, FWeatherParams& Out, FString& OutError)
{
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *Path))
	{
		Out = FWeatherParams();
		OutError = FString::Printf(TEXT("cannot read %s"), *FPaths::ConvertRelativePathToFull(Path));
		return false;
	}
	return LoadFromString(Text, Out, OutError);
}

bool FWeatherParams::ParseCalendar(const FJsonObject& Section, FWeatherCalendarParams& Out, FString& OutError)
{
	return WeatherParams::Private::ReadCalendar(Section, Out, nullptr, OutError);
}

bool FWeatherParams::ParseSky(const FJsonObject& Section, FWeatherSkyParams& Out, FString& OutError)
{
	return WeatherParams::Private::ReadSky(Section, Out, nullptr, OutError);
}

const FWeatherFieldDesc* FWeatherParams::FindField(FName Name) const
{
	return Fields.FindByPredicate([Name](const FWeatherFieldDesc& Field) { return Field.Name == Name; });
}
