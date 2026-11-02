using UnrealBuildTool;

public class SeasonalWeatherEditor : ModuleRules
{
	public SeasonalWeatherEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "SeasonalWeather", "StateTreeModule" });
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"StateTreeEditorModule", "UnrealEd", "Slate", "SlateCore", "InputCore", "AssetRegistry", "WorkspaceMenuStructure", "Json"
		});
	}
}
