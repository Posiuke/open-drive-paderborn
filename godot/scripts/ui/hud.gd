extends CanvasLayer

## HUD controller for speed, gear, minimap, and info display.

@onready var speed_label: Label = $SpeedLabel
@onready var gear_label: Label = $GearLabel
@onready var info_label: Label = $InfoLabel
@onready var chunk_info: Label = $ChunkInfo
@onready var minimap_rect: TextureRect = $MinimapRect
@onready var minimap_viewport: SubViewport = $MinimapViewport
@onready var minimap_camera: Camera3D = $MinimapViewport/MinimapCamera


func _ready() -> void:
	# Set minimap viewport texture
	await get_tree().process_frame
	if minimap_viewport and minimap_rect:
		minimap_rect.texture = minimap_viewport.get_texture()


func _process(_delta: float) -> void:
	_update_minimap()


func _update_minimap() -> void:
	if not minimap_camera or not GameManager.player_car:
		return

	# Follow player from above
	var car_pos := GameManager.player_car.global_position
	minimap_camera.global_position = Vector3(car_pos.x, car_pos.y + 300, car_pos.z)
	minimap_camera.global_rotation = Vector3(-PI / 2.0, 0, 0)

	# Rotate minimap with car heading
	var car_rot := GameManager.player_car.global_rotation.y
	minimap_camera.global_rotation.y = -car_rot
