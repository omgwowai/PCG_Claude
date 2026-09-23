#include "McpWebSocketServer.h"

#include "McpScriptRunner.h"
#include "UnrealMcpBridgeSettings.h"

#include "INetworkingWebSocket.h"
#include "IWebSocketNetworkingModule.h"
#include "IWebSocketServer.h"
#include "WebSocketNetworkingDelegates.h"
#include "Modules/ModuleManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Async/Async.h"
#include "Containers/Ticker.h"

// NOTE (UE-version-sensitivity): The WebSocketNetworking module's API names and
// signatures (IWebSocketServer::Init, INetworkingWebSocket, the callback typedefs
// FWebSocketClientConnectedCallBack / FWebSocketPacketReceivedCallBack,
// SetReceiveCallBack, the Send signature/flags, and CreateServer) can vary across
// UE versions. The code below targets the typical UE 5.x WebSocketNetworking API
// and was cross-checked against the UE 5.7 headers under
// Engine/Plugins/Experimental/WebSocketNetworking/Source/WebSocketNetworking/Public.
// Verified there: Init(uint32 Port, FWebSocketClientConnectedCallBack, FString
// BindAddress); FWebSocketClientConnectedCallBack(INetworkingWebSocket*);
// FWebSocketPacketReceivedCallBack(void* Data, int32 Size); Send(const uint8*,
// uint32, bool bPrependSize = true); and CreateServer() returns
// TUniquePtr<IWebSocketServer> (hence the TUniquePtr member in the header).
// If this fails to compile on UE 5.7, adapt the Init/callback/Send calls to the
// installed signatures but PRESERVE the run->game-thread->result flow and the JSON
// field names (type, id, script_path, args, ok, stdout, return, error) below.

// Defined here (not defaulted in the header) so the TUniquePtr<IWebSocketServer>
// member is destroyed where IWebSocketServer is a complete type.
FMcpWebSocketServer::FMcpWebSocketServer() = default;
FMcpWebSocketServer::~FMcpWebSocketServer() = default;

bool FMcpWebSocketServer::Start()
{
	const UUnrealMcpBridgeSettings* Settings = GetDefault<UUnrealMcpBridgeSettings>();

	IWebSocketNetworkingModule* Module = &FModuleManager::LoadModuleChecked<IWebSocketNetworkingModule>("WebSocketNetworking");
	Server = Module->CreateServer();

	FWebSocketClientConnectedCallBack Connected;
	Connected.BindRaw(this, &FMcpWebSocketServer::OnClientConnected);

	if (!Server.IsValid() || !Server->Init(static_cast<uint32>(Settings->Port), Connected, TEXT("127.0.0.1")))
	{
		UE_LOG(LogTemp, Error, TEXT("UnrealMcpBridge: failed to bind WebSocket server on port %d"), Settings->Port);
		Server.Reset();
		return false;
	}

	TickHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda(
		[this](float) { Tick(); return true; }));

	UE_LOG(LogTemp, Log, TEXT("UnrealMcpBridge: WebSocket server listening on 127.0.0.1:%d"), Settings->Port);
	return true;
}

void FMcpWebSocketServer::Stop()
{
	if (TickHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
		TickHandle.Reset();
	}
	ActiveClient = nullptr;
	Server.Reset();
}

void FMcpWebSocketServer::Tick()
{
	if (Server.IsValid())
	{
		Server->Tick();
	}
}

void FMcpWebSocketServer::OnClientConnected(INetworkingWebSocket* ClientSocket)
{
	ActiveClient = ClientSocket;

	// Clear ActiveClient when this socket closes so a deferred reply (below) is dropped
	// instead of writing to a freed socket. Both this and the receive/reply callbacks run
	// on the game thread (Server->Tick()), so the check/clear is serialized and race-free.
	// Confirm closed-callback typedef name (FWebSocketInfoCallBack) on 5.7.
	FWebSocketInfoCallBack Closed;
	Closed.BindLambda([this, ClientSocket]()
	{
		if (ActiveClient == ClientSocket)
		{
			ActiveClient = nullptr;
		}
	});
	ClientSocket->SetSocketClosedCallBack(Closed);

	FWebSocketPacketReceivedCallBack Received;
	Received.BindLambda([this, ClientSocket](void* Data, int32 Size)
	{
		// BUILD-VERIFY: The frames are UTF-8 JSON and the buffer is NOT null-terminated,
		// so we decode UTF-8 with an explicit length. Verified against UE 5.7
		// Containers/UnrealString.h.inl: FString::ConstructFromPtrSize has a
		// (const UTF8CHAR* Str, int32 Size) overload that decodes UTF-8 correctly, while
		// the length+ANSICHAR/TCHAR FString constructors are deprecated since 5.4. If
		// ConstructFromPtrSize differs on your build, any UTF-8-correct, length-aware
		// decode is acceptable, e.g. FString(StringCast<TCHAR>((const UTF8CHAR*)Data, Size)).
		const FString Message = FString::ConstructFromPtrSize(reinterpret_cast<const UTF8CHAR*>(Data), Size);
		HandleMessage(ClientSocket, Message);
	});
	ClientSocket->SetReceiveCallBack(Received);
}

void FMcpWebSocketServer::HandleMessage(INetworkingWebSocket* ClientSocket, const FString& Message)
{
	TSharedPtr<FJsonObject> Obj;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);
	if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
	{
		return; // ignore malformed frames
	}

	const FString Type = Obj->GetStringField(TEXT("type"));
	if (Type != TEXT("run"))
	{
		return;
	}

	FString Id;
	FString ScriptPath;
	if (!Obj->TryGetStringField(TEXT("id"), Id) || !Obj->TryGetStringField(TEXT("script_path"), ScriptPath))
	{
		return; // malformed run frame
	}

	// Re-serialize the args object to a JSON string for mcp_args.
	FString ArgsJson = TEXT("{}");
	const TSharedPtr<FJsonObject>* ArgsObj;
	if (Obj->TryGetObjectField(TEXT("args"), ArgsObj))
	{
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ArgsJson);
		FJsonSerializer::Serialize(ArgsObj->ToSharedRef(), Writer);
	}

	// Execute on the game thread; reply when done. The receive callback fires off the
	// game thread, but FMcpScriptRunner::RunScript checks IsInGameThread() (UE's
	// embedded Python is not thread-safe), so we hop onto the game thread here.
	AsyncTask(ENamedThreads::GameThread, [this, ClientSocket, Id, ScriptPath, ArgsJson]()
	{
		const FMcpScriptResult Result = FMcpScriptRunner::RunScript(ScriptPath, ArgsJson);

		const TSharedRef<FJsonObject> Reply = MakeShared<FJsonObject>();
		Reply->SetStringField(TEXT("type"), TEXT("result"));
		Reply->SetStringField(TEXT("id"), Id);
		Reply->SetBoolField(TEXT("ok"), Result.bOk);
		Reply->SetStringField(TEXT("stdout"), Result.Stdout);
		if (Result.bOk)
		{
			// Embed the script's return JSON as a raw value.
			TSharedPtr<FJsonValue> ReturnValue;
			const TSharedRef<TJsonReader<>> RReader = TJsonReaderFactory<>::Create(Result.ReturnJson);
			if (FJsonSerializer::Deserialize(RReader, ReturnValue) && ReturnValue.IsValid())
			{
				Reply->SetField(TEXT("return"), ReturnValue);
			}
		}
		else
		{
			Reply->SetStringField(TEXT("error"), Result.Error);
		}

		FString ReplyText;
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ReplyText);
		FJsonSerializer::Serialize(Reply, Writer);

		if (ActiveClient != ClientSocket)
		{
			return; // client disconnected before we could reply; drop the response
		}
		SendFrame(ClientSocket, ReplyText);
	});
}

void FMcpWebSocketServer::SendFrame(INetworkingWebSocket* ClientSocket, const FString& Json)
{
	if (!ClientSocket)
	{
		return;
	}
	FTCHARToUTF8 Utf8(*Json);
	// BUILD-VERIFY: The third Send param is "bPrependSize" in many UE versions. For a
	// text WebSocket frame we want the raw UTF-8 bytes sent as-is (no 4-byte length
	// prefix), so pass false. Confirm the param's meaning/name against the UE 5.7
	// INetworkingWebSocket::Send signature.
	ClientSocket->Send(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length(), /*PrependSize*/ false);
}
