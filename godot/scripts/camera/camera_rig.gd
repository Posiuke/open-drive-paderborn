extends Node3D

## Camera rig with Third-Person (SpringArm) and First-Person (Cockpit) modes.
## Toggle with V key.

@export var target_path: NodePath
@export var follow_speed: float = 8.0
@export var rotation_speed: float = 5.0

# Third-person settings
@export var tp_height: float = 2.5
@export var tp_distance: float = 8.0
@export var tp_look_ahead: float = 3.0

# Camera mode
enum CameraMode { THIRD_PERSON, FIRST_PERSON }
var _mode: CameraMode = CameraMode.THIRD_PERSON

# References
var _target: Node3D
var _tp_camera: Camera3D
var _fp_camera: Camera3D
var _spring_arm: SpringArm3D
var _tp_pivot: Node3D

# Smooth follow
var _smooth_position: Vector3
var _smooth_rotation: float = 0.0


func _ready() -> void:
	await get_tree().process_frame

	if target_path:
		_target = get_node_or_null(target_path)

	_tp_pivot = $ThirdPersonPivot
	_spring_arm = $ThirdPersonPivot/SpringArm3D
	_tp_camera = $ThirdPersonPivot/SpringArm3D/ThirdPersonCamera
	_fp_camera = $FirstPersonCamera

	if _target:
		_smooth_position = _target.global_position
		_smooth_rotation = _target.global_rotation.y

	_set_camera_mode(_mode)


func _process(delta: float) -> void:
	if _target == null:
		_target = get_node_or_null(target_path) if target_path else null
		if _target == null:
			return

	# Toggle camera
	if Input.is_action_just_pressed("toggle_camera"):
		if _mode == CameraMode.THIRD_PERSON:
			_set_camera_mode(CameraMode.FIRST_PERSON)
		else:
			_set_camera_mode(CameraMode.THIRD_PERSON)

	match _mode:
		CameraMode.THIRD_PERSON:
			_update_third_person(delta)
		CameraMode.FIRST_PERSON:
			_update_first_person(delta)


func _set_camera_mode(mode: CameraMode) -> void:
	_mode = mode
	match mode:
		CameraMode.THIRD_PERSON:
			if _tp_camera:
				_tp_camera.current = true
			if _fp_camera:
				_fp_camera.current = false
		CameraMode.FIRST_PERSON:
			if _fp_camera:
				_fp_camera.current = true
			if _tp_camera:
				_tp_camera.current = false


func _update_third_person(delta: float) -> void:
	if not _target or not _tp_pivot:
		return

	var target_pos := _target.global_position
	var target_rot := _target.global_rotation.y

	# Get car velocity for look-ahead
	var velocity := Vector3.ZERO
	if _target is RigidBody3D:
		velocity = (_target as RigidBody3D).linear_velocity

	# Speed-dependent distance
	var speed := velocity.length()
	var speed_factor := clampf(speed / 30.0, 0.0, 1.0)
	var current_distance := lerpf(tp_distance, tp_distance * 1.4, speed_factor)
	var current_height := lerpf(tp_height, tp_height * 1.2, speed_factor)

	# Smooth position follow
	_smooth_position = _smooth_position.lerp(target_pos, follow_speed * delta)

	# Smooth rotation follow (with look-ahead in velocity direction)
	var desired_rot := target_rot
	if speed > 2.0:
		var vel_angle := atan2(velocity.x, velocity.z)
		desired_rot = lerp_angle(target_rot, vel_angle, 0.3)

	_smooth_rotation = lerp_angle(_smooth_rotation, desired_rot, rotation_speed * delta)

	# Position the pivot
	_tp_pivot.global_position = _smooth_position + Vector3(0, current_height, 0)
	_tp_pivot.global_rotation.y = _smooth_rotation + PI

	# Update spring arm length
	if _spring_arm:
		_spring_arm.spring_length = current_distance


func _update_first_person(delta: float) -> void:
	if not _target or not _fp_camera:
		return

	# Attach camera to car
	var car_transform := _target.global_transform
	var offset := car_transform.basis * Vector3(0, 1.2, 0.3)
	_fp_camera.global_position = car_transform.origin + offset
	_fp_camera.global_rotation = _target.global_rotation
	# Look forward
	_fp_camera.rotate_y(PI)
