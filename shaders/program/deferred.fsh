#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
uniform sampler2D colortex0;
in vec2 xonUV;
layout(location = 0) out vec4 xonOpaqueCopy;

void main() {
    xonOpaqueCopy = vec4(texture(colortex0, xonSourceUV(xonUV)).rgb, 1.0);
}
