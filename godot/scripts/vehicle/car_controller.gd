extends VehicleBody3D

## Car controller with speed-dependent steering, gas, brake, and reverse.

# Engine
@export var max_engine_force: float = 3500.0
@export var max_brake_force: float = 50.0
@export var max_speed_kmh: float = 180.0
@export var reverse_max_speed_kmh: float = 30.0
@export var reverse_force_multiplier: float = 0.4

# Steering
@export var max_steer_angle: float = 0.45  # radians (~25°)
@export var steer_speed: float = 3.0       # How fast steering responds
@export var steer_return_speed: float = 5.0 # How fast steering centers

# Speed-dependent steering reduction
@export var speed_steer_curve_min_speed: float = 30.0  # km/h where reduction starts
@export var speed_steer_curve_max_speed: float = 120.0 # km/h where reduction maxes
@export var min_steer_at_speed: float = 0.3  # Min steering multiplier at high speed

# State
var _current_steer: float = 0.0
var _speed_kmh: float = 0.0
var _is_reversing: bool = false
var _gear_text: String = "D"
var _spawn_transform: Transform3D

# Wheel references
@onready var _wheel_fl: VehicleWheel3D = $WheelFL
@onready var _wheel_fr: VehicleWheel3D = $WheelFR
@onready var _wheel_rl: VehicleWheel3D = $WheelRL
@onready var _wheel_rr: VehicleWheel3D = $WheelRR


func _ready() -> void:
	_spawn_transform = global_transform
	GameManager.player_car = self


func _physics_process(delta: float) -> void:
	# Calculate speed
	var velocity_local := global_basis.inverse() * linear_velocity
	_speed_kmh = abs(velocity_local.z) * 3.6  # m/s → km/h
	var forward_speed := -velocity_local.z  # Negative Z is forward in Godot

	GameManager.player_speed_kmh = _speed_kmh

	# === Steering ===
	var steer_input := Input.get_axis("steer_right", "steer_left")

	# Speed-dependent steering
	var speed_factor := 1.0
	if _speed_kmh > speed_steer_curve_min_speed:
		var t := clampf(
			(_speed_kmh - speed_steer_curve_min_speed) /
			(speed_steer_curve_max_speed - speed_steer_curve_min_speed),
			0.0, 1.0
		)
		speed_factor = lerpf(1.0, min_steer_at_speed, t)

	var target_steer := steer_input * max_steer_angle * speed_factor

	# Smooth steering
	if abs(steer_input) > 0.01:
		_current_steer = move_toward(_current_steer, target_steer, steer_speed * delta)
	else:
		_current_steer = move_toward(_current_steer, 0.0, steer_return_speed * delta)

	steering = _current_steer

	# === Throttle / Brake / Reverse ===
	var gas_input := Input.get_action_strength("move_forward")
	var brake_input := Input.get_action_strength("move_backward")
	var space_brake := Input.get_action_strength("brake")
	var handbrake := Input.is_action_pressed("handbrake")

	# Determine direction
	if gas_input > 0.01:
		if _is_reversing and _speed_kmh < 2.0:
			_is_reversing = false

		if not _is_reversing:
			# Forward drive
			if _speed_kmh < max_speed_kmh:
				engine_force = gas_input * max_engine_force
			else:
				engine_force = 0.0
			brake = 0.0
			_gear_text = "D"
		else:
			# Was reversing, brake first
			engine_force = 0.0
			brake = max_brake_force
			_gear_text = "R"

	elif brake_input > 0.01:
		if forward_speed > 1.0:
			# Moving forward → brake
			engine_force = 0.0
			brake = brake_input * max_brake_force
			_gear_text = "D"
		elif _speed_kmh < 2.0:
			# Stopped or slow → reverse
			_is_reversing = true
			if _speed_kmh < reverse_max_speed_kmh:
				engine_force = -brake_input * max_engine_force * reverse_force_multiplier
			else:
				engine_force = 0.0
			brake = 0.0
			_gear_text = "R"
		else:
			# Transition
			engine_force = 0.0
			brake = brake_input * max_brake_force * 0.5
			_gear_text = "D"
	else:
		# No input → coast / engine brake
		engine_force = 0.0
		if _speed_kmh > 1.0:
			brake = 2.0  # Light engine braking
		else:
			brake = 0.0
			_is_reversing = false
		_gear_text = "N" if _speed_kmh < 1.0 else "D"

	# Space brake (always brakes)
	if space_brake > 0.01:
		brake = maxf(brake, space_brake * max_brake_force)
		engine_force = 0.0

	# Handbrake
	if handbrake:
		brake = max_brake_force
		engine_force = 0.0
		# Lock rear wheels
		_wheel_rl.wheel_friction_slip = 0.5
		_wheel_rr.wheel_friction_slip = 0.5
	else:
		_wheel_rl.wheel_friction_slip = 3.5
		_wheel_rr.wheel_friction_slip = 3.5

	# === Reset ===
	if Input.is_action_just_pressed("reset_car"):
		_reset_car()

	# === Update HUD ===
	_update_hud()

	# === Prevent falling into void ===
	if global_position.y < -50.0:
		_reset_car()


func _reset_car() -> void:
	# Reset position to spawn or slightly above current position
	var reset_transform := global_transform
	reset_transform.basis = Basis()  # Reset rotation
	reset_transform.origin.y += 2.0  # Lift up

	global_transform = reset_transform
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	_is_reversing = false


func _update_hud() -> void:
	# Speed
	var speed_label := get_node_or_null("../HUD/SpeedLabel")
	if speed_label and speed_label is Label:
		speed_label.text = "%d km/h" % int(_speed_kmh)

	# Gear
	var gear_label := get_node_or_null("../HUD/GearLabel")
	if gear_label and gear_label is Label:
		gear_label.text = _gear_text

	# Color speed label based on speed
	if speed_label and speed_label is Label:
		if _speed_kmh > 100:
			speed_label.modulate = Color(1.0, 0.3, 0.3)
		elif _speed_kmh > 50:
			speed_label.modulate = Color(1.0, 0.8, 0.3)
		else:
			speed_label.modulate = Color(1.0, 1.0, 1.0)
