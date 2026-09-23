// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class PCG_Claude : ModuleRules
{
	public PCG_Claude(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"AIModule",
			"StateTreeModule",
			"GameplayStateTreeModule",
			"UMG",
			"Slate"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });

		PublicIncludePaths.AddRange(new string[] {
			"PCG_Claude",
			"PCG_Claude/Variant_Platforming",
			"PCG_Claude/Variant_Platforming/Animation",
			"PCG_Claude/Variant_Combat",
			"PCG_Claude/Variant_Combat/AI",
			"PCG_Claude/Variant_Combat/Animation",
			"PCG_Claude/Variant_Combat/Gameplay",
			"PCG_Claude/Variant_Combat/Interfaces",
			"PCG_Claude/Variant_Combat/UI",
			"PCG_Claude/Variant_SideScrolling",
			"PCG_Claude/Variant_SideScrolling/AI",
			"PCG_Claude/Variant_SideScrolling/Gameplay",
			"PCG_Claude/Variant_SideScrolling/Interfaces",
			"PCG_Claude/Variant_SideScrolling/UI"
		});

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
