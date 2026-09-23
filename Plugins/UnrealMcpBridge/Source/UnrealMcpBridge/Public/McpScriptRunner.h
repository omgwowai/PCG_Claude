#pragma once

#include "CoreMinimal.h"

/** Result of running a script via the embedded Python interpreter. */
struct FMcpScriptResult
{
	bool bOk = false;
	FString Stdout;
	FString Error;
	/** JSON text of the script's `mcp_result` global, or empty. */
	FString ReturnJson;
};

/**
 * Resolves a request's script path against the configured scripts root,
 * rejecting any path that escapes it, then executes the script in UE's
 * embedded Python with `mcp_args` injected. MUST be called on the game thread.
 */
class FMcpScriptRunner
{
public:
	/** Resolve ScriptPathRelative under the scripts root.
	 *  Returns false (with OutError set) if it escapes the root or is not .py. */
	static bool ResolveScriptPath(const FString& ScriptPathRelative, FString& OutAbsolute, FString& OutError);

	/** Run the script. ArgsJson is the JSON object string for `mcp_args`. */
	static FMcpScriptResult RunScript(const FString& ScriptPathRelative, const FString& ArgsJson);
};
