using UnrealBuildTool;

public class UnrealMcpBridge : ModuleRules
{
	public UnrealMcpBridge(ReadOnlyTargetRules Target) : base(Target)
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
			"Projects",
			"DeveloperSettings",
			"Json",
			"WebSocketNetworking",
			"PythonScriptPlugin",
		});
	}
}
