// PyPCGToolsLibrary.h -- Python access to the PCG graph fields its reflection layer cannot reach.
// Every write returns an empty string on success, otherwise an error message; nothing asserts.
// Writes refuse assets under /CitySamplePCG/, /PCGPrimitives* and /Engine/ (/Engine/Transient is
// allowed); objects that live in a world (level actors and their components) are allowed even when
// their package sits under a protected mount.
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PyPCGToolsLibrary.generated.h"

class UPCGGraph;
class UPCGGraphInstance;
class UPCGNode;
class UPCGSettings;

UCLASS()
class PYPCGTOOLS_API UPyPCGToolsLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** The whole graph as IR JSON (schema 1). See docs/superpowers/plans/2026-10-13-pypcg-18-stage-town.md, Task 1. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString ExportGraphIR(UPCGGraph* Graph);

	/** {"<param>": <value>} for the parameters this instance marks overridden. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString ExportInstanceOverrides(UPCGGraphInstance* Instance);

	/** Writes the listed properties (protected ones included) from a JSON object. "$text:<t>" values import as UE text. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetPropertiesJson(UObject* Object, const FString& Json);

	/** Sets one parameter of a graph instance from {"v": <value>} and marks it overridden. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetInstanceParameter(UPCGGraphInstance* Instance, FName Name, const FString& ValueJson);

	/** Inline default of input pin PinIndex (0-based): activation, and when bHasValue the metadata type and {"v": <value>}. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetPinDefaultValue(UPCGSettings* Settings, int32 PinIndex, const FString& TypeName, const FString& ValueJson, bool bHasValue, bool bActivated);

	/** Replaces the graph's user parameters with {"params": [...]} (IR form, plus "tooltip"), then rebuilds the category hierarchy. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetGraphUserParameters(UPCGGraph* Graph, const FString& Json);

	/** Binds a Get Graph Parameter node to the graph parameter ParamName (case-insensitive lookup; the caller's spelling is kept) and refreshes its pins. */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString BindUserParameterGetter(UPCGSettings* Getter, const FString& ParamName);

	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetNodeComment(UPCGNode* Node, const FString& Comment, bool bBubbleVisible, bool bBubblePinned);

	/** Replaces the graph's comment boxes with {"boxes": [...]} (IR form; fresh GUIDs). */
	UFUNCTION(BlueprintCallable, Category = "PyPCG")
	static FString SetGraphCommentBoxes(UPCGGraph* Graph, const FString& Json);
};
