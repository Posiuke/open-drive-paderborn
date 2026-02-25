extends Node3D

## Dynamic chunk streaming manager.
## Loads and unloads terrain/building chunks based on player position.
## Supports both local file loading and HTTP server streaming.

@export var load_radius_lod0: int = 2   # 5x5 grid of full-detail chunks
@export var load_radius_lod1: int = 4   # Outer ring of simplified chunks

# Currently loaded chunk instances: key "cx_cz" -> Node3D
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

# HTTP chunk fetcher (server mode)
var _chunk_fetcher: ChunkFetcher = null

# Prefetch tracking
var _last_prefetch_chunk: Vector2i = Vector2i(-9999, -9999)
var _prefetch_interval: float = 2.0  # seconds between prefetch calls
var _prefetch_timer: float = 0.0


func _ready() -> void:
	# Find player car
	await get_tree().process_frame
	_player = get_node_or_null("../PlayerCar")
	if _player == null:
		push_warning("WorldManager: PlayerCar not found!")

	# Setup HTTP fetcher if in server mode
	if GameManager.use_server:
		_setup_chunk_fetcher()


func _setup_chunk_fetcher() -> void:
	_chunk_fetcher = ChunkFetcher.new()
	_chunk_fetcher.server_url = GameManager.server_url
	_chunk_fetcher.name = "ChunkFetcher"
	add_child(_chunk_fetcher)
	_chunk_fetcher.chunk_ready.connect(_on_chunk_fetched)
	_chunk_fetcher.chunk_failed.connect(_on_chunk_fetch_failed)
	print("WorldManager: HTTP streaming enabled -> ", GameManager.server_url)


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

	# Process load queue (file mode only)
	if not GameManager.use_server:
		_process_load_queue()

	# Prefetch (server mode)
	if GameManager.use_server:
		_prefetch_timer -= delta
		if _prefetch_timer <= 0.0:
			_prefetch_timer = _prefetch_interval
			_send_prefetch()

	# Update HUD
	_update_hud()


func _update_chunks(center: Vector2i) -> void:
	print("WorldManager: Updating chunks around ", center, " | use_server=", GameManager.use_server, " | manifest_chunks=", GameManager.chunk_manifest.get("total_chunks", 0))
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
			var parts: PackedStringArray = key.split("_")
			var cx := int(parts[0])
			var cz := int(parts[1])
			var lod: int = needed_chunks[key]

			if GameManager.use_server:
				_request_chunk_http(key, cx, cz, lod)
			elif GameManager.has_chunk(cx, cz):
				_load_queue.append({"key": key, "cx": cx, "cz": cz, "lod": lod})
			else:
				print("WorldManager: Chunk not in manifest: ", key)


func _request_chunk_http(key: String, cx: int, cz: int, lod: int) -> void:
	"""Request a chunk via HTTP from the streaming server."""
	_loading_chunks[key] = true

	# Priority: LOD0 chunks closer to player get higher priority
	var dist := absi(cx - _last_chunk.x) + absi(cz - _last_chunk.y)
	var priority := dist + lod * 100

	_chunk_fetcher.fetch_chunk(cx, cz, lod, priority)


func _on_chunk_fetched(key: String, cx: int, cz: int, lod: int, scene: Node3D) -> void:
	"""Called when a chunk GLB is downloaded and parsed."""
	_loading_chunks.erase(key)

	# Check if still needed (player might have moved)
	var chunk_key := "%d_%d" % [cx, cz]
	if _loaded_chunks.has(chunk_key):
		scene.queue_free()
		return

	scene.name = "Chunk_" + chunk_key
	_generate_collisions(scene)
	add_child(scene)
	_loaded_chunks[chunk_key] = scene
	GameManager.loaded_chunks = _loaded_chunks.size()


func _on_chunk_fetch_failed(key: String, cx: int, cz: int, lod: int) -> void:
	_loading_chunks.erase(key)


func _send_prefetch() -> void:
	"""Send a prefetch hint to the server based on current velocity."""
	if _chunk_fetcher == null or _player == null:
		return

	var speed := GameManager.player_speed_kmh
	if speed < 5.0:
		return

	# Calculate heading from velocity
	var vel := _player.linear_velocity
	var heading_deg := rad_to_deg(atan2(vel.x, vel.z))  # 0=north, 90=east
	if heading_deg < 0:
		heading_deg += 360.0

	_chunk_fetcher.send_prefetch(
		_last_chunk.x, _last_chunk.y,
		heading_deg, speed
	)


# === File-based loading (unchanged from original) ===

func _process_load_queue() -> void:
	var loaded_this_frame := 0

	while _load_queue.size() > 0 and loaded_this_frame < _chunks_per_frame:
		var item: Dictionary = _load_queue.pop_front()
		_load_chunk_file(item["key"], item["cx"], item["cz"], item["lod"])
		loaded_this_frame += 1


func _load_chunk_file(key: String, cx: int, cz: int, lod: int) -> void:
	var file_path := GameManager.get_chunk_file(cx, cz, lod)
	if file_path == "":
		print("WorldManager: No file path for chunk ", key)
		return

	if not ResourceLoader.exists(file_path):
		print("WorldManager: Resource not found: ", file_path)
		return

	_loading_chunks[key] = true

	# Load the GLB scene
	var scene: PackedScene = load(file_path) as PackedScene
	if scene == null:
		print("WorldManager: Failed to load scene: ", file_path)
		_loading_chunks.erase(key)
		return
	print("WorldManager: Loaded chunk ", key)

	var instance := scene.instantiate()
	instance.name = "Chunk_" + key

	# Generate static collision bodies for the chunk
	_generate_collisions(instance)

	add_child(instance)
	_loaded_chunks[key] = instance
	_loading_chunks.erase(key)

	GameManager.loaded_chunks = _loaded_chunks.size()


# === Common ===

func _unload_chunk(key: String) -> void:
	if _loaded_chunks.has(key):
		var node: Node3D = _loaded_chunks[key]
		node.queue_free()
		_loaded_chunks.erase(key)
		GameManager.loaded_chunks = _loaded_chunks.size()

	# Cancel pending HTTP request if any
	if GameManager.use_server and _loading_chunks.has(key):
		var parts := key.split("_")
		if parts.size() >= 2:
			_chunk_fetcher.cancel(int(parts[0]), int(parts[1]), 0)
			_chunk_fetcher.cancel(int(parts[0]), int(parts[1]), 1)
		_loading_chunks.erase(key)


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
		var info := "Chunks: %d loaded" % _loaded_chunks.size()
		if GameManager.use_server and _chunk_fetcher:
			info += " | %d fetching | %d queued" % [
				_chunk_fetcher.get_active_count(),
				_chunk_fetcher.get_queue_size(),
			]
		chunk_label.text = info
