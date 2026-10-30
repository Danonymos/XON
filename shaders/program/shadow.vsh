#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/shadows.glsl"

in vec4 mc_Entity;
in vec4 mc_midTexCoord;
out vec2 xonShadowUV;

void main() {
    xonShadowUV = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    vec4 shadowView = gl_ModelViewMatrix * gl_Vertex;
#ifdef XON_WAVING_FOLIAGE
    bool isLeaves = abs(mc_Entity.x - 10003.0) < 0.5;
    bool isCrossPlant = abs(mc_Entity.x - 10004.0) < 0.5;
    if (isLeaves || isCrossPlant) {
        vec3 playerPos = (shadowModelViewInverse * shadowView).xyz;
        float foliageDistSq = dot(playerPos, playerPos);
        if (foliageDistSq < 784.0) {
            float waveFade = 1.0 - smoothstep(400.0, 784.0, foliageDistSq);
            float topVertex = isCrossPlant ? float(gl_MultiTexCoord0.t < mc_midTexCoord.t) : 0.45;
            vec3 worldPos = playerPos + cameraPosition;
            float windTime = frameTimeCounter * 2.2;
            float waveX = sin(windTime + worldPos.x * 1.3 + worldPos.z * 0.7 + worldPos.y * 0.5);
            float waveZ = cos(windTime * 0.85 + worldPos.z * 1.4 - worldPos.x * 0.6);
            float skylight = clamp((gl_TextureMatrix[1] * gl_MultiTexCoord1).y * (16.0 / 15.0) - (1.0 / 30.0), 0.0, 1.0);
            float strength = (0.032 + rainStrength * 0.024) * topVertex * (0.35 + 0.65 * skylight) * waveFade;
            playerPos.xz += vec2(waveX, waveZ) * strength;
            shadowView = shadowModelView * vec4(playerPos, 1.0);
        }
    }
#endif
    vec4 clip = gl_ProjectionMatrix * shadowView;
    clip.xyz = xonDistortShadow(clip.xyz / clip.w) * clip.w;
    gl_Position = clip;
}
