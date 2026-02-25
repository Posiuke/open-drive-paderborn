extends Node
class_name OriginManager

## Floating Origin system to prevent Float32 precision loss during long drives.
##
## Problem: At 300+ km from origin, Float32 has ~4cm precision -> physics jitter.
## Solution: When player moves >10km from current origin, shift everything back.
##
## The global UTM coordinates are tracked in GameManager.origin_utm_e/n.
## Chunk positions are always: chunk_utm_center - current_origin.

## Distance threshold for origin rebase (meters)
@export var rebase_threshold: float = 10000.0

## Reference to the world root containing all chunks
@export var world_root: Node3D

## Reference to the player vehicle
var _player: VehicleBody3D

# Rebase stats
var total_rebases: int = 0
var last_rebase_shift: Vector3 = Vector3.ZERO


func _ready() -> void:
	await get_tree().process_frame
	_player = get_node_or_null("../../PlayerCar")
	if world_root == null:
		world_root = get_parent() as Node3D


func _physics_process(_delta: float) -> void:
	if _player == null:
		_player = get_node_or_null("../../PlayerCar")
		if _player == null:
			return

	# Check if player is far enough from origin to warrant a rebase
	var pos := _player.global_position
	var distance := Vector2(pos.x, pos.z).length()

	if distance > rebase_threshold:
		_rebase_origin(pos)


func _rebase_origin(player_pos: Vector3) -> void:
	"""Shift everything so the player is near (0, y, 0) again.

	This is a single-frame operation that:
	1. Calculates the shift vector
	2. Moves all world children (chunks, objects)
	3. Moves the player
	4. Updates the global UTM origin in GameManager
	"""
	# Shift to move player's XZ near zero (keep Y unchanged)
	var shift := Vector3(player_pos.x, 0.0, player_pos.z)

	print("OriginManager: Rebasing origin. Shift: ", shift,
		  " Distance was: ", Vector2(player_pos.x, player_pos.z).length(), "m")

	# Update global UTM origin
	# Godot X = UTM East, Godot Z = UTM North
	GameManager.origin_utm_e += shift.x
	GameManager.origin_utm_n += shift.z

	# Shift all children of the world root
	if world_root:
		for child in world_root.get_children():
			if child is Node3D:
				child.position -= shift

	# Shift the player
	if _player:
		_player.global_position -= shift
		# VehicleBody3D: also need to wake up physics
		_player.sleeping = false

	# Shift any other top-level nodes that need it (camera targets etc.)
	# The camera rig follows the player, so it will update automatically.

	total_rebases += 1
	last_rebase_shift = shift

	print("OriginManager: Rebase #", total_rebases, " complete. ",
		  "New UTM origin: (", GameManager.origin_utm_e, ", ",
		  GameManager.origin_utm_n, ")")
