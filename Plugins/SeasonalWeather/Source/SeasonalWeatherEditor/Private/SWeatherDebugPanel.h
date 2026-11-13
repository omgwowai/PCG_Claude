#pragma once

#include "CoreMinimal.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"
#include "WeatherTypes.h"

class STextComboBox;
class UWeatherSubsystem;

/** The weather debug panel (spec §1.8), tab "SeasonalWeatherPanel", opened by weather.Panel: time of day, time scale,
 *  season, weather type and the manual override of the world the editor shows. Every control calls a UWeatherSubsystem
 *  setter, then ApplyNow(); what the controls show is read back from the subsystem, so it follows console commands and
 *  scripts. Without a subsystem or a domain the controls are disabled and do nothing. */
class SWeatherDebugPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SWeatherDebugPanel) {}
	SLATE_END_ARGS()
	void Construct(const FArguments& InArgs);
	/** The PIE world's subsystem when playing, else the editor world's; nullptr when neither has one. */
	static UWeatherSubsystem* Weather();
	/** One line: date, season (+ transition %), active type, sun elevation; "no weather in this level" without a domain. */
	FText StatusText() const;
private:
	TArray<TSharedPtr<FString>> SeasonNames;
	TArray<TSharedPtr<FString>> TypeNames;
	FWeatherOverride Pending;

	/** Keeps the two combo boxes on the subsystem's season and active type: STextComboBox has no selection attribute. */
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;
	TSharedPtr<STextComboBox> SeasonCombo;
	TSharedPtr<STextComboBox> TypeCombo;
};
