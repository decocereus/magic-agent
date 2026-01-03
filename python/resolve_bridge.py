#!/usr/bin/env python3
"""
DaVinci Resolve Bridge - Communication layer between magic-agent CLI and Resolve.

Protocol:
- Reads JSON command from stdin
- Writes JSON response to stdout
- Logs/errors go to stderr
"""

import sys
import json
import os

# Add Resolve script module path
RESOLVE_SCRIPT_PATHS = [
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
]

for path in RESOLVE_SCRIPT_PATHS:
    if path not in sys.path:
        sys.path.append(path)


def get_resolve():
    """Get the Resolve application object."""
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except ImportError:
        return None


def success(result=None):
    """Return success response."""
    return {"success": True, "result": result or {}}


def error(message, code="PYTHON_ERROR"):
    """Return error response."""
    return {"success": False, "error": message, "code": code}


# =============================================================================
# Operations
# =============================================================================

def op_check_connection(resolve, params):
    """Check if Resolve is running and accessible."""
    if resolve is None:
        return error("DaVinci Resolve is not running", "RESOLVE_NOT_RUNNING")
    
    # Try to get product name to verify connection
    try:
        product = resolve.GetProductName()
        version = resolve.GetVersionString()
        return success({"product": product, "version": version})
    except Exception as e:
        return error(f"Failed to connect to Resolve: {e}", "RESOLVE_NOT_RUNNING")


def op_get_context(resolve, params):
    """Get full Resolve context for LLM."""
    if resolve is None:
        return error("DaVinci Resolve is not running", "RESOLVE_NOT_RUNNING")
    
    try:
        context = {
            "product": resolve.GetProductName(),
            "version": resolve.GetVersionString(),
            "project": None,
            "timeline": None,
            "media_pool": None,
        }
        
        pm = resolve.GetProjectManager()
        project = pm.GetCurrentProject() if pm else None
        
        if project:
            context["project"] = {
                "name": project.GetName(),
                "timeline_count": project.GetTimelineCount(),
            }
            
            # Get timeline info
            timeline = project.GetCurrentTimeline()
            if timeline:
                context["timeline"] = get_timeline_context(timeline)
            
            # Get media pool info
            media_pool = project.GetMediaPool()
            if media_pool:
                context["media_pool"] = get_media_pool_context(media_pool)
        
        return success(context)
    except Exception as e:
        return error(f"Failed to get context: {e}")


def get_timeline_context(timeline):
    """Extract timeline information."""
    try:
        settings = timeline.GetSetting()
        
        # Get track info
        video_tracks = []
        audio_tracks = []
        
        video_track_count = timeline.GetTrackCount("video")
        audio_track_count = timeline.GetTrackCount("audio")
        
        for i in range(1, video_track_count + 1):
            track_info = {
                "index": i,
                "name": timeline.GetTrackName("video", i),
                "clips": get_track_clips(timeline, "video", i),
            }
            video_tracks.append(track_info)
        
        for i in range(1, audio_track_count + 1):
            track_info = {
                "index": i,
                "name": timeline.GetTrackName("audio", i),
                "clips": get_track_clips(timeline, "audio", i),
            }
            audio_tracks.append(track_info)
        
        # Get markers
        markers = []
        timeline_markers = timeline.GetMarkers()
        for frame, marker_data in timeline_markers.items():
            markers.append({
                "frame": frame,
                "color": marker_data.get("color", ""),
                "name": marker_data.get("name", ""),
                "note": marker_data.get("note", ""),
                "duration": marker_data.get("duration", 1),
            })
        
        return {
            "name": timeline.GetName(),
            "frame_rate": float(settings.get("timelineFrameRate", 24)),
            "resolution": [
                int(settings.get("timelineResolutionWidth", 1920)),
                int(settings.get("timelineResolutionHeight", 1080)),
            ],
            "start_frame": timeline.GetStartFrame(),
            "end_frame": timeline.GetEndFrame(),
            "tracks": {
                "video": video_tracks,
                "audio": audio_tracks,
            },
            "markers": markers,
        }
    except Exception as e:
        print(f"Error getting timeline context: {e}", file=sys.stderr)
        return None


def get_track_clips(timeline, track_type, track_index):
    """Get clips on a track."""
    clips = []
    try:
        items = timeline.GetItemListInTrack(track_type, track_index)
        if items:
            for idx, item in enumerate(items):
                clips.append({
                    "index": idx,
                    "name": item.GetName(),
                    "start": item.GetStart(),
                    "end": item.GetEnd(),
                    "duration": item.GetDuration(),
                })
    except Exception as e:
        print(f"Error getting track clips: {e}", file=sys.stderr)
    return clips


def get_media_pool_context(media_pool):
    """Get media pool information."""
    try:
        root = media_pool.GetRootFolder()
        clips = []
        folders = []
        
        # Get clips in root
        for clip in root.GetClipList() or []:
            clips.append(clip.GetName())
        
        # Get subfolders
        for folder in root.GetSubFolderList() or []:
            folders.append(folder.GetName())
        
        return {
            "clips": clips,
            "folders": folders,
        }
    except Exception as e:
        print(f"Error getting media pool context: {e}", file=sys.stderr)
        return {"clips": [], "folders": []}


# =============================================================================
# Media Operations
# =============================================================================

def op_import_media(resolve, params):
    """Import files into media pool."""
    paths = params.get("paths", [])
    if not paths:
        return error("No paths provided", "INVALID_VALUE")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    imported = []
    failed = []
    
    for path in paths:
        if os.path.exists(path):
            result = media_pool.ImportMedia([path])
            if result:
                imported.append(os.path.basename(path))
            else:
                failed.append(path)
        else:
            failed.append(path)
    
    return success({"imported": imported, "failed": failed})


def op_append_to_timeline(resolve, params):
    """Append clips to timeline."""
    clip_names = params.get("clips", [])
    track = params.get("track", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    clips_to_append = []
    for name in clip_names:
        for clip in root.GetClipList() or []:
            if clip.GetName() == name:
                clips_to_append.append(clip)
                break
    
    if clips_to_append:
        result = media_pool.AppendToTimeline(clips_to_append)
        return success({"appended": len(result) if result else 0})
    
    return success({"appended": 0})


def op_create_timeline(resolve, params):
    """Create a new timeline."""
    name = params.get("name", "New Timeline")
    clip_names = params.get("clips", [])
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    
    if clip_names:
        # Create timeline with clips
        root = media_pool.GetRootFolder()
        clips = []
        for cname in clip_names:
            for clip in root.GetClipList() or []:
                if clip.GetName() == cname:
                    clips.append(clip)
                    break
        timeline = media_pool.CreateTimelineFromClips(name, clips)
    else:
        # Create empty timeline
        timeline = media_pool.CreateEmptyTimeline(name)
    
    if timeline:
        return success({"timeline": timeline.GetName()})
    return error("Failed to create timeline")


# =============================================================================
# Clip Property Operations
# =============================================================================

def op_set_clip_property(resolve, params):
    """Modify clip properties."""
    selector = params.get("selector", {})
    properties = params.get("properties", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    clips = []
    
    if selector.get("all"):
        # All clips on track
        items = timeline.GetItemListInTrack("video", track)
        if items:
            clips = list(items)
    elif "index" in selector:
        # Specific clip by index
        items = timeline.GetItemListInTrack("video", track)
        if items and 0 <= selector["index"] < len(items):
            clips = [items[selector["index"]]]
    elif "name" in selector:
        # Clip by name
        items = timeline.GetItemListInTrack("video", track)
        if items:
            clips = [item for item in items if item.GetName() == selector["name"]]
    
    modified = 0
    for clip in clips:
        for prop, value in properties.items():
            try:
                clip.SetProperty(prop, value)
                modified += 1
            except Exception as e:
                print(f"Failed to set {prop} on clip: {e}", file=sys.stderr)
    
    return success({"modified": modified})


# =============================================================================
# Marker Operations
# =============================================================================

def op_add_marker(resolve, params):
    """Add marker to timeline."""
    frame = params.get("frame", 0)
    color = params.get("color", "Blue")
    name = params.get("name", "")
    note = params.get("note", "")
    duration = params.get("duration", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.AddMarker(frame, color, name, note, duration)
    if result:
        return success({"frame": frame})
    return error("Failed to add marker")


def op_delete_marker(resolve, params):
    """Delete markers."""
    frame = params.get("frame")
    color = params.get("color")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    deleted = 0
    if frame is not None:
        if timeline.DeleteMarkerAtFrame(frame):
            deleted = 1
    elif color:
        if timeline.DeleteMarkersByColor(color):
            deleted = 1  # API doesn't return count
    
    return success({"deleted": deleted})


# =============================================================================
# Track Operations
# =============================================================================

def op_add_track(resolve, params):
    """Add new track."""
    track_type = params.get("type", "video")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    current_count = timeline.GetTrackCount(track_type)
    result = timeline.AddTrack(track_type)
    
    if result:
        return success({"index": current_count + 1})
    return error(f"Failed to add {track_type} track")


def op_set_track_name(resolve, params):
    """Rename track."""
    track_type = params.get("type", "video")
    index = params.get("index", 1)
    name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.SetTrackName(track_type, index, name)
    if result:
        return success({})
    return error(f"Failed to rename track")


def op_enable_track(resolve, params):
    """Enable/disable track."""
    track_type = params.get("type", "video")
    index = params.get("index", 1)
    enabled = params.get("enabled", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.SetTrackEnable(track_type, index, enabled)
    if result:
        return success({})
    return error(f"Failed to set track enable state")


def op_lock_track(resolve, params):
    """Lock/unlock track."""
    track_type = params.get("type", "video")
    index = params.get("index", 1)
    locked = params.get("locked", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.SetTrackLock(track_type, index, locked)
    if result:
        return success({})
    return error(f"Failed to set track lock state")


# =============================================================================
# Render Operations
# =============================================================================

def op_add_render_job(resolve, params):
    """Configure render job."""
    format_name = params.get("format", "mp4")
    codec = params.get("codec", "H264")
    path = params.get("path", "")
    filename = params.get("filename", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    # Set render settings
    project.SetRenderSettings({
        "TargetDir": path,
        "CustomName": filename,
    })
    
    job_id = project.AddRenderJob()
    if job_id:
        return success({"job_id": job_id})
    return error("Failed to add render job", "RENDER_FAILED")


def op_start_render(resolve, params):
    """Begin rendering."""
    wait = params.get("wait", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.StartRendering()
    if not result:
        return error("Failed to start render", "RENDER_FAILED")
    
    if wait:
        while project.IsRenderingInProgress():
            import time
            time.sleep(1)
    
    return success({"status": "complete" if wait else "started"})


# =============================================================================
# Timeline Operations
# =============================================================================

def op_set_timeline(resolve, params):
    """Switch active timeline."""
    name = params.get("name")
    index = params.get("index")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    if name:
        count = project.GetTimelineCount()
        for i in range(1, count + 1):
            tl = project.GetTimelineByIndex(i)
            if tl and tl.GetName() == name:
                project.SetCurrentTimeline(tl)
                return success({"timeline": name})
        return error(f"Timeline not found: {name}", "TIMELINE_NOT_FOUND")
    
    if index:
        tl = project.GetTimelineByIndex(index)
        if tl:
            project.SetCurrentTimeline(tl)
            return success({"timeline": tl.GetName()})
        return error(f"Timeline not found at index {index}", "TIMELINE_NOT_FOUND")
    
    return error("Must specify name or index")


def op_duplicate_timeline(resolve, params):
    """Copy timeline."""
    name = params.get("name", "Timeline Copy")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    new_timeline = timeline.DuplicateTimeline(name)
    if new_timeline:
        return success({"timeline": new_timeline.GetName()})
    return error("Failed to duplicate timeline")


def op_export_timeline(resolve, params):
    """Export timeline."""
    path = params.get("path", "")
    format_type = params.get("format", "xml")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Map format to export type
    export_map = {
        "aaf": "AAF",
        "xml": "FinalCutProXML",
        "edl": "EDL",
        "fcpxml": "FCPXML",
    }
    
    export_type = export_map.get(format_type.lower(), "FinalCutProXML")
    
    result = timeline.Export(path, export_type)
    if result:
        return success({"path": path})
    return error(f"Failed to export timeline to {path}")


# =============================================================================
# Main
# =============================================================================

OPERATIONS = {
    "check_connection": op_check_connection,
    "get_context": op_get_context,
    "import_media": op_import_media,
    "append_to_timeline": op_append_to_timeline,
    "create_timeline": op_create_timeline,
    "set_clip_property": op_set_clip_property,
    "add_marker": op_add_marker,
    "delete_marker": op_delete_marker,
    "add_track": op_add_track,
    "set_track_name": op_set_track_name,
    "enable_track": op_enable_track,
    "lock_track": op_lock_track,
    "add_render_job": op_add_render_job,
    "start_render": op_start_render,
    "set_timeline": op_set_timeline,
    "duplicate_timeline": op_duplicate_timeline,
    "export_timeline": op_export_timeline,
}


def main():
    """Main entry point."""
    # Read command from stdin
    try:
        input_data = sys.stdin.read()
        command = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(json.dumps(error(f"Invalid JSON input: {e}")))
        sys.exit(1)
    
    op = command.get("op")
    params = command.get("params", {})
    
    if op not in OPERATIONS:
        print(json.dumps(error(f"Unknown operation: {op}")))
        sys.exit(1)
    
    # Get Resolve instance
    resolve = get_resolve()
    
    # Execute operation
    result = OPERATIONS[op](resolve, params)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
