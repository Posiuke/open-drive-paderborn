extends Control

## Round speedometer display widget.

@export var max_speed: float = 200.0
@export var needle_color: Color = Color(1, 0.2, 0.2)
@export var dial_color: Color = Color(0.9, 0.9, 0.9)
@export var bg_color: Color = Color(0.1, 0.1, 0.12, 0.85)

var _speed: float = 0.0


func _process(_delta: float) -> void:
	_speed = GameManager.player_speed_kmh
	queue_redraw()


func _draw() -> void:
	var center := size / 2.0
	var radius := min(size.x, size.y) / 2.0 - 10.0

	# Background circle
	draw_circle(center, radius, bg_color)

	# Dial markings
	var start_angle := PI * 0.75  # 135°
	var end_angle := PI * 2.25     # 405°
	var sweep := end_angle - start_angle

	# Major ticks (every 20 km/h)
	for i in range(0, int(max_speed) + 1, 20):
		var t := float(i) / max_speed
		var angle := start_angle + t * sweep
		var inner := center + Vector2(cos(angle), sin(angle)) * (radius - 20)
		var outer := center + Vector2(cos(angle), sin(angle)) * (radius - 5)
		draw_line(inner, outer, dial_color, 2.0)

	# Minor ticks (every 10 km/h)
	for i in range(0, int(max_speed) + 1, 10):
		var t := float(i) / max_speed
		var angle := start_angle + t * sweep
		var inner := center + Vector2(cos(angle), sin(angle)) * (radius - 12)
		var outer := center + Vector2(cos(angle), sin(angle)) * (radius - 5)
		draw_line(inner, outer, dial_color, 1.0)

	# Needle
	var speed_t := clampf(_speed / max_speed, 0.0, 1.0)
	var needle_angle := start_angle + speed_t * sweep
	var needle_end := center + Vector2(cos(needle_angle), sin(needle_angle)) * (radius - 25)
	draw_line(center, needle_end, needle_color, 3.0, true)

	# Center hub
	draw_circle(center, 5.0, needle_color)
