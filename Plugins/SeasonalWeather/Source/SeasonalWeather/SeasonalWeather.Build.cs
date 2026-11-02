using UnrealBuildTool;

public class SeasonalWeather : ModuleRules
{
	public SeasonalWeather(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "StateTreeModule" });
		PrivateDependencyModuleNames.AddRange(new string[] { "RenderCore", "RHI", "Json", "SeasonalWeatherShaders" });
	}
}
