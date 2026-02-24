shader_type spatial;

// Terrain shader with grass-like appearance
uniform vec4 grass_color_1 : source_color = vec4(0.25, 0.5, 0.18, 1.0);
uniform vec4 grass_color_2 : source_color = vec4(0.35, 0.6, 0.22, 1.0);
uniform vec4 dirt_color : source_color = vec4(0.45, 0.38, 0.25, 1.0);
uniform float roughness : hint_range(0.0, 1.0) = 0.9;
uniform float noise_scale : hint_range(1.0, 100.0) = 20.0;
uniform float blend_sharpness : hint_range(1.0, 20.0) = 8.0;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; i++) {
        v += a * noise(p);
        p *= 2.0;
        a *= 0.5;
    }
    return v;
}

void fragment() {
    vec2 world_pos = UV * noise_scale;

    // Multi-octave noise for grass variation
    float n = fbm(world_pos);
    float n2 = fbm(world_pos * 3.0 + vec2(100.0));

    // Blend grass colors
    vec3 grass = mix(grass_color_1.rgb, grass_color_2.rgb, n);

    // Dirt patches
    float dirt_mask = smoothstep(0.45, 0.55, n2);
    vec3 color = mix(grass, dirt_color.rgb, dirt_mask * 0.3);

    // Slope-based dirt (steeper = more dirt)
    float slope = 1.0 - dot(NORMAL, vec3(0.0, 1.0, 0.0));
    color = mix(color, dirt_color.rgb, smoothstep(0.3, 0.6, slope));

    ALBEDO = color;
    ROUGHNESS = roughness;
    METALLIC = 0.0;
}
