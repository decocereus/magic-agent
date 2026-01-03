# Magic Agent: Natural-Language Editing CLI for DaVinci Resolve

## Overview

A macOS CLI tool that converts natural language editing requests into structured execution plans, then applies them to DaVinci Resolve via its Python scripting API.

```
User: "set opacity to 50% on all clips in track 1"
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│                      magic-agent CLI                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ Command  │  │   LLM    │  │  Plan    │  │   Resolve   │  │
│  │ Parser   │→ │Interpreter│→│ Executor │→ │   Bridge    │  │
│  │ (clap)   │  │ (Claude) │  │          │  │  (Python)   │  │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
                                        ┌───────────────────┐
                                        │  DaVinci Resolve  │
                                        │   Studio 20.0+    │
                                        └───────────────────┘
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Rust | Fast, single binary, excellent CLI ergonomics |
| LLM | Claude Sonnet 4 (Anthropic API) | Best structured output compliance |
| Config | `~/.config/magic-agent/config.toml` | Standard XDG-style config |
| Python | Bundle scripts, invoke system Python | Resolve requires Python; avoids embedding complexity |
| Output | JSON default, `--pretty` for human | Machine-parseable by default |
| Confirmation | Require `--yes` for apply | Prevent accidental execution |
| Rollback | Deferred (v2) | Focus on core functionality first |
| Fusion/Animation | Deferred (v2) | Adds significant complexity |

---

## Configuration

### File Location
```
~/.config/magic-agent/config.toml
```

### Format
```toml
[llm]
provider = "anthropic"              # anthropic | openai | openrouter
api_key = "sk-ant-..."              # API key for provider
model = "claude-sonnet-4-20250514"  # Optional, defaults to Sonnet 4

[resolve]
python_path = "/opt/homebrew/bin/python3"  # Optional, auto-detects if not set

[output]
default_format = "json"  # json | pretty
```

### Environment Variable Fallback
- `ANTHROPIC_API_KEY` - Used if `llm.api_key` not set
- `OPENAI_API_KEY` - Used for OpenAI provider
- `OPENROUTER_API_KEY` - Used for OpenRouter provider

---

## CLI Interface

### Commands

```bash
# Diagnostics
magic-agent doctor                    # Check Resolve, Python, API key
magic-agent status                    # Show current project/timeline (JSON)
magic-agent status --pretty           # Human-readable status

# Planning (read-only, no changes made)
magic-agent plan "your request"       # Generate plan JSON
magic-agent plan --pretty "..."       # Human-readable plan

# Execution
magic-agent apply "request" --yes              # Generate + execute
magic-agent apply --plan plan.json --yes       # Execute saved plan
magic-agent apply --dry-run "..."              # Validate only (no --yes needed)

# Help
magic-agent --help
magic-agent <command> --help
```

### Global Flags

| Flag | Description |
|------|-------------|
| `--pretty` | Human-readable output instead of JSON |
| `--config <path>` | Use alternate config file |
| `--verbose` | Enable debug logging |

### Command-Specific Flags

| Command | Flag | Description |
|---------|------|-------------|
| `apply` | `--yes` | Required to execute (safety) |
| `apply` | `--dry-run` | Validate plan without executing |
| `apply` | `--plan <file>` | Execute from saved plan file |

---

## Project Structure

```
magic-agent/
├── Cargo.toml
├── Cargo.lock
├── PLAN.md                         # This file
├── README.md                       # User documentation
├── src/
│   ├── main.rs                     # Entry point, CLI definition
│   ├── cli/
│   │   ├── mod.rs
│   │   └── commands.rs             # Command implementations
│   ├── config.rs                   # Config loading
│   ├── interpreter/
│   │   ├── mod.rs
│   │   ├── client.rs               # Claude API client
│   │   ├── prompt.rs               # System prompt + context formatting
│   │   └── schema.rs               # Plan types + validation
│   ├── executor/
│   │   ├── mod.rs
│   │   ├── validator.rs            # Precondition checking
│   │   └── runner.rs               # Operation dispatch
│   ├── resolve/
│   │   ├── mod.rs
│   │   ├── bridge.rs               # Python process management
│   │   └── context.rs              # Resolve state types
│   └── error.rs                    # Error types
├── python/
│   └── resolve_bridge.py           # Bundled Python script (all operations)
└── schema/
    └── plan.schema.json            # JSON Schema (for reference)
```

---

## Plan Schema

### Top-Level Structure

```json
{
  "version": "1.0",
  "target": {
    "project": "Project Name",
    "timeline": "Timeline Name"
  },
  "preconditions": [
    { "type": "project_open" },
    { "type": "timeline_exists", "name": "Timeline 1" }
  ],
  "operations": [
    { "op": "set_clip_property", "params": { ... } }
  ]
}
```

### Precondition Types

| Type | Params | Description |
|------|--------|-------------|
| `project_open` | - | A project must be open |
| `timeline_exists` | `name: string` | Named timeline must exist |
| `timeline_active` | - | A timeline must be active |
| `track_exists` | `type: string, index: int` | Track must exist |
| `clip_exists` | `track: int, index: int` | Clip must exist at position |
| `media_exists` | `name: string` | Media must exist in pool |

### Operations (15 total)

#### Media Operations

**`import_media`** - Import files into media pool
```json
{
  "op": "import_media",
  "params": {
    "paths": ["/path/to/file1.mp4", "/path/to/file2.mov"]
  }
}
```
Returns: `{ "imported": ["file1.mp4"], "failed": [] }`

---

**`append_to_timeline`** - Append clips to timeline
```json
{
  "op": "append_to_timeline",
  "params": {
    "clips": ["clip1.mp4", "clip2.mov"],
    "track": 1
  }
}
```
Returns: `{ "appended": 2 }`

---

**`create_timeline`** - Create new timeline
```json
{
  "op": "create_timeline",
  "params": {
    "name": "New Timeline",
    "clips": ["clip1.mp4"]  // optional
  }
}
```
Returns: `{ "timeline": "New Timeline" }`

---

#### Clip Property Operations

**`set_clip_property`** - Modify clip properties
```json
{
  "op": "set_clip_property",
  "params": {
    "selector": {
      "track": 1,
      "index": 0        // specific clip
      // OR "name": "clip.mov"
      // OR "all": true (all clips on track)
    },
    "properties": {
      "Opacity": 50.0,
      "ZoomX": 1.2,
      "ZoomY": 1.2,
      "Pan": 100,
      "Tilt": -50,
      "RotationAngle": 15,
      "CropLeft": 0.1,
      "CropRight": 0.1,
      "FlipX": true
    }
  }
}
```
Returns: `{ "modified": 5 }`

**Available Properties:**

| Property | Type | Range |
|----------|------|-------|
| `Opacity` | float | 0.0 - 100.0 |
| `ZoomX` | float | 0.0 - 100.0 |
| `ZoomY` | float | 0.0 - 100.0 |
| `Pan` | float | -4.0*width to 4.0*width |
| `Tilt` | float | -4.0*height to 4.0*height |
| `RotationAngle` | float | -360.0 to 360.0 |
| `AnchorPointX` | float | position |
| `AnchorPointY` | float | position |
| `CropLeft` | float | 0.0 to width |
| `CropRight` | float | 0.0 to width |
| `CropTop` | float | 0.0 to height |
| `CropBottom` | float | 0.0 to height |
| `FlipX` | bool | true/false |
| `FlipY` | bool | true/false |

---

#### Marker Operations

**`add_marker`** - Add marker to timeline
```json
{
  "op": "add_marker",
  "params": {
    "frame": 100,
    "color": "Red",
    "name": "Important",
    "note": "Review this section",
    "duration": 30
  }
}
```
Returns: `{ "frame": 100 }`

**Available Colors:** Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream

---

**`delete_marker`** - Remove markers
```json
{
  "op": "delete_marker",
  "params": {
    "frame": 100,     // delete at specific frame
    // OR "color": "Red"  // delete all of color
  }
}
```
Returns: `{ "deleted": 1 }`

---

#### Track Operations

**`add_track`** - Add new track
```json
{
  "op": "add_track",
  "params": {
    "type": "video"  // video | audio | subtitle
  }
}
```
Returns: `{ "index": 2 }`

---

**`set_track_name`** - Rename track
```json
{
  "op": "set_track_name",
  "params": {
    "type": "video",
    "index": 1,
    "name": "B-Roll"
  }
}
```
Returns: `{}`

---

**`enable_track`** - Enable/disable track
```json
{
  "op": "enable_track",
  "params": {
    "type": "video",
    "index": 1,
    "enabled": false
  }
}
```
Returns: `{}`

---

**`lock_track`** - Lock/unlock track
```json
{
  "op": "lock_track",
  "params": {
    "type": "video",
    "index": 1,
    "locked": true
  }
}
```
Returns: `{}`

---

#### Render Operations

**`add_render_job`** - Configure render job
```json
{
  "op": "add_render_job",
  "params": {
    "format": "mp4",
    "codec": "H265",
    "path": "/Users/me/Renders",
    "filename": "output"
  }
}
```
Returns: `{ "job_id": "..." }`

**Available Formats:** AVI, BRAW, Cineon, DCP, DPX, EXR, GIF, HLS, IMF, JPEG 2000, MJ2, MKV, MP4, MTS, MXF OP-Atom, MXF OP1A, Panasonic AVC, QuickTime, TIFF, Wave

---

**`start_render`** - Begin rendering
```json
{
  "op": "start_render",
  "params": {
    "wait": true  // block until complete
  }
}
```
Returns: `{ "status": "complete" }`

---

#### Timeline Operations

**`set_timeline`** - Switch active timeline
```json
{
  "op": "set_timeline",
  "params": {
    "name": "Timeline 2"
    // OR "index": 2
  }
}
```
Returns: `{ "timeline": "Timeline 2" }`

---

**`duplicate_timeline`** - Copy timeline
```json
{
  "op": "duplicate_timeline",
  "params": {
    "name": "Timeline 1 Copy"
  }
}
```
Returns: `{ "timeline": "Timeline 1 Copy" }`

---

**`export_timeline`** - Export timeline
```json
{
  "op": "export_timeline",
  "params": {
    "path": "/Users/me/exports/timeline.xml",
    "format": "xml"  // aaf | xml | edl | fcpxml
  }
}
```
Returns: `{ "path": "/Users/me/exports/timeline.xml" }`

---

## Resolve Context

The context sent to the LLM for plan generation:

```json
{
  "product": "DaVinci Resolve Studio",
  "version": "20.0.0.49",
  "project": {
    "name": "content",
    "timeline_count": 2
  },
  "timeline": {
    "name": "Timeline 1",
    "frame_rate": 29.97,
    "resolution": [1920, 1080],
    "start_frame": 108000,
    "end_frame": 108804,
    "tracks": {
      "video": [
        {
          "index": 1,
          "name": "Video 1",
          "clips": [
            {
              "index": 0,
              "name": "decocereus.mov",
              "start": 108000,
              "end": 108804,
              "duration": 804
            }
          ]
        }
      ],
      "audio": [
        { "index": 1, "name": "Audio 1", "clips": [] }
      ]
    },
    "markers": []
  },
  "media_pool": {
    "clips": ["decocereus.mov", "clip2.mp4"],
    "folders": ["Raw Footage", "Audio"]
  }
}
```

---

## System Prompt

```markdown
You are an assistant that converts natural language editing requests into structured execution plans for DaVinci Resolve.

## Available Operations

### Media
- `import_media`: Import files into media pool
  params: { paths: string[] }

- `append_to_timeline`: Add clips to end of timeline  
  params: { clips: string[], track?: number }

- `create_timeline`: Create new timeline
  params: { name: string, clips?: string[] }

### Clip Properties
- `set_clip_property`: Modify clip properties
  params: { selector: ClipSelector, properties: PropertyMap }
  
  ClipSelector:
    { track: number, index: number } - specific clip
    { track: number, name: string } - by name
    { track: number, all: true } - all clips on track
  
  Properties: Opacity (0-100), ZoomX/ZoomY (0-100), Pan, Tilt, 
  RotationAngle (-360 to 360), CropLeft/Right/Top/Bottom, FlipX/FlipY (bool)

### Markers
- `add_marker`: Add marker to timeline
  params: { frame: number, color: string, name?: string, note?: string, duration?: number }
  colors: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream

- `delete_marker`: Remove markers
  params: { frame?: number, color?: string }

### Tracks
- `add_track`: Add new track
  params: { type: "video" | "audio" | "subtitle" }

- `set_track_name`: Rename track
  params: { type: string, index: number, name: string }

- `enable_track`: Enable/disable track
  params: { type: string, index: number, enabled: boolean }

- `lock_track`: Lock/unlock track
  params: { type: string, index: number, locked: boolean }

### Render
- `add_render_job`: Configure render job
  params: { format?: string, codec?: string, path?: string, filename?: string }

- `start_render`: Begin rendering
  params: { wait?: boolean }

### Timeline
- `set_timeline`: Switch active timeline
  params: { name?: string, index?: number }

- `duplicate_timeline`: Copy timeline
  params: { name: string }

- `export_timeline`: Export timeline
  params: { path: string, format: "aaf" | "xml" | "edl" | "fcpxml" }

## Constraints (CRITICAL - Operations NOT available)
- Cannot MOVE clips already on timeline (only append new clips)
- Cannot INSERT clips at specific timecodes (append only)
- Cannot create TRANSITIONS (no API)
- Cannot add KEYFRAME animation (requires Fusion, not supported in v1)
- Cannot do AUDIO automation/keyframes
- Cannot TRIM/SLIP/SLIDE existing clips

If user requests something impossible, return an error plan:
{
  "version": "1.0",
  "error": "Cannot move clips on timeline - this operation is not supported by Resolve's scripting API",
  "suggestion": "To reorder clips, you would need to manually drag them in the Resolve UI"
}

## Output Format
Return ONLY valid JSON. No markdown, no explanation, just the JSON object.

{
  "version": "1.0",
  "target": {
    "project": "<current project name>",
    "timeline": "<current timeline name or null>"
  },
  "preconditions": [
    { "type": "project_open" },
    { "type": "timeline_exists", "name": "..." }
  ],
  "operations": [
    { "op": "<operation_name>", "params": { ... } }
  ]
}

## Current Context
{{CONTEXT}}

## User Request
{{REQUEST}}
```

---

## Python Bridge Protocol

### Communication
- CLI spawns Python process
- Sends JSON command to stdin
- Receives JSON response from stdout
- Stderr used for logging/errors

### Command Format
```json
{
  "op": "operation_name",
  "params": { ... }
}
```

### Response Format

Success:
```json
{
  "success": true,
  "result": { ... }
}
```

Error:
```json
{
  "success": false,
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

### Special Commands

**`get_context`** - Returns full Resolve context
```json
{ "op": "get_context" }
```

**`check_connection`** - Verify Resolve is running
```json
{ "op": "check_connection" }
```

---

## Error Codes

| Code | Description |
|------|-------------|
| `RESOLVE_NOT_RUNNING` | DaVinci Resolve is not running |
| `NO_PROJECT` | No project is currently open |
| `NO_TIMELINE` | No timeline is active |
| `TIMELINE_NOT_FOUND` | Named timeline does not exist |
| `CLIP_NOT_FOUND` | Clip not found at specified position |
| `TRACK_NOT_FOUND` | Track does not exist |
| `MEDIA_NOT_FOUND` | Media not found in pool |
| `IMPORT_FAILED` | Failed to import media |
| `RENDER_FAILED` | Render job failed |
| `INVALID_PROPERTY` | Property name not recognized |
| `INVALID_VALUE` | Property value out of range |
| `PYTHON_ERROR` | Unexpected Python error |
| `API_ERROR` | LLM API error |
| `SCHEMA_ERROR` | Plan JSON validation failed |

---

## Implementation Phases

### Phase 1: Foundation
- [x] Project structure created
- [x] Cargo.toml with dependencies
- [x] Basic CLI skeleton (clap)
- [x] Config file loading
- [x] Python bridge: connection check
- [x] `doctor` command
- [x] `status` command

### Phase 2: Plan Generation
- [x] Claude API client
- [x] System prompt template
- [x] Context formatting
- [x] Plan schema types
- [x] JSON validation
- [x] `plan` command

### Phase 3: Execution
- [x] Precondition validator
- [x] Operation dispatcher
- [x] All 15 Python operations
- [x] Execution logging
- [x] `apply` command

### Phase 4: Polish
- [x] Error messages
- [x] Pretty output formatting
- [ ] Edge case handling
- [ ] README documentation
- [ ] Testing

---

## Deferred Features (v2)

- [ ] Plan history (SQLite storage)
- [ ] `history` command
- [ ] Rollback via project duplication
- [ ] Fusion animation operations
- [ ] Batch operations on multiple timelines
- [ ] Custom operation macros
- [ ] Local LLM support (Ollama)

---

## Dependencies

```toml
[dependencies]
clap = { version = "4", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
toml = "0.8"
dirs = "5"
tempfile = "3"
thiserror = "2"
anyhow = "1"
tracing = "0.1"
tracing-subscriber = "0.3"
```

---

## Testing Strategy

### Unit Tests
- Config parsing
- Plan schema validation
- Context serialization

### Integration Tests
- Python bridge communication
- Full plan → execute cycle (requires Resolve running)

### Manual Testing Checklist
- [ ] `doctor` with Resolve running
- [ ] `doctor` with Resolve closed
- [ ] `status` shows correct project/timeline
- [ ] `plan` generates valid JSON
- [ ] `apply --dry-run` validates without executing
- [ ] `apply --yes` executes operations
- [ ] Error handling for invalid requests

---

## Example Workflows

### Import and Arrange
```bash
magic-agent apply "import all mp4 files from ~/Videos/raw and add them to the timeline" --yes
```

### Batch Property Change
```bash
magic-agent apply "set opacity to 80% on all clips in video track 1" --yes
```

### Add Markers
```bash
magic-agent apply "add a red marker named 'Review' at frame 500 with note 'check audio sync'" --yes
```

### Prepare for Render
```bash
magic-agent apply "add a render job for mp4 h265 to ~/Renders/final" --yes
magic-agent apply "start the render and wait for completion" --yes
```

### Export Timeline
```bash
magic-agent apply "export the timeline as fcpxml to ~/exports/timeline.fcpxml" --yes
```
