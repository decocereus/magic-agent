use thiserror::Error;

/// Re-export for library use
pub use MagicError as MagicAgentError;

#[derive(Error, Debug)]
#[allow(dead_code)]
pub enum MagicError {
    #[error("DaVinci Resolve is not running")]
    ResolveNotRunning,

    #[error("No project is currently open")]
    NoProject,

    #[error("No timeline is active")]
    NoTimeline,

    #[error("Timeline not found: {0}")]
    TimelineNotFound(String),

    #[error("Clip not found at track {track}, index {index}")]
    ClipNotFound { track: i32, index: i32 },

    #[error("Track not found: {track_type} {index}")]
    TrackNotFound { track_type: String, index: i32 },

    #[error("Media not found in pool: {0}")]
    MediaNotFound(String),

    #[error("Failed to import media: {0}")]
    ImportFailed(String),

    #[error("Render failed: {0}")]
    RenderFailed(String),

    #[error("Invalid property: {0}")]
    InvalidProperty(String),

    #[error("Invalid value for {property}: {message}")]
    InvalidValue { property: String, message: String },

    #[error("Python bridge error: {0}")]
    PythonError(String),

    #[error("LLM API error: {0}")]
    ApiError(String),

    #[error("Plan validation failed: {0}")]
    SchemaError(String),

    #[error("Config error: {0}")]
    ConfigError(String),

    #[error("Python not found at: {0}")]
    PythonNotFound(String),

    #[error("Operation not supported: {0}")]
    UnsupportedOperation(String),
}

/// Error code for JSON output
#[allow(dead_code)]
impl MagicError {
    pub fn code(&self) -> &'static str {
        match self {
            MagicError::ResolveNotRunning => "RESOLVE_NOT_RUNNING",
            MagicError::NoProject => "NO_PROJECT",
            MagicError::NoTimeline => "NO_TIMELINE",
            MagicError::TimelineNotFound(_) => "TIMELINE_NOT_FOUND",
            MagicError::ClipNotFound { .. } => "CLIP_NOT_FOUND",
            MagicError::TrackNotFound { .. } => "TRACK_NOT_FOUND",
            MagicError::MediaNotFound(_) => "MEDIA_NOT_FOUND",
            MagicError::ImportFailed(_) => "IMPORT_FAILED",
            MagicError::RenderFailed(_) => "RENDER_FAILED",
            MagicError::InvalidProperty(_) => "INVALID_PROPERTY",
            MagicError::InvalidValue { .. } => "INVALID_VALUE",
            MagicError::PythonError(_) => "PYTHON_ERROR",
            MagicError::ApiError(_) => "API_ERROR",
            MagicError::SchemaError(_) => "SCHEMA_ERROR",
            MagicError::ConfigError(_) => "CONFIG_ERROR",
            MagicError::PythonNotFound(_) => "PYTHON_NOT_FOUND",
            MagicError::UnsupportedOperation(_) => "UNSUPPORTED_OPERATION",
        }
    }
}
