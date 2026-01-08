# Magic Agent

Direct CLI for DaVinci Resolve scripting operations. Invoke Resolve tools from the terminal or automations.

## Requirements

- macOS (tested on macOS 14+)
- DaVinci Resolve Studio 20.0+ (scripting requires Studio version)
- Python 3.9+
- Rust 1.70+ (for building)

## Installation

### Homebrew (recommended)

```bash
brew tap decocereus/magic-agent
brew install magic-agent
```

### Build from source

```bash
git clone https://github.com/decocereus/magic-agent.git
cd magic-agent
cargo build --release
```

The binary will be at `target/release/magic-agent`.

### Cargo (from git)

```bash
cargo install --git https://github.com/decocereus/magic-agent.git
```

### Install to Path
```bash
cargo install --path .
```

## Configuration

Create `~/.config/magic-agent/config.toml`:

```toml
[resolve]
# python_path = "/opt/homebrew/bin/python3"  # Auto-detected if not set

[output]
default_format = "json"  # json | pretty
```

## Usage

### Check setup

```bash
magic-agent doctor --pretty
```

Output:
```
Magic Agent Doctor

✔ python: Python 3.12.0
    Path: /opt/homebrew/bin/python3
✔ bridge_script: Found
✔ resolve: DaVinci Resolve Studio 20.0.0.49
```

### View current state

```bash
magic-agent status --pretty
```

Output:
```
Resolve Status

Product: DaVinci Resolve Studio 20.0.0.49

Project: My Project
Timelines: 2

Active Timeline: Timeline 1
Resolution: 1920x1080 @ 29.97 fps
Duration: 804 frames (108000 - 108804)

Video Tracks:
  Track 1: Video 1 (3 clips)

Audio Tracks:
  Track 1: Audio 1 (2 clips)

Media Pool: 5 clips, 2 folders
```

### List supported operations

```bash
magic-agent ops list
```

### Run typed commands

```bash
# Add a marker
magic-agent marker add 100 --color Red --name "Review"

# Treat frame as relative to timeline start (useful if the timeline starts at 01:00:00:00)
magic-agent marker add 0 --relative --color Blue --name "Start"

# Enable a track
magic-agent track enable --type video --index 2 --enable

# Set clip properties
magic-agent clip set-property --track 1 --index 0 --set Opacity=50 --set ZoomX=1.1

# Import media
magic-agent media import ~/media/clip1.mov ~/media/clip2.mov

# Export timeline
magic-agent timeline export --path ~/exports/project.fcpxml --format fcpxml
```

### Run any operation (raw JSON)

```bash
magic-agent op add_marker --params '{"frame":100,"color":"Red","name":"Review"}'
magic-agent op add_marker --params '{"frame":0,"relative":true,"color":"Blue","name":"Start"}'
```

### Batch operations

```bash
cat > batch.json <<'JSON'
[
  { "op": "add_marker", "params": { "frame": 100, "color": "Red" } },
  { "op": "set_current_timecode", "params": { "timecode": "00:00:10:00" } }
]
JSON

magic-agent batch --file batch.json
```

## Supported Operations (~85 operations)

### Media
- `import_media` - Import files into media pool
- `append_to_timeline` - Add clips to end of timeline
- `create_timeline` - Create new timeline

### Clip Properties
- `set_clip_property` - Modify opacity, zoom, pan, tilt, rotation, crop, flip
- `set_clip_enabled` - Enable/disable clip
- `set_clip_color` - Set clip color label

### Markers
- `add_marker` - Add marker with color, name, note
- `delete_marker` - Remove markers by frame or color

### Tracks
- `add_track` - Add video/audio/subtitle track
- `delete_track` - Remove a track
- `set_track_name` - Rename track
- `enable_track` - Enable/disable track
- `lock_track` - Lock/unlock track

### Fusion & Compositions
- `insert_fusion_composition` - Insert empty Fusion comp at playhead
- `create_fusion_clip` - Convert clips to Fusion clip
- `add_fusion_comp_to_clip` - Add Fusion comp to existing clip
- `create_compound_clip` - Combine clips into compound clip

### Generators & Titles
- `insert_generator` - Insert generator (solid, gradient, etc.)
- `insert_title` - Insert title (standard or Fusion)

### AI/Processing
- `stabilize_clip` - Apply stabilization
- `smart_reframe` - Auto-reframe for different aspect ratios
- `create_magic_mask` - Create AI-powered magic mask
- `detect_scene_cuts` - Auto-detect scene changes

### Clip Management
- `delete_clips` - Delete clips from timeline
- `set_clips_linked` - Link/unlink clips

### Color Grading
- `apply_lut` - Apply LUT to clip node
- `get_lut` - Get LUT path from clip
- `set_cdl` - Set CDL values (slope, offset, power, saturation)
- `copy_grades` - Copy grades between clips
- `reset_grades` - Reset all grades on clip
- `apply_grade_from_drx` - Apply grade from DRX file

### Color Versions
- `add_color_version` - Create new color version
- `load_color_version` - Switch to a color version
- `get_color_versions` - List versions
- `delete_color_version` - Remove a version

### Color Groups
- `create_color_group` - Create a color group
- `get_color_groups` - List all color groups
- `assign_to_color_group` - Assign clip to group
- `remove_from_color_group` - Remove clip from group
- `delete_color_group` - Delete a group

### Media Pool
- `create_media_pool_folder` - Create folder
- `set_current_media_pool_folder` - Change current folder
- `move_media_pool_clips` - Move clips between folders
- `delete_media_pool_clips` - Delete clips from pool
- `delete_media_pool_folders` - Delete folders
- `set_clip_metadata` / `get_clip_metadata` - Manage clip metadata
- `relink_clips` - Relink offline clips

### Flags
- `add_flag` - Add flag to clip
- `get_flags` - Get flags from clip
- `clear_flags` - Clear flags from clip

### Takes
- `add_take` - Add take to timeline clip
- `select_take` - Select a take
- `get_takes` - List takes
- `finalize_take` - Finalize take selection
- `delete_take` - Remove a take

### Render (Basic & Advanced)
- `add_render_job` - Configure render job
- `start_render` - Begin rendering
- `set_render_settings` - Detailed render settings
- `get_render_formats` / `get_render_codecs` - Query available formats
- `set_render_format_and_codec` - Set format/codec
- `get_render_presets` / `load_render_preset` / `save_render_preset` / `delete_render_preset` - Manage presets
- `get_render_jobs` / `delete_render_job` / `delete_all_render_jobs` - Manage job queue
- `get_render_job_status` - Check job progress

### Timeline
- `set_timeline` - Switch active timeline
- `duplicate_timeline` - Copy timeline
- `export_timeline` - Export as AAF/XML/EDL/FCPXML
- `import_timeline_from_file` - Import from AAF/EDL/XML/FCPXML

### Stills & Gallery
- `grab_still` - Capture still from current frame
- `export_still` - Export frame as image
- `get_gallery_albums` - List gallery albums

### Project & Timeline Settings
- `save_project` - Save project
- `export_project` - Export as .drp file
- `get_project_setting` / `set_project_setting` - Manage project settings
- `get_timeline_setting` / `set_timeline_setting` - Manage timeline settings

### Navigation
- `set_current_timecode` / `get_current_timecode` - Control playhead
- `open_page` / `get_current_page` - Switch Resolve pages

### Cache & Keyframes
- `set_clip_cache_mode` / `get_clip_cache_mode` - Control render cache
- `set_keyframe_mode` / `get_keyframe_mode` - Control keyframe mode
- `refresh_lut_list` - Refresh LUT list

### Audio
- `create_subtitles_from_audio` - Auto-generate subtitles
- `detect_beats` - Analyze audio and add markers at downbeats (bar starts)

#### Beat Detection

Automatically detect musical beats in audio and add clip markers for editing to music. Uses BeatNet neural network for accurate downbeat detection.

**Requirements:**

1. **Python 3.10** (recommended for compatibility):
   ```bash
   brew install python@3.10
   ```

2. **Create a virtual environment:**
   ```bash
   /opt/homebrew/opt/python@3.10/bin/python3.10 -m venv ~/.magic-agent-venv
   source ~/.magic-agent-venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install "numpy<2.0" cython setuptools wheel
   pip install git+https://github.com/CPJKU/madmom.git
   pip install BeatNet librosa pyaudio
   ```

4. **Configure magic-agent** to use the venv (in `~/.config/magic-agent/config.toml`):
   ```toml
   [resolve]
   python_path = "~/.magic-agent-venv/bin/python"
   ```

**Marker Colors:**
| Type | Color | Description |
|------|-------|-------------|
| Downbeat | Red | First beat of each bar |
| Beat | Blue | Regular beats (if enabled) |

**Examples:**
```bash
# Add downbeat markers on audio track 1
magic-agent op detect_beats --params '{"track":1,"track_type":"audio","mark_downbeats":true}'

# Add markers on audio track 2
magic-agent op detect_beats --params '{"track":2,"track_type":"audio","mark_downbeats":true}'

# Analyze video track with embedded audio
magic-agent op detect_beats --params '{"track":1,"track_type":"video","mark_downbeats":true}'
```

**Note:** Without BeatNet installed, the tool falls back to librosa which provides less accurate beat detection.

## Limitations

The Resolve scripting API does not support:
- Moving clips on timeline (append only)
- Inserting clips at specific timecodes
- Transitions
- Keyframe animation
- Audio automation
- Trimming/slipping/sliding clips

If you run an unsupported operation, the tool will explain what's not possible.

## Examples

```bash
# Batch property changes
magic-agent clip set-property --track 1 --all --set Opacity=80 --set ZoomX=1.1 --set ZoomY=1.1

# Add markers
magic-agent marker add 500 --color Red --name "Review" --note "check audio"
magic-agent op add_clip_marker --params '{"selector":{"track":1,"index":0},"frame":0,"color":"Blue","name":"Clip start"}'

# Prepare render
magic-agent render add-job --format mp4 --codec H265 --path ~/Renders/final

# Export timeline
magic-agent timeline export --path ~/exports/project.fcpxml --format fcpxml

# Track management
magic-agent track add --type video
magic-agent track name --type video --index 2 --name "B-Roll"
magic-agent track lock --type video --index 2 --lock

# Color grading
magic-agent op apply_lut --params '{"selector":{"track":1,"index":0},"lut_path":"/path/to/my.cube"}'
magic-agent op copy_grades --params '{"source":{"track":1,"index":0},"targets":{"track":1,"all":true}}'
magic-agent op reset_grades --params '{"selector":{"track":1,"index":0}}'

# Color groups
magic-agent op create_color_group --params '{"name":"Hero Shots"}'
magic-agent op assign_to_color_group --params '{"selector":{"track":1,"index":0},"group":"Hero Shots"}'

# Flags
magic-agent op add_flag --params '{"selector":{"track":1,"all":true},"color":"Red"}'
magic-agent op clear_flags --params '{"selector":{"track":1,"index":0},"color":"All"}'

# Media pool
magic-agent op create_media_pool_folder --params '{"name":"B-Roll"}'
magic-agent op move_media_pool_clips --params '{"clips":["clip1.mov","clip2.mov"],"target_folder":"B-Roll"}'

# Render presets
magic-agent op get_render_presets
magic-agent op load_render_preset --params '{"name":"YouTube 1080p"}'
```

## JSON Output

All commands output JSON by default (omit `--pretty`):

```bash
magic-agent status | jq '.timeline.name'
# "Timeline 1"

magic-agent op add_marker --params '{"frame":100,"color":"Blue"}' | jq '.frame'
# 100
```

## LLM Integration

Use `docs/ops.json` as a machine-readable catalog of operations and params.

Key rules:
- Clip selectors require exactly one of `index`, `name`, or `all`.
- Track indices are 1-based; clip indices are 0-based.
- `track_type` is optional in most clip selectors (defaults to `video`).
- `clip set-property --set KEY=VALUE` coerces bool/number/JSON when possible.
- Batch execution continues on errors; inspect `results[*].status`.

Common patterns:
```bash
# Discover operations
magic-agent ops list

# Print machine-readable schema
magic-agent ops schema

# Pretty schema output (global flag)
magic-agent --pretty ops schema

# Schema output format override
magic-agent ops schema --format raw

# Execute any op (string params)
magic-agent op add_marker --params '{"frame":100,"color":"Red"}'

# Execute any op (file or stdin)
magic-agent op add_marker --params-file params.json
cat params.json | magic-agent op add_marker --params-stdin

# Batch (array or wrapper format)
magic-agent batch --stdin <<'JSON'
[
  { "op": "add_marker", "params": { "frame": 100, "color": "Red" } },
  { "op": "set_current_timecode", "params": { "timecode": "00:00:10:00" } }
]
JSON
```

## Troubleshooting

### "DaVinci Resolve is not running"
Start Resolve before running commands. The scripting API requires Resolve to be open.

### "Bridge script not found"
When running from source, use `cargo run` or ensure the `python/` directory is next to the binary.

### Python errors
Ensure Python 3.9+ is installed and the Resolve scripting modules are accessible:
```bash
python3 -c "import DaVinciResolveScript"
```

## License

MIT
