extends Node

## Global game state manager (Autoload singleton).
## Supports both file-based (offline) and server-based (streaming) modes.

# Game state
var player_car: VehicleBody3D
var player_speed_kmh: float = 0.0
var loaded_chunks: int = 0
var total_chunks: int = 0

# Chunk manifest data (file mode only)
var chunk_manifest: Dictionary = {}
var chunks_path: String = "res://assets/chunks/"

# Origin: Paderborner Dom in local coordinates = (0, 0, 0)
const CHUNK_SIZE: float = 256.0
const ORIGIN_LAT: float = 51.7189
const ORIGIN_LON: float = 8.7544

# === Server Mode ===
## Set to true to load chunks from the streaming server instead of local files.
var use_server: bool = false
var server_url: String = "http://127.0.0.1:8090"

# Global UTM origin tracking for floating origin
# These are the UTM easting/northing of the current Godot (0,0,0) point.
# Initially set to the Dom origin. Updated by OriginManager during rebase.
var origin_utm_e: float = 0.0
var origin_utm_n: float = 0.0

# Precalculated Dom UTM (filled on ready)
const _DOM_UTM_E: float = 488599.0  # Approximate, overridden at runtime
const _DOM_UTM_N: float = 5731013.0


func _ready() -> void:
	# Check for server mode via command line args or config
	_check_server_mode()

	if use_server:
		print("GameManager ready. Server mode: ", server_url)
		origin_utm_e = _DOM_UTM_E
		origin_utm_n = _DOM_UTM_N
	else:
		_load_manifest()
		print("GameManager ready. File mode. Chunks: ", chunk_manifest.get("total_chunks", 0))


func _check_server_mode() -> void:
	# Check command line arguments for --server or --server-url
	var args := OS.get_cmdline_args()
	for i in range(args.size()):
		if args[i] == "--server":
			use_server = true
		elif args[i] == "--server-url" and i + 1 < args.size():
			use_server = true
			server_url = args[i + 1]

	# Also check for a config file
	var config_path := "res://server_config.json"
	if FileAccess.file_exists(config_path):
		var file := FileAccess.open(config_path, FileAccess.READ)
		var json := JSON.new()
		if json.parse(file.get_as_text()) == OK:
			var cfg: Dictionary = json.data
			if cfg.get("use_server", false):
				use_server = true
				server_url = cfg.get("server_url", server_url)


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
	# In server mode, all chunks are potentially available
	if use_server:
		return true
	var key := "%d_%d" % [cx, cz]
	return chunk_manifest.has("chunks") and chunk_manifest["chunks"].has(key)


func world_to_chunk(pos: Vector3) -> Vector2i:
	var cx := int(floor(pos.x / CHUNK_SIZE))
	var cz := int(floor(pos.z / CHUNK_SIZE))
	return Vector2i(cx, cz)
