#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "UnrealMcpBridgeSettings.generated.h"

UCLASS(config = Editor, defaultconfig, meta = (DisplayName = "Unreal MCP Bridge"))
class UUnrealMcpBridgeSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UUnrealMcpBridgeSettings();

	/** Localhost port the WebSocket server listens on. */
	UPROPERTY(config, EditAnywhere, Category = "Unreal MCP Bridge")
	int32 Port = 8777;

	/** Scripts root, relative to the project directory. Scripts must live under this. */
	UPROPERTY(config, EditAnywhere, Category = "Unreal MCP Bridge")
	FString ScriptsRootRelative = TEXT("Content/Python");

	/** Absolute, normalized scripts root resolved against the project dir. */
	FString GetScriptsRootAbsolute() const;
};
