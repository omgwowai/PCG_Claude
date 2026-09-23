// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "PCG_ClaudeGameMode.generated.h"

/**
 *  Simple GameMode for a third person game
 */
UCLASS(abstract)
class APCG_ClaudeGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	
	/** Constructor */
	APCG_ClaudeGameMode();
};



