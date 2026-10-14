using UnrealBuildTool;

public class PyPCGTools : ModuleRules
{
	public PyPCGTools(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"PCG",
			"Json",
			"JsonUtilities",
		});
	}
}
