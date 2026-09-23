#include "UnrealMcpBridgeModule.h"
#include "McpWebSocketServer.h"
#include "Modules/ModuleManager.h"

#define LOCTEXT_NAMESPACE "FUnrealMcpBridgeModule"

void FUnrealMcpBridgeModule::StartupModule()
{
	Server = MakeShared<FMcpWebSocketServer>();
	Server->Start();
}

void FUnrealMcpBridgeModule::ShutdownModule()
{
	if (Server.IsValid())
	{
		Server->Stop();
		Server.Reset();
	}
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FUnrealMcpBridgeModule, UnrealMcpBridge)
