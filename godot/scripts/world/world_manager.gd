extends Node3D

## Dynamic chunk streaming manager.
## Loads and unloads terrain/building chunks based on player position.

@export var load_radius_lod0: int = 2   # 5×5 grid of full-detail chunks
@export var load_radius_lod1: int = 4   # Outer ring of simplified chunks

# Currently loaded chunk instances: key "cx_cz" → Node3D
var _loaded_chunks: Dictionary = {}
# Chunks currently being loaded (async)
var _loading_chunks: Dictionary = {}
# Player reference
var _player: VehicleBody3D
var _last_chunk: Vector2i = Vector2i(-9999, -9999)

# Performance tracking
var _frame_budget_ms: float = 4.0  # Max ms per frame for chunk loading
var _chunks_per_frame: int = 2     # Max chunks to load per frame
var _load_queue: Array = []


func _ready() -> void:
	# Find player car
	await get_tree().process_frame
	_player = get_node_or_null("../PlayerCar")
	if _player == null:
		push_warning("WorldManager: PlayerCar not found!")


func _process(delta: float) -> void:
	if _player == null:
		_player = get_node_or_null("../PlayerCar")
		if _player == null:
			return

	var player_chunk := GameManager.world_to_chunk(_player.global_position)

	# Only update when player moves to new chunk
	if player_chunk != _last_chunk:
		_last_chunk = player_chunk
		_update_chunks(player_chunk)

	# Process load queue
	_process_load_queue()

	# Update HUD
	_update_hud()


func _update_chunks(center: Vector2i) -> void:
	var needed_chunks: Dictionary = {}

	# LOD0: Close chunks with full detail
	for dx in range(-load_radius_lod0, load_radius_lod0 + 1):
		for dz in range(-load_radius_lod0, load_radius_lod0 + 1):
			var cx := center.x + dx
			var cz := center.y + dz
			var key := "%d_%d" % [cx, cz]
			needed_chunks[key] = 0  # LOD 0

	# LOD1: Outer ring
	for dx in range(-load_radius_lod1, load_radius_lod1 + 1):
		for dz in range(-load_radius_lod1, load_radius_lod1 + 1):
			var cx := center.x + dx
			var cz := center.y + dz
			var key := "%d_%d" % [cx, cz]
			if not needed_chunks.has(key):
				needed_chunks[key] = 1  # LOD 1

	# Unload chunks no longer needed
	var to_remove: Array = []
	for key in _loaded_chunks:
		if not needed_chunks.has(key):
			to_remove.append(key)

	for key in to_remove:
		_unload_chunk(key)

	# Queue loading of new chunks
	for key in needed_chunks:
		if not _loaded_chunks.has(key) and not _loading_chunks.has(key):
			var parts := key.split("_")
			var cx := int(parts[0])
			var cz := int(parts[1])
			var lod: int = needed_chunks[key]

			if GameManager.has_chunk(cx, cz):
				_load_queue.append({"key": key, "cx": cx, "cz": cz, "lod": lod})


func _process_load_queue() -> void:
	var loaded_this_frame := 0

	while _load_queue.size() > 0 and loaded_this_frame < _chunks_per_frame:
		var item: Dictionary = _load_queue.pop_front()
		_load_chunk(item["key"], item["cx"], item["cz"], item["lod"])
		loaded_this_frame += 1


func _load_chunk(key: String, cx: int, cz: int, lod: int) -> void:
	var file_path := GameManager.get_chunk_file(cx, cz, lod)
	if file_path == "":
		return

	if not ResourceLoader.exists(file_path):
		return

	_loading_chunks[key] = true

	# Load the GLB scene
	var scene := load(file_path) as PackedScene
	if scene == null:
		_loading_chunks.erase(key)
		return

	var instance := scene.instantiate()
	instance.name = "Chunk_" + key

	# Generate static collision bodies for the chunk
	_generate_collisions(instance)

	add_child(instance)
	_loaded_chunks[key] = instance
	_loading_chunks.erase(key)

	GameManager.loaded_chunks = _loaded_chunks.size()


func _unload_chunk(key: String) -> void:
	if _loaded_chunks.has(key):
		var node: Node3D = _loaded_chunks[key]
		node.queue_free()
		_loaded_chunks.erase(key)
		GameManager.loaded_chunks = _loaded_chunks.size()


func _generate_collisions(chunk_node: Node) -> void:
	# Find all MeshInstance3D children and create static body collisions
	for child in chunk_node.get_children():
		if child is MeshInstance3D:
			var mesh_instance: MeshInstance3D = child
			var mesh := mesh_instance.mesh

			if mesh == null:
				continue

			var layer_name := mesh_instance.name.to_lower()

			# Create StaticBody3D with collision
			var static_body := StaticBody3D.new()

			if "building" in layer_name:
				# Use simplified box collisions for buildings
				static_body.collision_layer = 2  # buildings layer
				var shape := mesh.create_convex_shape()
				if shape:
					var col_shape := CollisionShape3D.new()
					col_shape.shape = shape
					static_body.add_child(col_shape)
			elif "road" in layer_name or "terrain" in layer_name:
				# Use trimesh for roads and terrain (driveable surfaces)
				static_body.collision_layer = 1  # terrain layer
				var shape := mesh.create_trimesh_shape()
				if shape:
					var col_shape := CollisionShape3D.new()
					col_shape.shape = shape
					static_body.add_child(col_shape)
			else:
				# Landuse/water - terrain layer
				static_body.collision_layer = 1
				var shape := mesh.create_trimesh_shape()
				if shape:
					var col_shape := CollisionShape3D.new()
					col_shape.shape = shape
					static_body.add_child(col_shape)

			if static_body.get_child_count() > 0:
				mesh_instance.add_child(static_body)
			else:
				static_body.queue_free()

		# Recurse into children
		if child.get_child_count() > 0:
			_generate_collisions(child)


func _update_hud() -> void:
	var chunk_label := get_node_or_null("../HUD/ChunkInfo")
	if chunk_label and chunk_label is Label:
		chunk_label.text = "Chunks: %d loaded" % _loaded_chunks.size()
