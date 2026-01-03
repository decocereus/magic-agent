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

### Build from source

```bash
git clone https://github.com/amartyasingh/magic-agent.git
cd magic-agent
cargo build --release
```

The binary will be at `target/release/magic-agent`.

### Install to PATH

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

## Supported Operations

### Media
- `import_media` - Import files into media pool
- `append_to_timeline` - Add clips to end of timeline
- `create_timeline` - Create new timeline

### Clip Properties
- `set_clip_property` - Modify opacity, zoom, pan, tilt, rotation, crop, flip

### Markers
- `add_marker` - Add marker with color, name, note
- `delete_marker` - Remove markers by frame or color

### Tracks
- `add_track` - Add video/audio/subtitle track
- `set_track_name` - Rename track
- `enable_track` - Enable/disable track
- `lock_track` - Lock/unlock track

### Render
- `add_render_job` - Configure render settings
- `start_render` - Begin rendering

### Timeline
- `set_timeline` - Switch active timeline
- `duplicate_timeline` - Copy timeline
- `export_timeline` - Export as AAF/XML/EDL/FCPXML

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
