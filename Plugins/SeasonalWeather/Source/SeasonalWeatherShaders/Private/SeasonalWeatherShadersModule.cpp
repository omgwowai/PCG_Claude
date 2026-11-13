#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "ShaderCore.h"

class FSeasonalWeatherShadersModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		const FString ShaderDir = FPaths::Combine(IPluginManager::Get().FindPlugin(TEXT("SeasonalWeather"))->GetBaseDir(), TEXT("Shaders"));
		AddShaderSourceDirectoryMapping(TEXT("/Plugin/SeasonalWeather"), ShaderDir);
	}
};

IMPLEMENT_MODULE(FSeasonalWeatherShadersModule, SeasonalWeatherShaders)
