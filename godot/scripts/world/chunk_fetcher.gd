extends Node
class_name ChunkFetcher

## HTTP-based chunk fetcher with concurrent request pool and priority queue.
## Fetches GLB chunks from the Python streaming server.

signal chunk_ready(key: String, cx: int, cz: int, lod: int, scene: Node3D)
signal chunk_failed(key: String, cx: int, cz: int, lod: int)

## Server configuration
@export var server_url: String = "http://127.0.0.1:8090"

## Maximum concurrent HTTP requests
@export var max_concurrent: int = 6

## Request timeout in seconds
@export var request_timeout: float = 30.0

# Pool of HTTPRequest nodes
var _http_pool: Array[HTTPRequest] = []
var _active_requests: Dictionary = {}  # HTTPRequest -> request_info

# Priority queue: sorted by priority (lower = higher priority)
var _request_queue: Array = []  # [{key, cx, cz, lod, priority}]
var _pending_keys: Dictionary = {}  # key -> true (dedup)


func _ready() -> void:
	# Create HTTP request pool
	for i in range(max_concurrent):
		var http := HTTPRequest.new()
		http.timeout = request_timeout
		http.use_threads = true
		add_child(http)
		http.request_completed.connect(_on_request_completed.bind(http))
		_http_pool.append(http)


func _process(_delta: float) -> void:
	# Fill available pool slots from queue
	_dispatch_queued()


## Queue a chunk for fetching. Lower priority values are fetched first.
func fetch_chunk(cx: int, cz: int, lod: int, priority: int = 10) -> void:
	var key := "%d_%d_%d" % [cx, cz, lod]

	# Skip if already pending or active
	if _pending_keys.has(key):
		return
	for http in _active_requests:
		var info: Dictionary = _active_requests[http]
		if info["key"] == key:
			return

	_pending_keys[key] = true
	_request_queue.append({
		"key": key,
		"cx": cx,
		"cz": cz,
		"lod": lod,
		"priority": priority,
	})

	# Sort by priority (lower first)
	_request_queue.sort_custom(func(a, b): return a["priority"] < b["priority"])


## Cancel a pending or active request.
func cancel(cx: int, cz: int, lod: int) -> void:
	var key := "%d_%d_%d" % [cx, cz, lod]
	_pending_keys.erase(key)

	# Remove from queue
	for i in range(_request_queue.size() - 1, -1, -1):
		if _request_queue[i]["key"] == key:
			_request_queue.remove_at(i)
			break

	# Cancel active request
	for http in _active_requests:
		var info: Dictionary = _active_requests[http]
		if info["key"] == key:
			http.cancel_request()
			_active_requests.erase(http)
			break


## Cancel all pending and active requests.
func cancel_all() -> void:
	_request_queue.clear()
	_pending_keys.clear()
	for http in _active_requests:
		http.cancel_request()
	_active_requests.clear()


## Send a prefetch hint to the server.
func send_prefetch(player_cx: int, player_cz: int, heading_deg: float, speed_kmh: float) -> void:
	var http := HTTPRequest.new()
	http.timeout = 5.0
	add_child(http)

	var url := server_url + "/api/v1/prefetch"
	var body := JSON.stringify({
		"player_cx": player_cx,
		"player_cz": player_cz,
		"heading_deg": heading_deg,
		"speed_kmh": speed_kmh,
	})

	var headers := ["Content-Type: application/json"]
	http.request_completed.connect(func(_result, _code, _headers, _body):
		http.queue_free()
	)
	http.request(url, headers, HTTPClient.METHOD_POST, body)


## Check how many requests are currently in-flight.
func get_active_count() -> int:
	return _active_requests.size()


## Check how many requests are queued.
func get_queue_size() -> int:
	return _request_queue.size()


func _dispatch_queued() -> void:
	if _request_queue.is_empty():
		return

	# Find idle HTTP nodes
	for http in _http_pool:
		if _request_queue.is_empty():
			break
		if _active_requests.has(http):
			continue

		var item: Dictionary = _request_queue.pop_front()
		var key: String = item["key"]

		# Double check it wasn't cancelled
		if not _pending_keys.has(key):
			continue

		_pending_keys.erase(key)

		var url := "%s/api/v1/chunk/%d/%d/%d" % [
			server_url, item["cx"], item["cz"], item["lod"]
		]

		_active_requests[http] = item
		var err := http.request(url)
		if err != OK:
			_active_requests.erase(http)
			chunk_failed.emit(key, item["cx"], item["cz"], item["lod"])


func _on_request_completed(result: int, response_code: int,
		headers: PackedStringArray, body: PackedByteArray,
		http: HTTPRequest) -> void:

	if not _active_requests.has(http):
		return

	var info: Dictionary = _active_requests[http]
	_active_requests.erase(http)

	var key: String = info["key"]
	var cx: int = info["cx"]
	var cz: int = info["cz"]
	var lod: int = info["lod"]

	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		if response_code != 0:
			push_warning("ChunkFetcher: Failed to fetch %s (HTTP %d)" % [key, response_code])
		chunk_failed.emit(key, cx, cz, lod)
		return

	# Parse GLB from response body
	var scene := GLBLoader.load_from_buffer(body)
	if scene == null:
		push_warning("ChunkFetcher: Failed to parse GLB for " + key)
		chunk_failed.emit(key, cx, cz, lod)
		return

	chunk_ready.emit(key, cx, cz, lod, scene)
