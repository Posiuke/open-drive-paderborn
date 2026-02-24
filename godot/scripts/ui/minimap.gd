extends Control

## Simple minimap overlay with player indicator.

@export var map_size: float = 500.0  # World units shown
@export var bg_color: Color = Color(0.1, 0.15, 0.1, 0.8)
@export var player_color: Color = Color(1, 0.3, 0.3)
@export var border_color: Color = Color(0.4, 0.4, 0.4)


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	var rect_size := size
	var center := rect_size / 2.0

	# Background
	draw_rect(Rect2(Vector2.ZERO, rect_size), bg_color)

	# Border
	draw_rect(Rect2(Vector2.ZERO, rect_size), border_color, false, 2.0)

	# Player indicator (triangle pointing forward)
	var tri_size := 8.0
	var car_rotation := 0.0
	if GameManager.player_car:
		car_rotation = -GameManager.player_car.global_rotation.y

	var forward := Vector2(sin(car_rotation), -cos(car_rotation))
	var right := Vector2(forward.y, -forward.x)

	var p1 := center + forward * tri_size
	var p2 := center - forward * tri_size * 0.6 + right * tri_size * 0.5
	var p3 := center - forward * tri_size * 0.6 - right * tri_size * 0.5

	draw_colored_polygon(PackedVector2Array([p1, p2, p3]), player_color)

	# North indicator
	draw_string(ThemeDB.fallback_font, Vector2(center.x - 4, 15), "N",
		HORIZONTAL_ALIGNMENT_CENTER, -1, 12, Color.WHITE)
