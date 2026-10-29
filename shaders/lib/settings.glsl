#ifndef XON_SETTINGS
#define XON_SETTINGS

#define XON_MOTION_BLUR
#define XON_WAVING_FOLIAGE
#define XON_CAUSTICS
#define XON_HAND_LIGHT
#define XON_CLOUD_LIGHTING
#define XON_SHADOWS
#define XON_LIGHT_SHAFTS
#define XON_EMISSIVE_ORES
#define XON_BLOOM
#define XON_REFRACTION
#define XON_COLOR_GRADE
#define XON_EDGE_AA
//#define XON_AIR_FOG
#define XON_CLOUD_STYLE 1 // [0 1]
#define XON_ORE_GLOW 1.25 // [0.50 0.75 1.00 1.25 1.50 2.00]
#define XON_GRADE_STRENGTH 0.85 // [0.00 0.50 0.70 0.85 1.00]
#define XON_SATURATION 0.70 // [0.00 0.25 0.50 0.60 0.70 0.80 0.90 1.00 1.20 1.40]
#define XON_BLUR_STRENGTH 1.00 // [0.25 0.50 0.75 1.00 1.25 1.50 2.00]
#define XON_AO_STRENGTH 1.00 // [0.00 0.50 0.75 1.00 1.25 1.50]
#define XON_BRIGHTNESS 1.05 // [0.80 0.90 1.00 1.05 1.10 1.20 1.30]
#define XON_WARMTH 0.65 // [0.00 0.35 0.65 0.85 1.00]
#define XON_WATER_DETAIL 1 // [0 1]
#define XON_BLOCK_OUTLINE 1 // [0 1]
#define XON_FOG_AMOUNT 1.00 // [0.60 0.80 1.00 1.20 1.40]
#define XON_RENDER_MODE 0 // [0 1 2]

#if XON_RENDER_MODE == 1
#define XON_RENDER_SCALE 0.85
#elif XON_RENDER_MODE == 2
#define XON_RENDER_SCALE 0.75
#else
#define XON_RENDER_SCALE 1.00
#endif

const float XON_BLUR_EXPOSURE = 0.0055 * XON_BLUR_STRENGTH;
const float XON_BLUR_RADIUS = 10.0 * (0.4 + 0.6 * XON_BLUR_STRENGTH);
const int shadowMapResolution = 1024; // [512 1024 1536 2048]
const float shadowDistance = 96.0; // [64.0 80.0 96.0 128.0 160.0]
const float shadowIntervalSize = 2.0;
const bool shadowHardwareFiltering = true;
const float sunPathRotation = -25.0;

#endif
