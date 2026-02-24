shader_type spatial;
render_mode specular_phong;

// Water shader for the Pader river and Paderquellgebiet
uniform vec4 water_color : source_color = vec4(0.15, 0.35, 0.55, 1.0);
uniform vec4 foam_color : source_color = vec4(0.7, 0.8, 0.85, 1.0);
uniform float wave_speed : hint_range(0.01, 2.0) = 0.3;
uniform float wave_scale : hint_range(0.5, 20.0) = 5.0;
uniform float wave_height : hint_range(0.0, 1.0) = 0.15;
uniform float roughness : hint_range(0.0, 1.0) = 0.1;
uniform float metallic : hint_range(0.0, 1.0) = 0.3;
uniform float transparency : hint_range(0.0, 1.0) = 0.7;

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

void vertex() {
    // Animated wave displacement
    float t = TIME * wave_speed;
    vec2 wave_uv = VERTEX.xz * wave_scale;
    float wave1 = sin(wave_uv.x * 0.5 + t) * cos(wave_uv.y * 0.3 + t * 0.7);
    float wave2 = sin(wave_uv.x * 0.3 - t * 0.5) * cos(wave_uv.y * 0.5 + t * 0.3);
    VERTEX.y += (wave1 + wave2) * wave_height * 0.5;
}

void fragment() {
    float t = TIME * wave_speed;
    vec2 uv1 = UV * wave_scale + vec2(t * 0.1, t * 0.05);
    vec2 uv2 = UV * wave_scale * 1.5 + vec2(-t * 0.07, t * 0.08);

    float n1 = noise(uv1);
    float n2 = noise(uv2);
    float combined = (n1 + n2) * 0.5;

    // Color variation
    vec3 color = mix(water_color.rgb, water_color.rgb * 1.3, combined);

    // Foam highlights
    float foam = smoothstep(0.65, 0.8, combined);
    color = mix(color, foam_color.rgb, foam * 0.3);

    // Normal perturbation for reflections
    float nx = noise(uv1 + vec2(0.01, 0.0)) - noise(uv1 - vec2(0.01, 0.0));
    float nz = noise(uv1 + vec2(0.0, 0.01)) - noise(uv1 - vec2(0.0, 0.01));
    NORMAL = normalize(NORMAL + vec3(nx, 0.0, nz) * 0.5);

    ALBEDO = color;
    ROUGHNESS = roughness;
    METALLIC = metallic;
    ALPHA = transparency;
}
