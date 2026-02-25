extends RefCounted
class_name GLBLoader

## Loads GLB binary data into a Godot scene tree using GLTFDocument.


static func load_from_buffer(buffer: PackedByteArray) -> Node3D:
	"""Load a GLB from raw bytes and return a Node3D scene root."""
	if buffer.size() < 12:
		push_error("GLBLoader: Buffer too small to be a valid GLB")
		return null

	var doc := GLTFDocument.new()
	var state := GLTFState.new()

	var err := doc.append_from_buffer(buffer, "", state)
	if err != OK:
		push_error("GLBLoader: Failed to parse GLB buffer: error " + str(err))
		return null

	var scene := doc.generate_scene(state)
	if scene == null:
		push_error("GLBLoader: Failed to generate scene from GLB")
		return null

	return scene
