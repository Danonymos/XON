#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/atmosphere.glsl"
#include "/lib/clouds.glsl"

uniform sampler2D gtexture;
in vec3 xonSkyRay;
in vec4 xonSkyVertexColor;
in vec2 xonSkyTexCoord;
layout(location = 0) out vec4 xonScene;

void main() {
#if XON_RENDER_MODE > 0
    if (any(greaterThanEqual(gl_FragCoord.xy, vec2(viewWidth, viewHeight) * XON_RENDER_SCALE))) discard;
#endif
    vec3 rayDir = xonSafeNormalize(xonSkyRay);
#if defined XON_SKY_TEXTURED && XON_DIMENSION != 1
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
#else
    if (renderStage == MC_RENDER_STAGE_SUNSET) discard;
    vec3 color = xonCloudSky(rayDir, true);
    if (renderStage == MC_RENDER_STAGE_STARS) {
        float visibility = (1.0 - rainStrength) * (1.0 - xonCloudCover(rayDir));
        color += xonToLinear(xonSkyVertexColor.rgb) * 1.55 * visibility;
    }
#if XON_DIMENSION == 1
    // Crisp cosmic star specks embedded in the dark purple End void.
    vec3 starGrid = floor(rayDir * 220.0);
    float starHash = fract(sin(dot(starGrid, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
    if (starHash > 0.994 && rayDir.y > -0.25) {
        float twinkle = 0.65 + 0.35 * sin(frameTimeCounter * 2.4 + starHash * 62.8);
        vec3 starTint = mix(vec3(0.65, 0.45, 1.0), vec3(0.95, 0.85, 1.0), fract(starHash * 137.0));
        color += starTint * smoothstep(0.994, 0.9995, starHash) * twinkle * 0.85;
    }
#endif
    if (isEyeInWater != 0) {
        vec3 viewRay = mat3(gbufferModelView) * rayDir;
        color = xonFog(color, viewRay * (isEyeInWater == 1 ? 28.0 : max(far, 128.0)), 1.0);
    }
    color *= 1.0 - max(blindness, darknessFactor);
    xonScene = vec4(color, 1.0);
#endif
}
