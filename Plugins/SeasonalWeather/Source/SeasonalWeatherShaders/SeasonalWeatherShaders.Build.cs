using UnrealBuildTool;

public class SeasonalWeatherShaders : ModuleRules
{
	public SeasonalWeatherShaders(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "RenderCore", "RHI" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Projects" });
	}
}
