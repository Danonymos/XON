#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"

out vec2 xonTexCoord;
out vec4 xonAtlasBounds;
out vec2 xonLightLevels;
out vec4 xonVertexColor;
out vec3 xonViewPosition;
out vec3 xonPlayerPosition;
out vec3 xonWorldNormal;
flat out float xonMaterial;

#if defined XON_TERRAIN || defined XON_WATER
in vec4 mc_Entity;
in vec4 mc_midTexCoord;
#endif

void main() {
#ifdef XON_LINE
    float lineWidth = max(gl_Color.r, max(gl_Color.g, gl_Color.b)) < 0.15 ? 2.5 : 2.0;
    const float VIEW_SHRINK = 1.0 - (1.0 / 256.0);
    const mat4 VIEW_SCALE = mat4(
        VIEW_SHRINK, 0.0, 0.0, 0.0,
        0.0, VIEW_SHRINK, 0.0, 0.0,
        0.0, 0.0, VIEW_SHRINK, 0.0,
        0.0, 0.0, 0.0, 1.0
    );
    vec2 resolution = vec2(viewWidth, viewHeight) * XON_RENDER_SCALE;
    vec4 linePosStart = gl_ProjectionMatrix * VIEW_SCALE * gl_ModelViewMatrix * gl_Vertex;
    vec4 linePosEnd = gl_ProjectionMatrix * VIEW_SCALE * gl_ModelViewMatrix * vec4(gl_Vertex.xyz + gl_Normal, 1.0);
    vec3 ndc1 = linePosStart.xyz / max(abs(linePosStart.w), 0.00001);
    vec3 ndc2 = linePosEnd.xyz / max(abs(linePosEnd.w), 0.00001);
    vec2 lineScreenDirection = xonSafeNormalize(vec3((ndc2.xy - ndc1.xy) * resolution, 0.0)).xy;
    vec2 lineOffset = vec2(-lineScreenDirection.y, lineScreenDirection.x) * lineWidth / max(resolution, vec2(1.0));
    if (lineOffset.x < 0.0) lineOffset = -lineOffset;
    if (gl_VertexID % 2 != 0) lineOffset = -lineOffset;
    vec4 viewPosition = gl_ModelViewMatrix * gl_Vertex;
    xonViewPosition = viewPosition.xyz;
    xonPlayerPosition = (gbufferModelViewInverse * viewPosition).xyz;
    xonTexCoord = vec2(0.0);
    xonAtlasBounds = vec4(0.0);
    xonLightLevels = vec2(0.0, 1.0);
    xonVertexColor = gl_Color;
    xonWorldNormal = vec3(0.0, 1.0, 0.0);
    xonMaterial = 0.0;
    gl_Position = xonScaleClip(vec4((ndc1 + vec3(lineOffset, 0.0)) * linePosStart.w, linePosStart.w));
#else
    vec4 viewPosition = gl_ModelViewMatrix * gl_Vertex;
    vec3 playerPos = (gbufferModelViewInverse * viewPosition).xyz;
    xonTexCoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    xonAtlasBounds = vec4(xonTexCoord, 0.0, 0.0);
#if defined XON_TERRAIN || defined XON_WATER
    vec2 midUV = (gl_TextureMatrix[0] * mc_midTexCoord).xy;
    vec2 halfSpan = abs(xonTexCoord - midUV);
    if (halfSpan.x > 0.00001 && halfSpan.y > 0.00001) {
        xonAtlasBounds = vec4(midUV, halfSpan);
    }
#endif
    xonLightLevels = clamp((gl_TextureMatrix[1] * gl_MultiTexCoord1).xy
                         * (16.0 / 15.0) - (1.0 / 30.0), 0.0, 1.0);
    xonVertexColor = gl_Color;
    xonWorldNormal = xonSafeNormalize(mat3(gbufferModelViewInverse)
                                   * (gl_NormalMatrix * gl_Normal));
    xonMaterial = 0.0;
#if defined XON_TERRAIN || defined XON_WATER
    xonMaterial = mc_Entity.x;
#endif
#ifdef XON_TERRAIN
#ifdef XON_WAVING_FOLIAGE
    bool isLeaves = abs(xonMaterial - 10003.0) < 0.5;
    bool isCrossPlant = abs(xonMaterial - 10004.0) < 0.5;
    float foliageDistSq = dot(playerPos, playerPos);
    if ((isLeaves || isCrossPlant) && foliageDistSq < 1600.0) {
        float waveFade = 1.0 - smoothstep(900.0, 1600.0, foliageDistSq);
        float topVertex = isCrossPlant ? float(gl_MultiTexCoord0.t < mc_midTexCoord.t) : 0.45;
        vec3 worldPos = playerPos + cameraPosition;
        float windTime = frameTimeCounter * 2.2;
        float waveX = sin(windTime + worldPos.x * 1.3 + worldPos.z * 0.7 + worldPos.y * 0.5);
        float waveZ = cos(windTime * 0.85 + worldPos.z * 1.4 - worldPos.x * 0.6);
        float strength = (0.032 + rainStrength * 0.024) * topVertex * (0.35 + 0.65 * xonLightLevels.y) * waveFade;
        playerPos.xz += vec2(waveX, waveZ) * strength;
        viewPosition = gbufferModelView * vec4(playerPos, 1.0);
    }
#endif
#endif
    xonViewPosition = viewPosition.xyz;
    xonPlayerPosition = playerPos;
    gl_Position = xonScaleClip(gl_ProjectionMatrix * viewPosition);
#endif
}
