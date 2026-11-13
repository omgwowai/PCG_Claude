# hlsl_check.py -- compile the cloud material's generated HLSL (cs_cloud_code.generate) offline with the engine's DXC,
# wrapped the way UE wraps a Custom node (inputs as parameters, additional outputs inout, Texture*SampleLevel as in
# Common.ush 364). Catches HLSL errors before a material build in the editor, which needs the startup map (trap 136).
#   C:\Python314\python.exe -P -E Tools/cs_weather/hlsl_check.py      -> exit 0 when DXC compiles it
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
import cs_cloud_code as CC  # noqa: E402

DXC = r"E:\UnrealEngine\Engine\Binaries\ThirdParty\ShaderConductor\Win64\dxc.exe"
VEC3 = {"P", "Cam", "L"}


def wrapped():
    params, args, k = [], [], 0
    for pin in CC.pins():
        if pin == "WeatherTex":
            params += ["Texture2D WeatherTex", "SamplerState WeatherTexSampler"]
            args += ["gW", "gSm"]
        elif pin in ("ShapeTex", "DetailTex"):
            params += ["Texture3D %s" % pin, "SamplerState %sSampler" % pin]
            args += ["gS" if pin == "ShapeTex" else "gD", "gSm"]
        elif pin in VEC3:
            params.append("float3 %s" % pin)
            args.append({"P": "gP + pos.xyz", "Cam": "gCam", "L": "gL"}[pin])
        elif pin in ("Alt", "SD"):
            params.append("float %s" % pin)
            args.append("pos.z * 1000.0" if pin == "Alt" else "pos.w")
        else:
            params.append("float %s" % pin)
            args.append("gScal[%d][%d]" % (k // 4 % 64, k % 4))
            k += 1
    params += ["inout float Cons", "inout float AO", "inout float Alb"]
    return "\n".join([
        "float4 Texture3DSampleLevel(Texture3D Tex, SamplerState S, float3 UV, float Mip) "
        "{ return Tex.SampleLevel(S, UV, Mip); }",
        "float4 Texture2DSampleLevel(Texture2D Tex, SamplerState S, float2 UV, float Mip) "
        "{ return Tex.SampleLevel(S, UV, Mip); }",
        "Texture2D gW; Texture3D gS; Texture3D gD; SamplerState gSm;",
        "cbuffer C { float4 gScal[64]; float3 gP; float3 gCam; float3 gL; };",
        "float CustomExpression0(%s)" % ", ".join(params), "{", CC.generate(), "}",
        "float4 main(float4 pos : SV_Position) : SV_Target", "{", "float c = 0.0, a = 0.0, b = 0.0;",
        "float r = CustomExpression0(%s, c, a, b);" % ", ".join(args), "return float4(r, c, a, b);", "}"]) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(DXC):
        print("dxc not found at %s" % DXC)
        return 2
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "cloud_v2.hlsl")
        with open(src, "w", encoding="utf-8") as f:
            f.write(wrapped())
        r = subprocess.run([DXC, "-T", "ps_6_0", "-E", "main", "-O3", src, "-Fo", os.path.join(d, "cloud_v2.dxil")],
                           capture_output=True, text=True)
    print((r.stdout + r.stderr)[-3000:])
    print("dxc exit", r.returncode, "pins", len(CC.pins()))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
