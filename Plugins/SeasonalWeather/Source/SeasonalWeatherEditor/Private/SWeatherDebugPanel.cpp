#include "SWeatherDebugPanel.h"

#include "Editor.h"
#include "Editor/EditorEngine.h"
#include "Engine/World.h"
#include "Misc/DateTime.h"
#include "WeatherSubsystem.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Input/SSpinBox.h"
#include "Widgets/Input/STextComboBox.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

#define LOCTEXT_NAMESPACE "SeasonalWeather"

namespace WeatherDebugPanel::Private
{
	/** The subsystem the controls act on: Weather() while it has a domain, else nullptr, and the controls do nothing. */
	UWeatherSubsystem* ActiveWeather()
	{
		UWeatherSubsystem* Weather = SWeatherDebugPanel::Weather();
		return Weather && Weather->IsActive() ? Weather : nullptr;
	}

	/** A row of the panel: the label column, then the control. */
	TSharedRef<SWidget> Row(const FText& Label, const TSharedRef<SWidget>& Control)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(0.f, 0.f, 8.f, 0.f)
			[
				SNew(SBox)
				.WidthOverride(160.f)
				[
					SNew(STextBlock).Text(Label)
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.VAlign(VAlign_Center)
			[
				Control
			];
	}

	/** Selects the item called Name, unless it is shown already or the list is open (selecting closes the list). The
	 *  selection handlers ignore a name the subsystem already holds, so this never sets anything. */
	void ShowName(const TSharedPtr<STextComboBox>& Combo, const TArray<TSharedPtr<FString>>& Names, const FString& Name)
	{
		if (!Combo || Combo->IsOpen())
		{
			return;
		}
		const TSharedPtr<FString> Shown = Combo->GetSelectedItem();
		if (Shown && *Shown == Name)
		{
			return;
		}
		for (const TSharedPtr<FString>& Each : Names)
		{
			if (*Each == Name)
			{
				Combo->SetSelectedItem(Each);
				return;
			}
		}
	}

	/** The month and day of day DayOfYear (1 = 1 January, as WeatherAstronomy::DateJulianDay reads it) of a Gregorian
	 *  Year. FDateTime itself only covers years 1 to 9999, and the clock may run past them. */
	void MonthAndDay(const int32 Year, const double DayOfYear, int32& OutMonth, int32& OutDay)
	{
		OutMonth = 1;
		OutDay = FMath::Max(1, FMath::FloorToInt32(DayOfYear));
		while (OutMonth < 12 && OutDay > FDateTime::DaysInMonth(Year, OutMonth))
		{
			OutDay -= FDateTime::DaysInMonth(Year, OutMonth);
			++OutMonth;
		}
	}
}

void SWeatherDebugPanel::Construct(const FArguments& InArgs)
{
	using namespace WeatherDebugPanel::Private;
	for (const EWeatherSeason Season : TEnumRange<EWeatherSeason>())
	{
		SeasonNames.Add(MakeShared<FString>(WeatherNames::Season(Season)));
	}
	for (const EWeatherType Type : TEnumRange<EWeatherType>())
	{
		TypeNames.Add(MakeShared<FString>(WeatherNames::Type(Type)));
	}
	if (const UWeatherSubsystem* Subsystem = Weather())
	{
		Pending = Subsystem->GetOverride();   // the draft starts from the override the world shows
	}

	const FMargin RowPadding(0.f, 2.f);
	TSharedRef<SVerticalBox> Controls = SNew(SVerticalBox)
		.IsEnabled_Lambda([] { return ActiveWeather() != nullptr; });

	Controls->AddSlot()
	.AutoHeight()
	.Padding(RowPadding)
	[
		Row(LOCTEXT("Hour", "Hour"),
			SNew(SSlider)
			.MinValue(0.f)
			.MaxValue(24.f)
			.Value_Lambda([] { const UWeatherSubsystem* Subsystem = Weather(); return Subsystem ? float(Subsystem->GetCalendar().Hour) : 0.f; })
			.OnValueChanged_Lambda([](const float Hour)
			{
				if (UWeatherSubsystem* Subsystem = ActiveWeather())
				{
					Subsystem->SetTimeOfDay(Hour);
					Subsystem->ApplyNow();
				}
			}))
	];

	Controls->AddSlot()
	.AutoHeight()
	.Padding(RowPadding)
	[
		Row(LOCTEXT("RunInEditor", "Run in editor"),
			SNew(SBox)
			.HAlign(HAlign_Left)
			[
				SNew(SCheckBox)
				.IsChecked_Lambda([]
				{
					const UWeatherSubsystem* Subsystem = Weather();
					return Subsystem && Subsystem->GetRunInEditor() ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
				})
				.OnCheckStateChanged_Lambda([](const ECheckBoxState State)
				{
					if (UWeatherSubsystem* Subsystem = ActiveWeather())
					{
						Subsystem->SetRunInEditor(State == ECheckBoxState::Checked);
						Subsystem->ApplyNow();
					}
				})
			])
	];

	// The slider range too: with MinValue / MaxValue alone, SSpinBox drags between the limits of float.
	Controls->AddSlot()
	.AutoHeight()
	.Padding(RowPadding)
	[
		Row(LOCTEXT("TimeScale", "Time scale (game s / real s)"),
			SNew(SSpinBox<float>)
			.MinValue(0.f)
			.MaxValue(3600.f)
			.MinSliderValue(0.f)
			.MaxSliderValue(3600.f)
			.Value_Lambda([] { const UWeatherSubsystem* Subsystem = Weather(); return Subsystem ? float(Subsystem->GetTimeScale()) : 0.f; })
			.OnValueChanged_Lambda([](const float Scale)
			{
				if (UWeatherSubsystem* Subsystem = ActiveWeather())
				{
					Subsystem->SetTimeScale(Scale);
					Subsystem->ApplyNow();
				}
			}))
	];

	// Tick shows the subsystem's season and type; a name the subsystem holds already is ignored, because SetSeason would
	// also move the clock to the first day of the season.
	Controls->AddSlot()
	.AutoHeight()
	.Padding(RowPadding)
	[
		Row(LOCTEXT("Season", "Season"),
			SAssignNew(SeasonCombo, STextComboBox)
			.OptionsSource(&SeasonNames)
			.OnSelectionChanged_Lambda([](const TSharedPtr<FString> Name, ESelectInfo::Type)
			{
				EWeatherSeason Season = EWeatherSeason::Spring;
				UWeatherSubsystem* Subsystem = ActiveWeather();
				if (Subsystem && Name && WeatherNames::ParseSeason(*Name, Season) && Season != Subsystem->GetCalendar().Season)
				{
					Subsystem->SetSeason(Season);
					Subsystem->ApplyNow();
				}
			}))
	];

	Controls->AddSlot()
	.AutoHeight()
	.Padding(RowPadding)
	[
		Row(LOCTEXT("WeatherType", "Weather type"),
			SAssignNew(TypeCombo, STextComboBox)
			.OptionsSource(&TypeNames)
			.OnSelectionChanged_Lambda([](const TSharedPtr<FString> Name, ESelectInfo::Type)
			{
				EWeatherType Type = EWeatherType::Clear;
				UWeatherSubsystem* Subsystem = ActiveWeather();
				if (Subsystem && Name && WeatherNames::ParseType(*Name, Type) && Type != Subsystem->GetActiveWeatherType())
				{
					Subsystem->SetWeatherType(Type);
					Subsystem->ApplyNow();
				}
			}))
	];

	// The override is edited in Pending and sent with "Apply override".
	struct FOverrideRow
	{
		FText Label;
		float FWeatherOverride::* Member;
	};
	const FOverrideRow OverrideRows[] = {
		{ LOCTEXT("Precip", "Precipitation (mm/h)"), &FWeatherOverride::PrecipMmPerHour },
		{ LOCTEXT("Snow", "Snow fraction"), &FWeatherOverride::SnowFraction },
		{ LOCTEXT("Temperature", "Temperature (\u00B0C)"), &FWeatherOverride::TemperatureC },
		{ LOCTEXT("Humidity", "Humidity"), &FWeatherOverride::Humidity },
		{ LOCTEXT("WindDirection", "Wind from (\u00B0 from north)"), &FWeatherOverride::WindDirectionDeg },
		{ LOCTEXT("WindSpeed", "Wind speed (m/s)"), &FWeatherOverride::WindSpeedMps },
		{ LOCTEXT("Thunder", "Thunder potential"), &FWeatherOverride::ThunderPotential },
		{ LOCTEXT("Cloud", "Cloud cover"), &FWeatherOverride::CloudCover },
	};
	for (const FOverrideRow& Field : OverrideRows)
	{
		float FWeatherOverride::* const Member = Field.Member;
		Controls->AddSlot()
		.AutoHeight()
		.Padding(RowPadding)
		[
			Row(Field.Label,
				SNew(SSpinBox<float>)
				.Value_Lambda([this, Member] { return Pending.*Member; })
				.OnValueChanged_Lambda([this, Member](const float Value) { Pending.*Member = Value; }))
		];
	}

	Controls->AddSlot()
	.AutoHeight()
	.Padding(0.f, 8.f, 0.f, 0.f)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(0.f, 0.f, 8.f, 0.f)
		[
			SNew(SButton)
			.Text(LOCTEXT("ApplyOverride", "Apply override"))
			.OnClicked_Lambda([this]
			{
				if (UWeatherSubsystem* Subsystem = ActiveWeather())
				{
					Subsystem->SetOverride(Pending);
					Subsystem->ApplyNow();
				}
				return FReply::Handled();
			})
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			SNew(SButton)
			.Text(LOCTEXT("ResetOverride", "Reset override"))
			.OnClicked_Lambda([this]
			{
				if (UWeatherSubsystem* Subsystem = ActiveWeather())
				{
					Subsystem->ClearOverride();
					Subsystem->ApplyNow();
					Pending = Subsystem->GetOverride();   // the draft shows the defaults now in effect
				}
				return FReply::Handled();
			})
		]
	];

	ChildSlot
	[
		SNew(SScrollBox)
		+ SScrollBox::Slot()
		.Padding(8.f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 0.f, 0.f, 8.f)
			[
				SNew(STextBlock)
				.Text(this, &SWeatherDebugPanel::StatusText)
				.AutoWrapText(true)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				Controls
			]
		]
	];
}

UWeatherSubsystem* SWeatherDebugPanel::Weather()
{
	if (!GEditor)
	{
		return nullptr;
	}
	const UWorld* World = GEditor->PlayWorld ? GEditor->PlayWorld.Get() : GEditor->GetEditorWorldContext().World();
	return World ? World->GetSubsystem<UWeatherSubsystem>() : nullptr;
}

FText SWeatherDebugPanel::StatusText() const
{
	using namespace WeatherDebugPanel::Private;
	const UWeatherSubsystem* Subsystem = Weather();
	if (!Subsystem)
	{
		return LOCTEXT("NoSubsystem", "No weather subsystem in this world");
	}
	if (!Subsystem->IsActive())
	{
		return LOCTEXT("NoDomain", "No weather in this level (no AWeatherDomain, or the weather params failed to load)");
	}
	const FWeatherCalendarState Calendar = Subsystem->GetCalendar();
	int32 Month = 1;
	int32 Day = 1;
	MonthAndDay(Calendar.Year, Calendar.DayOfYear, Month, Day);
	const int32 Minutes = FMath::Clamp(FMath::FloorToInt32(Calendar.Hour * 60.0), 0, 24 * 60 - 1);
	const FText Date = FText::FromString(FString::Printf(TEXT("%04d-%02d-%02d %02d:%02d"), Calendar.Year, Month, Day, Minutes / 60, Minutes % 60));

	const FText Season = FText::FromString(WeatherNames::Season(Calendar.Season));
	const FText SeasonShown = Calendar.bInTransition
		? FText::Format(LOCTEXT("SeasonTransition", "{0} to {1} {2}%"), Season, FText::FromString(WeatherNames::Season(Calendar.NextSeason)),
			FText::AsNumber(FMath::FloorToInt32(Calendar.TransitionProgress * 100.0)))
		: Season;
	FNumberFormattingOptions OneDecimal;
	OneDecimal.SetMinimumFractionalDigits(1).SetMaximumFractionalDigits(1);
	return FText::Format(LOCTEXT("Status", "{0} | {1} | {2} | sun {3}\u00B0"), Date, SeasonShown,
		FText::FromString(WeatherNames::Type(Subsystem->GetActiveWeatherType())), FText::AsNumber(Subsystem->GetSun().ElevationDeg, &OneDecimal));
}

void SWeatherDebugPanel::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	using namespace WeatherDebugPanel::Private;
	SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
	if (const UWeatherSubsystem* Subsystem = Weather())
	{
		ShowName(SeasonCombo, SeasonNames, WeatherNames::Season(Subsystem->GetCalendar().Season));
		ShowName(TypeCombo, TypeNames, WeatherNames::Type(Subsystem->GetActiveWeatherType()));
	}
}

#undef LOCTEXT_NAMESPACE
