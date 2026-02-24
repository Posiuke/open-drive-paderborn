shader_type spatial;

// Procedural building facade with windows
uniform vec4 wall_color : source_color = vec4(0.7, 0.65, 0.6, 1.0);
uniform vec4 window_color : source_color = vec4(0.3, 0.4, 0.55, 1.0);
uniform vec4 window_lit_color : source_color = vec4(0.9, 0.8, 0.5, 1.0);
uniform float window_width : hint_range(0.1, 0.9) = 0.6;
uniform float window_height : hint_range(0.1, 0.9) = 0.5;
uniform float floor_height : hint_range(1.0, 5.0) = 3.0;
uniform float window_spacing : hint_range(1.0, 5.0) = 3.0;
uniform float roughness : hint_range(0.0, 1.0) = 0.8;
uniform float lit_probability : hint_range(0.0, 1.0) = 0.3;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void fragment() {
    vec2 uv = UV;

    // Scale UV to world units (UV is tiled per 3m)
    vec2 world_uv = uv * vec2(window_spacing, floor_height);

    // Window grid
    vec2 cell = floor(world_uv);
    vec2 cell_uv = fract(world_uv);

    // Window rectangle
    float margin_x = (1.0 - window_width) / 2.0;
    float margin_y_bottom = 0.15;
    float margin_y_top = 1.0 - window_height - margin_y_bottom;

    bool is_window = cell_uv.x > margin_x && cell_uv.x < (1.0 - margin_x) &&
                     cell_uv.y > margin_y_bottom && cell_uv.y < (margin_y_bottom + window_height);

    // Skip ground floor windows (first row)
    if (cell.y < 0.5) {
        is_window = false;
    }

    vec3 color = wall_color.rgb;
    float rough = roughness;

    if (is_window) {
        // Determine if window is lit
        float h = hash(cell);
        if (h < lit_probability) {
            color = window_lit_color.rgb;
            rough = 0.2;
        } else {
            color = window_color.rgb;
            rough = 0.15;
        }

        // Window frame
        float frame_width = 0.03;
        if (cell_uv.x < margin_x + frame_width || cell_uv.x > 1.0 - margin_x - frame_width ||
            cell_uv.y < margin_y_bottom + frame_width || cell_uv.y > margin_y_bottom + window_height - frame_width) {
            color = wall_color.rgb * 0.8;
            rough = roughness;
        }
    } else {
        // Wall noise
        float n = hash(floor(uv * 100.0)) * 0.04;
        color += vec3(n);
    }

    ALBEDO = color;
    ROUGHNESS = rough;
    METALLIC = is_window ? 0.3 : 0.0;
}
