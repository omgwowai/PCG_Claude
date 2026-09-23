#include "McpScriptRunner.h"

#include "UnrealMcpBridgeSettings.h"
#include "IPythonScriptPlugin.h"
#include "PythonScriptTypes.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/Base64.h"
#include "HAL/PlatformProcess.h"
#include "HAL/FileManager.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

bool FMcpScriptRunner::ResolveScriptPath(const FString& ScriptPathRelative, FString& OutAbsolute, FString& OutError)
{
	const UUnrealMcpBridgeSettings* Settings = GetDefault<UUnrealMcpBridgeSettings>();
	FString Root = Settings->GetScriptsRootAbsolute();
	FPaths::NormalizeDirectoryName(Root);

	FString Combined = FPaths::Combine(Root, ScriptPathRelative);
	OutAbsolute = FPaths::ConvertRelativePathToFull(Combined);
	FPaths::NormalizeFilename(OutAbsolute);

	// Compare against the root with a trailing slash so that a sibling dir whose
	// name merely starts with the root (e.g. ".../PythonEvil") cannot pass.
	const FString RootWithSlash = Root.EndsWith(TEXT("/")) ? Root : Root + TEXT("/");
	if (!OutAbsolute.StartsWith(RootWithSlash))
	{
		OutError = FString::Printf(TEXT("script path escapes scripts root: %s"), *ScriptPathRelative);
		return false;
	}
	if (!OutAbsolute.EndsWith(TEXT(".py")))
	{
		OutError = TEXT("script path must end with .py");
		return false;
	}
	if (!FPaths::FileExists(OutAbsolute))
	{
		OutError = FString::Printf(TEXT("script not found: %s"), *OutAbsolute);
		return false;
	}
	return true;
}

FMcpScriptResult FMcpScriptRunner::RunScript(const FString& ScriptPathRelative, const FString& ArgsJson)
{
	// ---------------------------------------------------------------------------
	// CONTRACT (verified by the user via build + run). This function MUST:
	//   (a) build `mcp_args` as a Python dict parsed from the `ArgsJson` string;
	//   (b) run the user's script with `mcp_args` available, allowing it to set
	//       a module global `mcp_result`;
	//   (c) recover stdout, the JSON of `mcp_result`, and any traceback into the
	//       FMcpScriptResult fields (Stdout / ReturnJson / Error);
	//   (d) keep `check(IsInGameThread())` — the embedded Python interpreter is
	//       not thread-safe and must be driven from the game thread.
	//
	// RESULT RECOVERY (temp-file approach — IS NOW THE IMPLEMENTATION):
	//   We do NOT rely on EvaluateStatement returning values via
	//   FPythonCommandEx::CommandResult. That round-trip returns the Python
	//   *repr* of the value (e.g. a stdout string "hello\n" comes back as the
	//   literal 'hello\n' with surrounding quotes and an escaped newline, and
	//   mcp_result JSON comes back quote-wrapped), which corrupts Stdout and
	//   ReturnJson. Instead, the Python wrapper writes a single JSON object
	//   {"stdout": ..., "result": <parsed-json-or-null>, "error": ...} to a temp
	//   file (FPaths::CreateTempFilename) and we read + parse that file here to
	//   populate the FMcpScriptResult fields. This avoids the repr problem and
	//   any quoting issues entirely. The output contract is identical.
	// ---------------------------------------------------------------------------

	check(IsInGameThread());

	FMcpScriptResult Result;

	FString AbsolutePath;
	FString ResolveError;
	if (!ResolveScriptPath(ScriptPathRelative, AbsolutePath, ResolveError))
	{
		Result.bOk = false;
		Result.Error = ResolveError;
		return Result;
	}

	IPythonScriptPlugin* Python = IPythonScriptPlugin::Get();
	if (!Python || !Python->IsPythonAvailable())
	{
		Result.bOk = false;
		Result.Error = TEXT("Python is not available in this editor.");
		return Result;
	}

	FString UserSource;
	if (!FFileHelper::LoadFileToString(UserSource, *AbsolutePath))
	{
		Result.bOk = false;
		Result.Error = FString::Printf(TEXT("failed to read script: %s"), *AbsolutePath);
		return Result;
	}

	// Temp file the wrapper will write its JSON result to.
	const FString ResultPath = FPaths::CreateTempFilename(FPlatformProcess::UserTempDir(), TEXT("mcp_result_"), TEXT(".json"));

	// Build a wrapper that:
	//  - parses mcp_args from the JSON string,
	//  - captures stdout,
	//  - execs the user source (so `mcp_result` and `mcp_args` are module globals),
	//  - writes {"stdout", "result", "error"} as JSON to the result file.
	// We pass the user source, args JSON, result path AND compile() name as base64
	// to avoid ANY quoting/escaping problems (triple quotes, backslashes, newlines,
	// apostrophes in Windows paths, etc.).
	const FString ArgsB64 = FBase64::Encode(ArgsJson);
	const FString SrcB64 = FBase64::Encode(UserSource);
	const FString OutPathB64 = FBase64::Encode(ResultPath);
	const FString NameB64 = FBase64::Encode(AbsolutePath.Replace(TEXT("\\"), TEXT("/")));

	const FString Wrapper = FString::Printf(TEXT(
		"import json, io, sys, traceback, base64\n"
		"mcp_args = json.loads(base64.b64decode('%s').decode('utf-8'))\n"
		"mcp_result = None\n"
		"__mcp_src = base64.b64decode('%s').decode('utf-8')\n"
		"__mcp_out_path = base64.b64decode('%s').decode('utf-8')\n"
		"__mcp_name = base64.b64decode('%s').decode('utf-8')\n"
		"__mcp_buf = io.StringIO()\n"
		"__mcp_old = sys.stdout\n"
		"sys.stdout = __mcp_buf\n"
		"__mcp_err = ''\n"
		"try:\n"
		"    exec(compile(__mcp_src, __mcp_name, 'exec'), globals())\n"
		"except Exception:\n"
		"    __mcp_err = traceback.format_exc()\n"
		"finally:\n"
		"    sys.stdout = __mcp_old\n"
		"with open(__mcp_out_path, 'w', encoding='utf-8') as __f:\n"
		"    json.dump({\n"
		"        \"stdout\": __mcp_buf.getvalue(),\n"
		"        \"result\": mcp_result,\n"
		"        \"error\": __mcp_err,\n"
		"    }, __f)\n"
	), *ArgsB64, *SrcB64, *OutPathB64, *NameB64);

	FPythonCommandEx Command;
	Command.Command = Wrapper;
	// The wrapper is a multi-statement script, so it must run in ExecuteFile mode.
	// ExecuteStatement compiles in Python's "single" mode and rejects multiple
	// statements ("multiple statements found while compiling a single statement").
	Command.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
	Command.Flags = EPythonCommandFlags::Unattended;

	const bool bExecOk = Python->ExecPythonCommandEx(Command);

	// Recover the result by reading the JSON file the wrapper wrote. We do NOT
	// trust EvaluateStatement repr round-trips (see contract comment above).
	FString FileContents;
	const bool bReadOk = FFileHelper::LoadFileToString(FileContents, *ResultPath);

	if (!bReadOk)
	{
		// The wrapper failed before it could write the file (e.g. a syntax/IO
		// error in the harness itself). Surface whatever Python reported.
		Result.bOk = false;
		Result.Error = Command.CommandResult.IsEmpty()
			? TEXT("failed to produce result file")
			: Command.CommandResult;
	}
	else
	{
		TSharedPtr<FJsonObject> Obj;
		TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(FileContents);
		if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
		{
			Result.bOk = false;
			Result.Error = Command.CommandResult.IsEmpty()
				? TEXT("failed to parse result file")
				: Command.CommandResult;
		}
		else
		{
			Obj->TryGetStringField(TEXT("stdout"), Result.Stdout);

			// Re-serialize the "result" JSON value back to a compact JSON string
			// so B4 can embed it verbatim as the response's `return` field.
			// null/missing result => "null".
			FString OutJson = TEXT("null");
			TSharedPtr<FJsonValue> ResultVal = Obj->TryGetField(TEXT("result"));
			if (ResultVal.IsValid() && ResultVal->Type != EJson::Null)
			{
				// NOTE: FJsonSerializer::Serialize(TSharedRef<FJsonValue>, Identifier,
				// Writer) writes a bare value with an empty identifier. Confirm this
				// overload compiles on UE 5.7 at build time; the logic is what matters.
				TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
					TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&OutJson);
				FJsonSerializer::Serialize(ResultVal.ToSharedRef(), TEXT(""), Writer);
				Writer->Close();
			}
			Result.ReturnJson = OutJson;

			FString ErrText;
			Obj->TryGetStringField(TEXT("error"), ErrText);
			if (!ErrText.IsEmpty())
			{
				Result.bOk = false;
				Result.Error = ErrText;
			}
			else
			{
				Result.bOk = true;
			}
		}
	}

	// Best-effort cleanup of the temp result file.
	IFileManager::Get().Delete(*ResultPath, /*RequireExists*/ false, /*EvenReadOnly*/ true, /*Quiet*/ true);

	return Result;
}
