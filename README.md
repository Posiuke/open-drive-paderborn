# Open Drive – Paderborn

Freies Fahrspiel durch Paderborn mit realen Straßen und Gebäuden aus OpenStreetMap-Daten.

![Godot 4.3](https://img.shields.io/badge/Godot-4.3-blue?logo=godotengine)
![Python 3.12](https://img.shields.io/badge/Python-3.12-yellow?logo=python)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

## Überblick

Eine Python-Pipeline lädt reale Geodaten für Paderborn herunter, generiert daraus 3D-Meshes (Straßen, Gebäude, Terrain, Gewässer) und exportiert sie als glTF-Chunks. Das Godot-4-Projekt lädt diese Chunks dynamisch und bietet Fahrzeugphysik, Kamerasteuerung und ein HUD.

```
Python Data Pipeline  ──▶  glTF Chunks (.glb)  ──▶  Godot 4 Spiel
```

### Eckdaten

| | |
|---|---|
| Stadtgebiet | ~9 km × 7,8 km (51.685°–51.755°N, 8.690°–8.820°E) |
| Welt-Ursprung | Paderborner Dom (51.7189°N, 8.7544°E) |
| Gebäude | ~38.600 aus OSM |
| Straßensegmente | ~7.200 |
| Chunks | 1.116 à 256 m × 256 m, je 2 LOD-Stufen |
| Terrain | SRTM-Höhendaten, 91–262 m ü. NN |

## Steuerung

| Taste | Aktion |
|-------|--------|
| W / ↑ | Gas |
| S / ↓ | Bremse / Rückwärts |
| A / ← | Lenken links |
| D / → | Lenken rechts |
| Leertaste | Bremse |
| Shift | Handbremse |
| V | Kamera wechseln (3rd / 1st Person) |
| R | Auto zurücksetzen |

## Projektstruktur

```
open-drive-paderborn/
├── pipeline/                      # Python-Datenpipeline
│   ├── config.py                  # Paderborn-Koordinaten, Konstanten
│   ├── 01_download_osm.py        # OSM-Daten (Straßen, Gebäude, Landnutzung)
│   ├── 02_download_terrain.py    # SRTM-Höhendaten
│   ├── 03_process_roads.py       # Straßen → 3D-Meshes
│   ├── 04_process_buildings.py   # Gebäude → extrudierte Meshes
│   ├── 05_process_terrain.py     # Terrain-Heightmap → Mesh
│   ├── 06_process_landuse.py     # Parks, Wasser, Flächen
│   ├── 07_chunk_and_export.py    # Aufteilen in Chunks, GLB-Export
│   ├── run_pipeline.sh           # Alle Schritte nacheinander
│   ├── requirements.txt
│   └── utils/
│       ├── geo.py                # WGS84 → UTM → Godot-Koordinaten
│       ├── mesh_builder.py       # Mesh-Generierung
│       ├── height_sampler.py     # SRTM-Höhenabfrage
│       └── chunk_manager.py      # Räumliche Chunk-Zuordnung
│
├── godot/                         # Godot 4 Projekt
│   ├── project.godot
│   ├── scenes/
│   │   ├── main.tscn             # Hauptszene (Welt, Licht, Fog, HUD)
│   │   └── vehicle/
│   │       └── player_car.tscn   # VehicleBody3D, 1400 kg, Hinterradantrieb
│   ├── scripts/
│   │   ├── autoload/game_manager.gd    # Chunk-Manifest, globaler State
│   │   ├── world/world_manager.gd      # Dynamisches Chunk-Streaming
│   │   ├── vehicle/car_controller.gd   # Lenkung, Gas, Bremse, Rückwärtsgang
│   │   ├── camera/camera_rig.gd        # 3rd-Person (SpringArm) + 1st-Person
│   │   └── ui/                         # HUD, Tacho, Minimap
│   └── assets/
│       ├── chunks/               # Generierte GLB-Dateien (nicht in Git)
│       ├── chunk_manifest.json   # Chunk-Index für den WorldManager
│       └── shaders/              # Asphalt, Fassaden, Terrain, Wasser
│
└── data/                          # Cache & Export (nicht in Git)
```

## Voraussetzungen

- **Python 3.10+** (Pipeline)
- **Godot 4.3+** mit Forward+-Renderer (Spiel)
- ~500 MB freier Speicher für Pipeline-Cache und exportierte Chunks

## Setup & Pipeline ausführen

```bash
# 1. Repository klonen
git clone git@github.com:Posiuke/open-drive-paderborn.git
cd open-drive-paderborn

# 2. Python-Umgebung einrichten
python3 -m venv venv
source venv/bin/activate
pip install -r pipeline/requirements.txt

# 3. Pipeline ausführen (lädt OSM + SRTM, generiert alle Chunks)
cd pipeline
bash run_pipeline.sh
```

Die Pipeline durchläuft 7 Schritte:

1. OSM-Daten herunterladen (Straßen, Gebäude, Landnutzung)
2. SRTM-Höhendaten herunterladen
3. Straßen zu 3D-Meshes verarbeiten
4. Gebäude extrudieren
5. Terrain-Meshes generieren
6. Landnutzung und Gewässer verarbeiten
7. In 256-m-Chunks aufteilen und als GLB exportieren

Nach Abschluss liegen die Chunks unter `godot/assets/chunks/`.

## Spiel starten

1. Godot 4.3 öffnen
2. Projekt importieren: `godot/project.godot`
3. Play drücken (F5)

Das Auto startet am Paderborner Dom. Der WorldManager lädt automatisch die umliegenden Chunks.

## Technische Details

### Chunk-Streaming

Der `WorldManager` lädt Chunks basierend auf der Spielerposition:
- **LOD0** (volle Details): 5×5 Grid um den Spieler (~640 m Radius)
- **LOD1** (vereinfacht): äußerer Ring (~1 km Radius)
- Chunks werden asynchron geladen/entladen, max. 2 pro Frame

### Fahrzeugphysik

- `VehicleBody3D` mit 4× `VehicleWheel3D`
- 1.400 kg Limousine, Hinterradantrieb
- Geschwindigkeitsabhängige Lenkung (reduziert ab 30 km/h)
- Federung und Reibung für 30–80 km/h Stadtfahrt abgestimmt
- 120 Hz Physik-Tickrate

### Shader

- **Asphalt**: Noise-Textur mit Fahrbahnmarkierungen
- **Gebäudefassaden**: Prozedurale Fenster mit zufälliger Beleuchtung
- **Terrain**: Multi-Oktav-Noise für Gras/Erde-Variation
- **Wasser**: Animierte Wellen mit Reflexionen (Pader & Paderquellgebiet)

### Paderborn-Spezifika

- **Dom** (33 m) als höchstes Gebäude der Altstadt
- **Paderquellgebiet** mit Water-Shader
- **Universität** im Süden (Warburger Straße)
- **Schloss Neuhaus** im Nordosten
- Terrain: relativ flach (94–150 m im Stadtgebiet), Padertal

## Windows-Export

1. In Godot: Projekt → Export → Preset hinzufügen → Windows Desktop
2. Export-Template herunterladen (falls nötig)
3. Als `.exe` exportieren

## Lizenz

MIT
