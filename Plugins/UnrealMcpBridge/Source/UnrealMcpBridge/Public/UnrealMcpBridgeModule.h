#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class FMcpWebSocketServer;

class FUnrealMcpBridgeModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	TSharedPtr<FMcpWebSocketServer> Server;
};
