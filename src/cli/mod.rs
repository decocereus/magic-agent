pub mod commands;

use clap::{Args, Parser, Subcommand, ValueEnum};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "magic-agent")]
#[command(about = "CLI for DaVinci Resolve scripting operations")]
#[command(version)]
pub struct Cli {
    /// Use alternate config file
    #[arg(long, global = true)]
    pub config: Option<PathBuf>,

    /// Human-readable output instead of JSON
    #[arg(long, global = true)]
    pub pretty: bool,

    /// Enable debug logging
    #[arg(long, global = true)]
    pub verbose: bool,

    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Check Resolve, Python, and bridge status
    Doctor,

    /// Show current project/timeline state
    Status,

    /// List available operation names
    Ops {
        #[command(subcommand)]
        command: OpsCommands,
    },

    /// Execute a single Resolve operation
    Op(OpArgs),

    /// Execute a batch of operations from JSON
    Batch(BatchArgs),

    /// Marker operations
    Marker {
        #[command(subcommand)]
        command: MarkerCommands,
    },

    /// Track operations
    Track {
        #[command(subcommand)]
        command: TrackCommands,
    },

    /// Timeline operations
    Timeline {
        #[command(subcommand)]
        command: TimelineCommands,
    },

    /// Media pool operations
    Media {
        #[command(subcommand)]
        command: MediaCommands,
    },

    /// Clip operations
    Clip {
        #[command(subcommand)]
        command: ClipCommands,
    },

    /// Render operations
    Render {
        #[command(subcommand)]
        command: RenderCommands,
    },

    /// Project operations
    Project {
        #[command(subcommand)]
        command: ProjectCommands,
    },

    /// Resolve page operations
    Page {
        #[command(subcommand)]
        command: PageCommands,
    },

    /// Playhead timecode operations
    Timecode {
        #[command(subcommand)]
        command: TimecodeCommands,
    },
}

#[derive(Subcommand)]
pub enum OpsCommands {
    /// List all supported operations
    List,
    /// Print the machine-readable ops schema
    Schema(OpsSchemaArgs),
}

#[derive(Clone, ValueEnum)]
pub enum OpsSchemaFormat {
    Json,
    Pretty,
    Raw,
}

#[derive(Args)]
pub struct OpsSchemaArgs {
    /// Output format: json, pretty, raw
    #[arg(long, value_enum)]
    pub format: Option<OpsSchemaFormat>,
}

#[derive(Args)]
pub struct OpArgs {
    /// Operation name (ex: add_marker)
    pub op: String,

    /// JSON params (ex: '{"frame":100,"color":"Red"}')
    #[arg(long)]
    pub params: Option<String>,

    /// Read params JSON from file
    #[arg(long)]
    pub params_file: Option<PathBuf>,

    /// Read params JSON from stdin
    #[arg(long)]
    pub params_stdin: bool,
}

#[derive(Args)]
pub struct BatchArgs {
    /// Read batch JSON from file
    #[arg(long)]
    pub file: Option<PathBuf>,

    /// Read batch JSON from stdin
    #[arg(long)]
    pub stdin: bool,

    /// Validate and echo the batch without executing
    #[arg(long)]
    pub dry_run: bool,
}

#[derive(Subcommand)]
pub enum MarkerCommands {
    /// Add a marker to the timeline
    Add(MarkerAddArgs),
    /// Delete markers by frame or color
    Delete(MarkerDeleteArgs),
}

#[derive(Args)]
pub struct MarkerAddArgs {
    /// Frame number
    pub frame: i64,
    /// Marker color (ex: Red, Blue)
    #[arg(long, default_value = "Blue")]
    pub color: String,
    /// Treat frame as relative to the timeline start frame
    #[arg(long)]
    pub relative: bool,
    /// Marker name
    #[arg(long)]
    pub name: Option<String>,
    /// Marker note
    #[arg(long)]
    pub note: Option<String>,
    /// Marker duration (frames)
    #[arg(long)]
    pub duration: Option<i32>,
}

#[derive(Args)]
pub struct MarkerDeleteArgs {
    /// Delete marker at frame
    #[arg(long)]
    pub frame: Option<i64>,
    /// Delete all markers of color
    #[arg(long)]
    pub color: Option<String>,
    /// Treat frame as relative to the timeline start frame
    #[arg(long)]
    pub relative: bool,
}

#[derive(Subcommand)]
pub enum TrackCommands {
    /// Add a track
    Add(TrackAddArgs),
    /// Delete a track
    Delete(TrackDeleteArgs),
    /// Rename a track
    Name(TrackNameArgs),
    /// Enable or disable a track
    Enable(TrackEnableArgs),
    /// Lock or unlock a track
    Lock(TrackLockArgs),
}

#[derive(Args)]
pub struct TrackAddArgs {
    /// Track type: video, audio, subtitle
    #[arg(long = "type", default_value = "video")]
    pub track_type: String,
}

#[derive(Args)]
pub struct TrackDeleteArgs {
    #[arg(long = "type", default_value = "video")]
    pub track_type: String,
    #[arg(long)]
    pub index: i32,
}

#[derive(Args)]
pub struct TrackNameArgs {
    #[arg(long = "type", default_value = "video")]
    pub track_type: String,
    #[arg(long)]
    pub index: i32,
    #[arg(long)]
    pub name: String,
}

#[derive(Args)]
pub struct TrackEnableArgs {
    #[arg(long = "type", default_value = "video")]
    pub track_type: String,
    #[arg(long)]
    pub index: i32,
    /// Enable the track
    #[arg(long)]
    pub enable: bool,
    /// Disable the track
    #[arg(long)]
    pub disable: bool,
}

#[derive(Args)]
pub struct TrackLockArgs {
    #[arg(long = "type", default_value = "video")]
    pub track_type: String,
    #[arg(long)]
    pub index: i32,
    /// Lock the track
    #[arg(long)]
    pub lock: bool,
    /// Unlock the track
    #[arg(long)]
    pub unlock: bool,
}

#[derive(Subcommand)]
pub enum TimelineCommands {
    /// Set the active timeline
    Set(TimelineSetArgs),
    /// Duplicate the active timeline
    Duplicate(TimelineDuplicateArgs),
    /// Export timeline
    Export(TimelineExportArgs),
    /// Import timeline from file
    Import(TimelineImportArgs),
}

#[derive(Args)]
pub struct TimelineSetArgs {
    /// Timeline name
    #[arg(long)]
    pub name: Option<String>,
    /// Timeline index (1-based)
    #[arg(long)]
    pub index: Option<i32>,
}

#[derive(Args)]
pub struct TimelineDuplicateArgs {
    /// New timeline name
    #[arg(long)]
    pub name: String,
}

#[derive(Args)]
pub struct TimelineExportArgs {
    /// Output path
    #[arg(long)]
    pub path: PathBuf,
    /// Format: aaf, xml, edl, fcpxml
    #[arg(long, default_value = "xml")]
    pub format: String,
}

#[derive(Args)]
pub struct TimelineImportArgs {
    /// Timeline file path
    #[arg(long)]
    pub path: PathBuf,
    /// New timeline name
    #[arg(long)]
    pub name: Option<String>,
    /// Do not import source clips
    #[arg(long)]
    pub no_import_source_clips: bool,
}

#[derive(Subcommand)]
pub enum MediaCommands {
    /// Import media into the media pool
    Import(MediaImportArgs),
    /// Append clips to timeline
    Append(MediaAppendArgs),
}

#[derive(Args)]
pub struct MediaImportArgs {
    /// Paths to media files
    #[arg(value_name = "PATH", num_args = 1..)]
    pub paths: Vec<PathBuf>,
}

#[derive(Args)]
pub struct MediaAppendArgs {
    /// Clip names to append
    #[arg(value_name = "CLIP", num_args = 1..)]
    pub clips: Vec<String>,
    /// Track index
    #[arg(long)]
    pub track: Option<i32>,
}

#[derive(Subcommand)]
pub enum ClipCommands {
    /// Set clip properties
    SetProperty(ClipSetPropertyArgs),
    /// Enable or disable clip(s)
    Enable(ClipEnableArgs),
    /// Set or clear clip color
    Color(ClipColorArgs),
    /// Delete clip(s)
    Delete(ClipDeleteArgs),
    /// Link or unlink clips
    Link(ClipLinkArgs),
}

#[derive(Args)]
pub struct ClipSetPropertyArgs {
    #[arg(long, default_value_t = 1)]
    pub track: i32,
    #[arg(long)]
    pub index: Option<i32>,
    #[arg(long)]
    pub name: Option<String>,
    #[arg(long)]
    pub all: bool,
    /// Properties in KEY=VALUE format
    #[arg(long = "set", value_name = "KEY=VALUE", num_args = 1..)]
    pub sets: Vec<String>,
}

#[derive(Args)]
pub struct ClipEnableArgs {
    #[arg(long, default_value_t = 1)]
    pub track: i32,
    #[arg(long)]
    pub index: Option<i32>,
    #[arg(long)]
    pub name: Option<String>,
    #[arg(long)]
    pub all: bool,
    #[arg(long, default_value = "video")]
    pub track_type: String,
    /// Enable selected clips
    #[arg(long)]
    pub enable: bool,
    /// Disable selected clips
    #[arg(long)]
    pub disable: bool,
}

#[derive(Args)]
pub struct ClipColorArgs {
    #[arg(long, default_value_t = 1)]
    pub track: i32,
    #[arg(long)]
    pub index: Option<i32>,
    #[arg(long)]
    pub name: Option<String>,
    #[arg(long)]
    pub all: bool,
    #[arg(long, default_value = "video")]
    pub track_type: String,
    /// Clip color label
    #[arg(long)]
    pub color: Option<String>,
    /// Clear clip color
    #[arg(long)]
    pub clear: bool,
}

#[derive(Args)]
pub struct ClipDeleteArgs {
    #[arg(long, default_value_t = 1)]
    pub track: i32,
    #[arg(long)]
    pub index: Vec<i32>,
    #[arg(long)]
    pub all: bool,
    #[arg(long, default_value = "video")]
    pub track_type: String,
    #[arg(long)]
    pub ripple: bool,
}

#[derive(Args)]
pub struct ClipLinkArgs {
    #[arg(long, default_value_t = 1)]
    pub track: i32,
    /// Clip indices to link/unlink
    #[arg(long, num_args = 1..)]
    pub indices: Vec<i32>,
    /// Link clips
    #[arg(long)]
    pub link: bool,
    /// Unlink clips
    #[arg(long)]
    pub unlink: bool,
}

#[derive(Subcommand)]
pub enum RenderCommands {
    /// Configure a render job
    AddJob(RenderAddJobArgs),
    /// Start rendering
    Start(RenderStartArgs),
    /// List available formats
    Formats,
    /// List codecs for a format
    Codecs(RenderCodecsArgs),
}

#[derive(Args)]
pub struct RenderAddJobArgs {
    #[arg(long)]
    pub format: Option<String>,
    #[arg(long)]
    pub codec: Option<String>,
    #[arg(long)]
    pub path: Option<PathBuf>,
    #[arg(long)]
    pub filename: Option<String>,
}

#[derive(Args)]
pub struct RenderStartArgs {
    /// Do not wait for render completion
    #[arg(long)]
    pub no_wait: bool,
}

#[derive(Args)]
pub struct RenderCodecsArgs {
    #[arg(long, default_value = "mp4")]
    pub format: String,
}

#[derive(Subcommand)]
pub enum ProjectCommands {
    /// Save current project
    Save,
    /// Export project to .drp
    Export(ProjectExportArgs),
    /// Get project setting(s)
    GetSetting(ProjectGetSettingArgs),
    /// Set a project setting
    SetSetting(ProjectSetSettingArgs),
}

#[derive(Args)]
pub struct ProjectExportArgs {
    #[arg(long)]
    pub path: PathBuf,
    #[arg(long)]
    pub without_stills_and_luts: bool,
}

#[derive(Args)]
pub struct ProjectGetSettingArgs {
    #[arg(long)]
    pub name: Option<String>,
}

#[derive(Args)]
pub struct ProjectSetSettingArgs {
    #[arg(long)]
    pub name: String,
    #[arg(long)]
    pub value: String,
}

#[derive(Subcommand)]
pub enum PageCommands {
    /// Get current Resolve page
    Get,
    /// Open a Resolve page
    Open(PageOpenArgs),
}

#[derive(Args)]
pub struct PageOpenArgs {
    /// Page name: media, cut, edit, fusion, color, fairlight, deliver
    #[arg(long)]
    pub page: String,
}

#[derive(Subcommand)]
pub enum TimecodeCommands {
    /// Get current timecode
    Get,
    /// Set current timecode
    Set(TimecodeSetArgs),
}

#[derive(Args)]
pub struct TimecodeSetArgs {
    /// Timecode in HH:MM:SS:FF
    pub timecode: String,
}
