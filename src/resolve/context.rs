use serde::{Deserialize, Serialize};

/// Full Resolve context for LLM consumption
#[derive(Debug, Serialize, Deserialize)]
pub struct ResolveContext {
    pub product: String,
    pub version: String,
    pub project: Option<ProjectInfo>,
    pub timeline: Option<TimelineInfo>,
    pub media_pool: Option<MediaPoolInfo>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProjectInfo {
    pub name: String,
    pub timeline_count: i32,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TimelineInfo {
    pub name: String,
    pub frame_rate: f64,
    pub resolution: [i32; 2],
    pub start_frame: i64,
    pub end_frame: i64,
    pub tracks: TrackInfo,
    pub markers: Vec<MarkerInfo>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TrackInfo {
    pub video: Vec<Track>,
    pub audio: Vec<Track>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Track {
    pub index: i32,
    pub name: String,
    pub clips: Vec<ClipInfo>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ClipInfo {
    pub index: i32,
    pub name: String,
    pub start: i64,
    pub end: i64,
    pub duration: i64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct MarkerInfo {
    pub frame: i64,
    pub color: String,
    pub name: String,
    pub note: String,
    pub duration: i32,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct MediaPoolInfo {
    pub clips: Vec<String>,
    pub folders: Vec<String>,
}

/// Connection check result
#[derive(Debug, Serialize, Deserialize)]
pub struct ConnectionInfo {
    pub product: String,
    pub version: String,
}
