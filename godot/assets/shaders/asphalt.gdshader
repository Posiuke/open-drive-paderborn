shader_type spatial;

// Asphalt road shader with subtle noise and lane markings
uniform vec4 base_color : source_color = vec4(0.3, 0.3, 0.32, 1.0);
uniform float roughness : hint_range(0.0, 1.0) = 0.85;
uniform float noise_strength : hint_range(0.0, 0.2) = 0.05;
uniform float lane_width : hint_range(0.01, 0.1) = 0.02;
uniform vec4 lane_color : source_color = vec4(0.9, 0.9, 0.9, 1.0);
uniform float lane_dash_length : hint_range(1.0, 20.0) = 6.0;
uniform float lane_gap_length : hint_range(1.0, 20.0) = 6.0;

// Simple hash function for noise
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

void fragment() {
    vec2 uv = UV;

    // Asphalt noise
    float n = noise(uv * 80.0) * noise_strength;
    float n2 = noise(uv * 200.0) * noise_strength * 0.5;

    vec3 color = base_color.rgb + vec3(n + n2);

    // Center lane marking (dashed)
    float center_dist = abs(uv.x - 0.5);
    float dash = step(0.5, fract(uv.y * lane_dash_length / (lane_dash_length + lane_gap_length)));
    if (center_dist < lane_width && dash > 0.5) {
        color = mix(color, lane_color.rgb, 0.8);
    }

    // Edge lines (solid)
    if (uv.x < lane_width * 2.0 || uv.x > 1.0 - lane_width * 2.0) {
        color = mix(color, lane_color.rgb, 0.6);
    }

    ALBEDO = color;
    ROUGHNESS = roughness;
    METALLIC = 0.0;
}
