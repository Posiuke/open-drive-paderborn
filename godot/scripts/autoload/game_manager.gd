extends Node

## Global game state manager (Autoload singleton).

# Game state
var player_car: VehicleBody3D
var player_speed_kmh: float = 0.0
var loaded_chunks: int = 0
var total_chunks: int = 0

# Chunk manifest data
var chunk_manifest: Dictionary = {}
var chunks_path: String = "res://assets/chunks/"

# Origin: Paderborner Dom in local coordinates = (0, 0, 0)
const CHUNK_SIZE: float = 256.0
const ORIGIN_LAT: float = 51.7189
const ORIGIN_LON: float = 8.7544


func _ready() -> void:
	# Load chunk manifest
	_load_manifest()
	print("GameManager ready. Chunks: ", chunk_manifest.get("total_chunks", 0))


func _load_manifest() -> void:
	var manifest_path := "res://assets/chunk_manifest.json"
	if not FileAccess.file_exists(manifest_path):
		push_warning("Chunk manifest not found: " + manifest_path)
		return

	var file := FileAccess.open(manifest_path, FileAccess.READ)
	var json := JSON.new()
	var err := json.parse(file.get_as_text())
	if err != OK:
		push_error("Failed to parse chunk manifest: " + json.get_error_message())
		return

	chunk_manifest = json.data
	total_chunks = chunk_manifest.get("total_chunks", 0)
	print("Loaded manifest: ", total_chunks, " chunks")


func get_chunk_file(cx: int, cz: int, lod: int) -> String:
	var key := "%d_%d" % [cx, cz]
	if chunk_manifest.has("chunks") and chunk_manifest["chunks"].has(key):
		var chunk_data: Dictionary = chunk_manifest["chunks"][key]
		var filename: String
		if lod == 0:
			filename = chunk_data.get("lod0", "")
		else:
			filename = chunk_data.get("lod1", "")
		if filename != "":
			return chunks_path + filename
	return ""


func has_chunk(cx: int, cz: int) -> bool:
	var key := "%d_%d" % [cx, cz]
	return chunk_manifest.has("chunks") and chunk_manifest["chunks"].has(key)


func world_to_chunk(pos: Vector3) -> Vector2i:
	var cx := int(floor(pos.x / CHUNK_SIZE))
	var cz := int(floor(pos.z / CHUNK_SIZE))
	return Vector2i(cx, cz)
