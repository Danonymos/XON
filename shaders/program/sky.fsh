#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/atmosphere.glsl"
#include "/lib/clouds.glsl"
#include "/lib/end_sky.glsl"

uniform sampler2D gtexture;
#if defined XON_SKY_TEXTURED && XON_DIMENSION == 1
uniform ivec4 blendFunc;
#endif
in vec3 xonSkyRay;
in vec4 xonSkyVertexColor;
in vec2 xonSkyTexCoord;
layout(location = 0) out vec4 xonScene;

void main() {
#if XON_RENDER_MODE > 0
    if (any(greaterThanEqual(gl_FragCoord.xy, vec2(viewWidth, viewHeight) * XON_RENDER_SCALE))) discard;
#endif
    vec3 rayDir = xonSafeNormalize(xonSkyRay);
#ifdef XON_SKY_TEXTURED
#if XON_DIMENSION == 1
    // End flashes share this program with the sky cube, but use native additive blending.
    if (blendFunc.y == 1) {
#else
    {
#endif
    vec4 celestial = texture(gtexture, xonSkyTexCoord) * xonSkyVertexColor;
    if (celestial.a < alphaTestRef) discard;
    vec3 color = xonToLinear(celestial.rgb) * 1.45;
#if XON_DIMENSION == 0
    color *= 1.0 - rainStrength * 0.85;
    celestial.a *= 1.0 - xonCloudCover(rayDir);
#endif
    color *= 1.0 - max(blindness, darknessFactor);
    if (isEyeInWater != 0) color *= isEyeInWater == 1 ? 0.48 : 0.0;
    xonScene = vec4(color, celestial.a);
    return;
    }
#endif
    if (renderStage == MC_RENDER_STAGE_SUNSET) discard;
    if (renderStage == MC_RENDER_STAGE_STARS && max(xonSkyVertexColor.r, max(xonSkyVertexColor.g, xonSkyVertexColor.b)) < 0.01) discard;
#if XON_DIMENSION == 1
    vec3 color = xonEndSky(rayDir);
#else
    vec3 color = xonCloudSky(rayDir, renderStage != MC_RENDER_STAGE_STARS);
#endif
    if (renderStage == MC_RENDER_STAGE_STARS) {
        float visibility = (1.0 - rainStrength) * (1.0 - xonCloudCover(rayDir));
        color += xonToLinear(xonSkyVertexColor.rgb) * 1.55 * visibility;
    }
    if (isEyeInWater != 0) {
        vec3 viewRay = mat3(gbufferModelView) * rayDir;
        if (isEyeInWater == 1) {
            float upFacing = xonSaturate(rayDir.y);
            float snellWindow = smoothstep(0.05, 0.65, upFacing);
            color = mix(vec3(0.0), color * (0.35 + 0.65 * snellWindow), snellWindow);
            float fogDist = mix(192.0, 32.0, snellWindow);
            color = xonFog(color, viewRay * fogDist, 0.85);
        } else {
            color = xonFog(color, viewRay * max(far, 128.0), 1.0);
        }
    }
    color *= 1.0 - max(blindness, darknessFactor);
    xonScene = vec4(color, 1.0);
}
