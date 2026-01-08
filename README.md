# Magic Agent

Natural-language editing CLI for DaVinci Resolve. Convert plain English commands into Resolve operations.

```
"set opacity to 50% on all clips in track 1"  →  Executes in Resolve
```

## Requirements

- macOS (tested on macOS 14+)
- DaVinci Resolve Studio 20.0+ (scripting requires Studio version)
- Python 3.9+
- Rust 1.70+ (for building)
- Anthropic API key (or OpenAI/OpenRouter)

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
[llm]
provider = "anthropic"  # anthropic | openai | openrouter
# api_key = "sk-ant-..."  # Or use environment variable

[resolve]
# python_path = "/opt/homebrew/bin/python3"  # Auto-detected if not set

[output]
default_format = "json"  # json | pretty
```

### Environment Variables

API keys can be set via environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export OPENAI_API_KEY="sk-..."
# or
export OPENROUTER_API_KEY="sk-or-..."
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
✔ api_key: Configured for anthropic
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

### Generate a plan

```bash
magic-agent plan "set opacity to 50% on all clips in track 1" --pretty
```

Output:
```
Execution Plan (v1.0)

Target Project: My Project
Target Timeline: Timeline 1

Preconditions:
  - ProjectOpen
  - TimelineActive

Operations:
  1. set_clip_property
      {
        "selector": { "track": 1, "all": true },
        "properties": { "Opacity": 50.0 }
      }
```

### Execute changes

```bash
# Generate and execute
magic-agent apply "set opacity to 50% on all clips" --yes

# Dry run (validate only)
magic-agent apply "set opacity to 50%" --dry-run

# Execute from saved plan
magic-agent plan "add a red marker at frame 100" > plan.json
magic-agent apply --plan plan.json --yes
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
magic-agent apply "add beat markers on audio track 1" --yes

# Add markers on audio track 2
magic-agent apply "add beat markers on audio track 2" --yes

# Analyze video track with embedded audio
magic-agent apply "detect beats on video track 1" --yes
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

If you request an unsupported operation, the tool will explain what's not possible.

## Examples

```bash
# Batch property changes
magic-agent apply "set opacity to 80% and zoom to 110% on all clips in video track 1" --yes

# Add markers
magic-agent apply "add a red marker named 'Review' at frame 500 with note 'check audio'" --yes

# Prepare render
magic-agent apply "add a render job for mp4 h265 to ~/Renders/final" --yes

# Export timeline
magic-agent apply "export the timeline as fcpxml to ~/exports/project.fcpxml" --yes

# Track management
magic-agent apply "add a new video track and name it 'B-Roll'" --yes
magic-agent apply "lock video track 2" --yes

# Color grading
magic-agent apply "apply the LUT at /path/to/my.cube to the first clip" --yes
magic-agent apply "copy grades from clip 0 to all other clips on track 1" --yes
magic-agent apply "reset grades on the first clip" --yes

# Color groups
magic-agent apply "create a color group called 'Hero Shots'" --yes
magic-agent apply "assign the first clip to the 'Hero Shots' color group" --yes

# Flags
magic-agent apply "add a red flag to all clips on track 1" --yes
magic-agent apply "clear all flags from the first clip" --yes

# Media pool
magic-agent apply "create a folder called 'B-Roll' in the media pool" --yes
magic-agent apply "move clips 'clip1.mov' and 'clip2.mov' to the 'B-Roll' folder" --yes

# Render presets
magic-agent apply "list available render presets" --yes
magic-agent apply "load the 'YouTube 1080p' render preset" --yes
```

## JSON Output

All commands output JSON by default (omit `--pretty`):

```bash
magic-agent status | jq '.timeline.name'
# "Timeline 1"

magic-agent plan "add marker at frame 100" | jq '.operations'
# [{"op": "add_marker", "params": {"frame": 100, "color": "Blue"}}]
```

## Troubleshooting

### "DaVinci Resolve is not running"
Start Resolve before running commands. The scripting API requires Resolve to be open.

### "API key not configured"
Set your API key in config or environment:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### "Bridge script not found"
When running from source, use `cargo run` or ensure the `python/` directory is next to the binary.

### Python errors
Ensure Python 3.9+ is installed and the Resolve scripting modules are accessible:
```bash
python3 -c "import DaVinciResolveScript"
```

## License

MIT
