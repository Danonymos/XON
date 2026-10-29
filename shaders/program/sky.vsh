#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"

out vec3 xonSkyRay;
out vec4 xonSkyVertexColor;
out vec2 xonSkyTexCoord;

void main() {
    vec4 viewPosition = gl_ModelViewMatrix * gl_Vertex;
    xonSkyRay = mat3(gbufferModelViewInverse) * viewPosition.xyz;
    xonSkyVertexColor = gl_Color;
    xonSkyTexCoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    gl_Position = xonScaleClip(gl_ProjectionMatrix * viewPosition);
}
