#ifndef XON_UNIFORMS
#define XON_UNIFORMS

uniform mat4 gbufferModelView;
uniform mat4 gbufferModelViewInverse;
uniform mat4 gbufferProjection;
uniform mat4 gbufferProjectionInverse;
uniform mat4 gbufferPreviousModelView;
uniform mat4 gbufferPreviousProjection;
uniform mat4 shadowModelView;
uniform mat4 shadowModelViewInverse;
uniform mat4 shadowProjection;
uniform vec3 cameraPosition;
uniform vec3 previousCameraPosition;
uniform vec3 sunPosition;
uniform vec3 fogColor;
uniform vec3 skyColor;
uniform vec4 lightningBoltPosition;
uniform ivec2 eyeBrightnessSmooth;
uniform vec4 entityColor;
uniform float viewWidth;
uniform float viewHeight;
uniform float frameTimeCounter;
uniform float frameTime;
uniform float rainStrength;
uniform float wetness;
uniform float thunderStrength;
uniform float nightVision;
uniform float blindness;
uniform float darknessFactor;
uniform float far;
uniform float fogStart;
uniform float fogEnd;
uniform float alphaTestRef;
uniform float endFlashIntensity;
uniform int frameCounter;
uniform int isEyeInWater;
uniform int moonPhase;
uniform int heldBlockLightValue;
uniform int heldBlockLightValue2;
uniform int renderStage;

#endif
