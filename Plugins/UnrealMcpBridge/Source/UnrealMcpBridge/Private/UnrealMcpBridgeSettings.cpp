#include "UnrealMcpBridgeSettings.h"

#include "Misc/Paths.h"

UUnrealMcpBridgeSettings::UUnrealMcpBridgeSettings()
{
	CategoryName = TEXT("Plugins");
}

FString UUnrealMcpBridgeSettings::GetScriptsRootAbsolute() const
{
	const FString Root = FPaths::Combine(FPaths::ProjectDir(), ScriptsRootRelative);
	FString Absolute = FPaths::ConvertRelativePathToFull(Root);
	FPaths::NormalizeDirectoryName(Absolute);
	return Absolute;
}
