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
    """Append clips to timeline with optional in/out points."""
    clips_param = params.get("clips", [])
    track = params.get("track", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    # Support both simple list of names and detailed clip info
    clips_to_append = []
    
    for clip_param in clips_param:
        # Handle both string names and dict with in/out points
        if isinstance(clip_param, str):
            # Simple case: just clip name
            clip_name = clip_param
            in_point = None
            out_point = None
        else:
            # Advanced case: dict with name and optional in/out points
            clip_name = clip_param.get("name")
            in_point = clip_param.get("in_point")  # Frame number
            out_point = clip_param.get("out_point")  # Frame number
        
        # Find the media pool clip
        media_pool_clip = None
        for clip in root.GetClipList() or []:
            if clip.GetName() == clip_name:
                media_pool_clip = clip
                break
        
        if not media_pool_clip:
            continue
        
        # Build clip info dict
        if in_point is not None or out_point is not None:
            # Use advanced format with in/out points
            clip_info = {
                "mediaPoolItem": media_pool_clip,
                "trackIndex": track
            }
            if in_point is not None:
                clip_info["startFrame"] = in_point
            if out_point is not None:
                clip_info["endFrame"] = out_point
            
            clips_to_append.append(clip_info)
        else:
            # Simple format - just the clip object
            clips_to_append.append(media_pool_clip)
    
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
    relative = params.get("relative")

    if not name:
        name = " "
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    try:
        frame = int(frame)
    except (TypeError, ValueError):
        return error("frame must be an integer", "INVALID_PARAM")

    start_frame = timeline.GetStartFrame() or 0
    if relative is True:
        frame = start_frame + frame
    elif relative is None and frame < start_frame:
        frame = start_frame + frame

    result = timeline.AddMarker(frame, color, name, note, duration)
    if result:
        return success({"frame": frame})
    return error("Failed to add marker")


def op_add_clip_marker(resolve, params):
    """Add marker to clip(s)."""
    selector = params.get("selector", {})
    frame = params.get("frame", 0)
    color = params.get("color", "Blue")
    name = params.get("name", "")
    note = params.get("note", "")
    duration = params.get("duration", 1)
    timeline_frame = params.get("timeline_frame", False)

    if not name:
        name = " "

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    try:
        frame = int(frame)
    except (TypeError, ValueError):
        return error("frame must be an integer", "INVALID_PARAM")

    track = selector.get("track", 1)
    track_type = selector.get("track_type", "video")
    items = timeline.GetItemListInTrack(track_type, track)
    if not items:
        return error("No clips found")

    clips = []
    if selector.get("all"):
        clips = list(items)
    elif "index" in selector:
        idx = selector["index"]
        if 0 <= idx < len(items):
            clips = [items[idx]]
    elif "name" in selector:
        clips = [item for item in items if item.GetName() == selector["name"]]

    if not clips:
        return error("No clips selected")

    added = 0
    failed = 0
    skipped = 0

    for clip in clips:
        marker_frame = frame
        if timeline_frame:
            start = clip.GetStart() or 0
            marker_frame = frame - start

        clip_duration = clip.GetDuration()
        if clip_duration is not None and (marker_frame < 0 or marker_frame >= clip_duration):
            skipped += 1
            continue

        result = clip.AddMarker(marker_frame, color, name, note, duration)
        if result:
            added += 1
        else:
            failed += 1

    return success({"added": added, "failed": failed, "skipped": skipped})


def op_delete_marker(resolve, params):
    """Delete markers."""
    frame = params.get("frame")
    color = params.get("color")
    relative = params.get("relative")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    deleted = 0
    if frame is not None:
        try:
            frame = int(frame)
        except (TypeError, ValueError):
            return error("frame must be an integer", "INVALID_PARAM")

        start_frame = timeline.GetStartFrame() or 0
        if relative is True:
            frame = start_frame + frame
        elif relative is None and frame < start_frame:
            frame = start_frame + frame

        if timeline.DeleteMarkerAtFrame(frame):
            deleted = 1
    elif color:
        if timeline.DeleteMarkersByColor(color):
            deleted = 1  # API doesn't return count
    
    return success({"deleted": deleted})


# =============================================================================
# Marker Utilities
# =============================================================================

def op_clear_markers(resolve, params):
    """Clear timeline and/or clip markers."""
    clear_timeline = params.get("timeline", True)
    clear_clips = params.get("clips", True)
    track_type = params.get("track_type")
    track_index = params.get("track")

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    counts = {
        "timeline_deleted": 0,
        "clip_deleted": 0,
        "tracks_scanned": 0,
        "clips_scanned": 0
    }

    if clear_timeline:
        markers = timeline.GetMarkers() or {}
        for frame in list(markers.keys()):
            if timeline.DeleteMarkerAtFrame(frame):
                counts["timeline_deleted"] += 1

    if clear_clips:
        track_types = [track_type] if track_type else ["video", "audio"]
        for ttype in track_types:
            max_track = timeline.GetTrackCount(ttype)
            track_indices = [track_index] if track_index else range(1, max_track + 1)
            for idx in track_indices:
                counts["tracks_scanned"] += 1
                items = timeline.GetItemListInTrack(ttype, idx) or []
                for item in items:
                    counts["clips_scanned"] += 1
                    markers = item.GetMarkers() or {}
                    for frame in list(markers.keys()):
                        try:
                            if item.DeleteMarkerAtFrame(frame):
                                counts["clip_deleted"] += 1
                        except Exception:
                            pass

    return success(counts)


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
    
    # Set format/codec only when explicitly provided
    if "format" in params or "codec" in params:
        project.SetCurrentRenderFormatAndCodec(format_name, codec)

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
# Fusion & Composition Operations
# =============================================================================

def op_insert_fusion_composition(resolve, params):
    """Insert a Fusion composition into timeline."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.InsertFusionCompositionIntoTimeline()
    if result:
        return success({"timeline_item": result.GetName() if result else "Fusion Composition"})
    return error("Failed to insert Fusion composition")


def op_create_fusion_clip(resolve, params):
    """Create a Fusion clip from timeline items."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Get clips to convert
    track = selector.get("track", 1)
    clips = []
    
    if selector.get("all"):
        items = timeline.GetItemListInTrack("video", track)
        if items:
            clips = list(items)
    elif "indices" in selector:
        items = timeline.GetItemListInTrack("video", track)
        if items:
            for idx in selector["indices"]:
                if 0 <= idx < len(items):
                    clips.append(items[idx])
    elif "index" in selector:
        items = timeline.GetItemListInTrack("video", track)
        if items and 0 <= selector["index"] < len(items):
            clips = [items[selector["index"]]]
    
    if not clips:
        return error("No clips selected")
    
    result = timeline.CreateFusionClip(clips)
    if result:
        return success({"timeline_item": result.GetName() if result else "Fusion Clip"})
    return error("Failed to create Fusion clip")


def op_add_fusion_comp_to_clip(resolve, params):
    """Add a Fusion composition to a specific clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    comp = clip.AddFusionComp()
    if comp:
        return success({"fusion_comp": "Added"})
    return error("Failed to add Fusion composition to clip")


def op_create_compound_clip(resolve, params):
    """Create a compound clip from timeline items."""
    selector = params.get("selector", {})
    name = params.get("name", "Compound Clip")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    clips = []
    
    if selector.get("all"):
        items = timeline.GetItemListInTrack("video", track)
        if items:
            clips = list(items)
    elif "indices" in selector:
        items = timeline.GetItemListInTrack("video", track)
        if items:
            for idx in selector["indices"]:
                if 0 <= idx < len(items):
                    clips.append(items[idx])
    elif "index" in selector:
        items = timeline.GetItemListInTrack("video", track)
        if items and 0 <= selector["index"] < len(items):
            clips = [items[selector["index"]]]
    
    if not clips:
        return error("No clips selected")
    
    result = timeline.CreateCompoundClip(clips, {"name": name})
    if result:
        return success({"timeline_item": result.GetName() if result else name})
    return error("Failed to create compound clip")


# =============================================================================
# Generator & Title Operations
# =============================================================================

def op_insert_generator(resolve, params):
    """Insert a generator into timeline."""
    generator_name = params.get("name", "")
    generator_type = params.get("type", "standard")  # standard, fusion, ofx
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = None
    if generator_type == "fusion":
        result = timeline.InsertFusionGeneratorIntoTimeline(generator_name)
    elif generator_type == "ofx":
        result = timeline.InsertOFXGeneratorIntoTimeline(generator_name)
    else:
        result = timeline.InsertGeneratorIntoTimeline(generator_name)
    
    if result:
        return success({"timeline_item": result.GetName() if result else generator_name})
    return error(f"Failed to insert generator: {generator_name}")


def op_insert_title(resolve, params):
    """Insert a title into timeline."""
    title_name = params.get("name", "")
    title_type = params.get("type", "standard")  # standard, fusion

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    if title_type == "fusion":
        result = timeline.InsertFusionTitleIntoTimeline(title_name)
    else:
        result = timeline.InsertTitleIntoTimeline(title_name)

    if result:
        return success({"timeline_item": result.GetName() if result else title_name})
    return error(f"Failed to insert title: {title_name}")


# =============================================================================
# Text+ Operations
# =============================================================================

def op_add_text_to_timeline(resolve, params):
    """Add a Text+ title with custom content at playhead."""
    text = params.get("text", "")
    duration = params.get("duration", 150)  # Default 5 seconds at 30fps
    style = params.get("style", {})

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    # Insert Text+ generator
    result = timeline.InsertFusionGeneratorIntoTimeline("Text+")
    if not result:
        return error("Failed to insert Text+ generator")

    try:
        # Get the Fusion composition
        comp = result.GetFusionCompByIndex(1)
        if not comp:
            return error("Could not get Fusion composition")

        # Find the Text+ tool in the composition
        text_tool = None
        for tool in comp.GetToolList().values():
            if tool.GetAttrs()["TOOL_Name"] == "Text+":
                text_tool = tool
                break

        if not text_tool:
            return error("Could not find Text+ tool in composition")

        # Set text content
        text_tool.SetInput("StyledText", text)

        # Apply styling if provided
        if style:
            # Font
            if "font" in style:
                text_tool.SetInput("Font", style["font"])

            # Size
            if "size" in style:
                text_tool.SetInput("Size", style["size"])

            # Color
            if "color" in style:
                c = style["color"]
                alpha = c.get("a", 1.0)
                text_tool.SetInput("Red1", c["r"])
                text_tool.SetInput("Green1", c["g"])
                text_tool.SetInput("Blue1", c["b"])
                text_tool.SetInput("Alpha1", alpha)

            # Bold/Italic
            if "bold" in style:
                text_tool.SetInput("Bold", style["bold"])
            if "italic" in style:
                text_tool.SetInput("Italic", style["italic"])

            # Tracking (letter spacing)
            if "tracking" in style:
                text_tool.SetInput("Tracking", style["tracking"])

            # Line spacing
            if "line_spacing" in style:
                text_tool.SetInput("LineSpacing", style["line_spacing"])

            # Horizontal anchor
            if "h_anchor" in style:
                h_anchor_map = {"left": 0, "center": 1, "right": 2}
                text_tool.SetInput("Center", h_anchor_map.get(style["h_anchor"], 1))

            # Vertical anchor
            if "v_anchor" in style:
                v_anchor_map = {"top": 0, "center": 1, "bottom": 2}
                text_tool.SetInput("VerticalAlignment", v_anchor_map.get(style["v_anchor"], 1))

            # Position
            if "position" in style:
                pos = style["position"]
                text_tool.SetInput("Center", {
                    1: pos["x"],
                    2: pos["y"],
                    3: 0
                })

            # Shading (outline/shadow)
            shading = style.get("shading", {})
            if shading:
                if "enabled" in shading:
                    text_tool.SetInput("ShadingEnabled", shading["enabled"])

                if "color" in shading:
                    sc = shading["color"]
                    sa = sc.get("a", 1.0)
                    text_tool.SetInput("Red2", sc["r"])
                    text_tool.SetInput("Green2", sc["g"])
                    text_tool.SetInput("Blue2", sc["b"])
                    text_tool.SetInput("Alpha2", sa)

                if "outline" in shading:
                    text_tool.SetInput("Outline", shading["outline"])

                if "shadow_offset" in shading:
                    shadow = shading["shadow_offset"]
                    text_tool.SetInput("ShadowOffset", {
                        1: shadow["x"],
                        2: shadow["y"],
                        3: 0
                    })

        # Set clip duration
        result.SetClipLength(duration)

        return success({
            "timeline_item": result.GetName() if result else "Text+",
            "text": text,
            "duration": duration
        })

    except Exception as e:
        return error(f"Failed to configure Text+: {e}")


def op_set_text_content(resolve, params):
    """Set text content on an existing Text+ clip."""
    selector = params.get("selector", {})
    text = params.get("text", "")

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    track = selector.get("track", 1)
    index = selector.get("index", 0)

    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")

    clip = items[index]

    try:
        # Get the Fusion composition
        comp = clip.GetFusionCompByIndex(1)
        if not comp:
            return error("Clip does not have a Fusion composition")

        # Find the Text+ tool
        text_tool = None
        for tool in comp.GetToolList().values():
            if tool.GetAttrs()["TOOL_Name"] == "Text+":
                text_tool = tool
                break

        if not text_tool:
            return error("Clip does not contain a Text+ tool")

        # Set text content
        text_tool.SetInput("StyledText", text)

        return success({"text_set": text})

    except Exception as e:
        return error(f"Failed to set text content: {e}")


def op_set_text_style(resolve, params):
    """Modify styling of an existing Text+ clip."""
    selector = params.get("selector", {})
    style = params.get("style", {})

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    track = selector.get("track", 1)
    index = selector.get("index", 0)

    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")

    clip = items[index]

    try:
        # Get the Fusion composition
        comp = clip.GetFusionCompByIndex(1)
        if not comp:
            return error("Clip does not have a Fusion composition")

        # Find the Text+ tool
        text_tool = None
        for tool in comp.GetToolList().values():
            if tool.GetAttrs()["TOOL_Name"] == "Text+":
                text_tool = tool
                break

        if not text_tool:
            return error("Clip does not contain a Text+ tool")

        # Apply styling
        modified = []

        # Font
        if "font" in style:
            text_tool.SetInput("Font", style["font"])
            modified.append("font")

        # Size
        if "size" in style:
            text_tool.SetInput("Size", style["size"])
            modified.append("size")

        # Color
        if "color" in style:
            c = style["color"]
            alpha = c.get("a", 1.0)
            text_tool.SetInput("Red1", c["r"])
            text_tool.SetInput("Green1", c["g"])
            text_tool.SetInput("Blue1", c["b"])
            text_tool.SetInput("Alpha1", alpha)
            modified.append("color")

        # Bold/Italic
        if "bold" in style:
            text_tool.SetInput("Bold", style["bold"])
            modified.append("bold")
        if "italic" in style:
            text_tool.SetInput("Italic", style["italic"])
            modified.append("italic")

        # Tracking
        if "tracking" in style:
            text_tool.SetInput("Tracking", style["tracking"])
            modified.append("tracking")

        # Line spacing
        if "line_spacing" in style:
            text_tool.SetInput("LineSpacing", style["line_spacing"])
            modified.append("line_spacing")

        # Horizontal anchor
        if "h_anchor" in style:
            h_anchor_map = {"left": 0, "center": 1, "right": 2}
            text_tool.SetInput("Center", h_anchor_map.get(style["h_anchor"], 1))
            modified.append("h_anchor")

        # Vertical anchor
        if "v_anchor" in style:
            v_anchor_map = {"top": 0, "center": 1, "bottom": 2}
            text_tool.SetInput("VerticalAlignment", v_anchor_map.get(style["v_anchor"], 1))
            modified.append("v_anchor")

        # Position
        if "position" in style:
            pos = style["position"]
            text_tool.SetInput("Center", {
                1: pos["x"],
                2: pos["y"],
                3: 0
            })
            modified.append("position")

        # Shading
        shading = style.get("shading", {})
        if shading:
            if "enabled" in shading:
                text_tool.SetInput("ShadingEnabled", shading["enabled"])
                modified.append("shading_enabled")

            if "color" in shading:
                sc = shading["color"]
                sa = sc.get("a", 1.0)
                text_tool.SetInput("Red2", sc["r"])
                text_tool.SetInput("Green2", sc["g"])
                text_tool.SetInput("Blue2", sc["b"])
                text_tool.SetInput("Alpha2", sa)
                modified.append("shading_color")

            if "outline" in shading:
                text_tool.SetInput("Outline", shading["outline"])
                modified.append("outline")

            if "shadow_offset" in shading:
                shadow = shading["shadow_offset"]
                text_tool.SetInput("ShadowOffset", {
                    1: shadow["x"],
                    2: shadow["y"],
                    3: 0
                })
                modified.append("shadow_offset")

        return success({"modified": modified})

    except Exception as e:
        return error(f"Failed to set text style: {e}")


def op_get_text_properties(resolve, params):
    """Get current text properties from a Text+ clip."""
    selector = params.get("selector", {})

    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")

    track = selector.get("track", 1)
    index = selector.get("index", 0)

    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")

    clip = items[index]

    try:
        # Get the Fusion composition
        comp = clip.GetFusionCompByIndex(1)
        if not comp:
            return error("Clip does not have a Fusion composition")

        # Find the Text+ tool
        text_tool = None
        for tool in comp.GetToolList().values():
            if tool.GetAttrs()["TOOL_Name"] == "Text+":
                text_tool = tool
                break

        if not text_tool:
            return error("Clip does not contain a Text+ tool")

        # Get properties
        properties = {
            "text": text_tool.GetInput("StyledText"),
            "font": text_tool.GetInput("Font"),
            "size": text_tool.GetInput("Size"),
            "color": {
                "r": text_tool.GetInput("Red1"),
                "g": text_tool.GetInput("Green1"),
                "b": text_tool.GetInput("Blue1"),
                "a": text_tool.GetInput("Alpha1")
            },
            "bold": text_tool.GetInput("Bold"),
            "italic": text_tool.GetInput("Italic"),
            "tracking": text_tool.GetInput("Tracking"),
            "line_spacing": text_tool.GetInput("LineSpacing"),
            "h_anchor": text_tool.GetInput("Center"),
            "v_anchor": text_tool.GetInput("VerticalAlignment"),
            "position": {
                "x": text_tool.GetInput("Center", 1),
                "y": text_tool.GetInput("Center", 2)
            },
            "shading": {
                "enabled": text_tool.GetInput("ShadingEnabled"),
                "color": {
                    "r": text_tool.GetInput("Red2"),
                    "g": text_tool.GetInput("Green2"),
                    "b": text_tool.GetInput("Blue2"),
                    "a": text_tool.GetInput("Alpha2")
                },
                "outline": text_tool.GetInput("Outline"),
                "shadow_offset": {
                    "x": text_tool.GetInput("ShadowOffset", 1),
                    "y": text_tool.GetInput("ShadowOffset", 2)
                }
            }
        }

        return success({"properties": properties})

    except Exception as e:
        return error(f"Failed to get text properties: {e}")


# =============================================================================
# Clip AI/Processing Operations
# =============================================================================

def op_stabilize_clip(resolve, params):
    """Stabilize a clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.Stabilize()
    if result:
        return success({"stabilized": True})
    return error("Failed to stabilize clip")


def op_smart_reframe(resolve, params):
    """Apply Smart Reframe to a clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.SmartReframe()
    if result:
        return success({"reframed": True})
    return error("Failed to apply Smart Reframe")


def op_create_magic_mask(resolve, params):
    """Create a Magic Mask on a clip."""
    selector = params.get("selector", {})
    mode = params.get("mode", "F")  # F=forward, B=backward, BI=bidirectional
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.CreateMagicMask(mode)
    if result:
        return success({"magic_mask_created": True, "mode": mode})
    return error("Failed to create Magic Mask")


def op_detect_scene_cuts(resolve, params):
    """Detect and create scene cuts in timeline."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.DetectSceneCuts()
    if result:
        return success({"scene_cuts_detected": True})
    return error("Failed to detect scene cuts")


# =============================================================================
# Clip Management Operations
# =============================================================================

def op_delete_clips(resolve, params):
    """Delete clips from timeline."""
    selector = params.get("selector", {})
    ripple = params.get("ripple", False)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    track_type = selector.get("track_type", "video")
    clips = []
    
    if selector.get("all"):
        items = timeline.GetItemListInTrack(track_type, track)
        if items:
            clips = list(items)
    elif "indices" in selector:
        items = timeline.GetItemListInTrack(track_type, track)
        if items:
            for idx in selector["indices"]:
                if 0 <= idx < len(items):
                    clips.append(items[idx])
    elif "index" in selector:
        items = timeline.GetItemListInTrack(track_type, track)
        if items and 0 <= selector["index"] < len(items):
            clips = [items[selector["index"]]]
    
    if not clips:
        return error("No clips selected")
    
    result = timeline.DeleteClips(clips, ripple)
    if result:
        return success({"deleted": len(clips), "ripple": ripple})
    return error("Failed to delete clips")


def op_set_clips_linked(resolve, params):
    """Link or unlink clips."""
    selector = params.get("selector", {})
    linked = params.get("linked", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    clips = []
    
    if "indices" in selector:
        items = timeline.GetItemListInTrack("video", track)
        if items:
            for idx in selector["indices"]:
                if 0 <= idx < len(items):
                    clips.append(items[idx])
    
    if not clips:
        return error("No clips selected (need at least 2)")
    
    result = timeline.SetClipsLinked(clips, linked)
    if result:
        return success({"linked": linked, "clips": len(clips)})
    return error("Failed to link/unlink clips")


def op_set_clip_enabled(resolve, params):
    """Enable or disable a clip."""
    selector = params.get("selector", {})
    enabled = params.get("enabled", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    track_type = selector.get("track_type", "video")
    modified = 0
    
    items = timeline.GetItemListInTrack(track_type, track)
    if not items:
        return error("No clips found")
    
    if selector.get("all"):
        for item in items:
            if item.SetClipEnabled(enabled):
                modified += 1
    elif "index" in selector:
        idx = selector["index"]
        if 0 <= idx < len(items):
            if items[idx].SetClipEnabled(enabled):
                modified = 1
    elif "name" in selector:
        for item in items:
            if item.GetName() == selector["name"]:
                if item.SetClipEnabled(enabled):
                    modified += 1
    
    return success({"modified": modified, "enabled": enabled})


def op_set_clip_color(resolve, params):
    """Set clip color label."""
    selector = params.get("selector", {})
    color = params.get("color", "")  # Orange, Apricot, Yellow, Lime, Olive, Green, Teal, Navy, Blue, Purple, Violet, Pink, Tan, Beige, Brown, Chocolate
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    track_type = selector.get("track_type", "video")
    modified = 0
    
    items = timeline.GetItemListInTrack(track_type, track)
    if not items:
        return error("No clips found")
    
    if selector.get("all"):
        for item in items:
            if color:
                if item.SetClipColor(color):
                    modified += 1
            else:
                if item.ClearClipColor():
                    modified += 1
    elif "index" in selector:
        idx = selector["index"]
        if 0 <= idx < len(items):
            if color:
                if items[idx].SetClipColor(color):
                    modified = 1
            else:
                if items[idx].ClearClipColor():
                    modified = 1
    elif "name" in selector:
        for item in items:
            if item.GetName() == selector["name"]:
                if color:
                    if item.SetClipColor(color):
                        modified += 1
                else:
                    if item.ClearClipColor():
                        modified += 1
    
    return success({"modified": modified, "color": color if color else "cleared"})


# =============================================================================
# Timeline Playhead & Navigation
# =============================================================================

def op_set_current_timecode(resolve, params):
    """Set the playhead position."""
    timecode = params.get("timecode", "00:00:00:00")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.SetCurrentTimecode(timecode)
    if result:
        return success({"timecode": timecode})
    return error(f"Failed to set timecode to {timecode}")


def op_get_current_timecode(resolve, params):
    """Get current playhead position."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    timecode = timeline.GetCurrentTimecode()
    return success({"timecode": timecode})


# =============================================================================
# Audio Operations
# =============================================================================

def op_create_subtitles_from_audio(resolve, params):
    """Create subtitles from audio using auto-captioning."""
    language = params.get("language", "auto")  # auto, english, spanish, french, etc.
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Map language names to API constants (would need resolve object)
    settings = {}
    # For now, use defaults
    
    result = timeline.CreateSubtitlesFromAudio(settings)
    if result:
        return success({"subtitles_created": True})
    return error("Failed to create subtitles from audio")


# =============================================================================
# Page Navigation
# =============================================================================

def op_open_page(resolve, params):
    """Switch to a specific Resolve page."""
    page = params.get("page", "edit")  # media, cut, edit, fusion, color, fairlight, deliver
    
    if resolve is None:
        return error("DaVinci Resolve is not running", "RESOLVE_NOT_RUNNING")
    
    result = resolve.OpenPage(page)
    if result:
        return success({"page": page})
    return error(f"Failed to open page: {page}")


def op_get_current_page(resolve, params):
    """Get the currently active page."""
    if resolve is None:
        return error("DaVinci Resolve is not running", "RESOLVE_NOT_RUNNING")
    
    page = resolve.GetCurrentPage()
    return success({"page": page})


# =============================================================================
# Grab Still
# =============================================================================

def op_grab_still(resolve, params):
    """Grab a still from the current frame."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    still = timeline.GrabStill()
    if still:
        return success({"still_grabbed": True})
    return error("Failed to grab still")


# =============================================================================
# Delete Track
# =============================================================================

def op_delete_track(resolve, params):
    """Delete a track from the timeline."""
    track_type = params.get("type", "video")
    index = params.get("index", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.DeleteTrack(track_type, index)
    if result:
        return success({"deleted": True, "type": track_type, "index": index})
    return error(f"Failed to delete {track_type} track {index}")


# =============================================================================
# Color Grading Operations
# =============================================================================

def op_apply_lut(resolve, params):
    """Apply LUT to a clip's node."""
    selector = params.get("selector", {})
    lut_path = params.get("lut_path", "")
    node_index = params.get("node_index", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    graph = clip.GetNodeGraph()
    if not graph:
        return error("Could not get node graph")
    
    result = graph.SetLUT(node_index, lut_path)
    if result:
        return success({"lut_applied": True, "path": lut_path, "node": node_index})
    return error(f"Failed to apply LUT: {lut_path}")


def op_get_lut(resolve, params):
    """Get LUT path from a clip's node."""
    selector = params.get("selector", {})
    node_index = params.get("node_index", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    graph = clip.GetNodeGraph()
    if not graph:
        return error("Could not get node graph")
    
    lut_path = graph.GetLUT(node_index)
    return success({"lut_path": lut_path, "node": node_index})


def op_set_cdl(resolve, params):
    """Set CDL values on a clip."""
    selector = params.get("selector", {})
    node_index = params.get("node_index", 1)
    slope = params.get("slope", "1.0 1.0 1.0")
    offset = params.get("offset", "0.0 0.0 0.0")
    power = params.get("power", "1.0 1.0 1.0")
    saturation = params.get("saturation", "1.0")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    cdl_map = {
        "NodeIndex": str(node_index),
        "Slope": slope,
        "Offset": offset,
        "Power": power,
        "Saturation": saturation
    }
    
    result = clip.SetCDL(cdl_map)
    if result:
        return success({"cdl_set": True, "node": node_index})
    return error("Failed to set CDL values")


def op_copy_grades(resolve, params):
    """Copy grades from one clip to others."""
    source_selector = params.get("source", {})
    target_selector = params.get("targets", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Get source clip
    source_track = source_selector.get("track", 1)
    source_index = source_selector.get("index", 0)
    
    source_items = timeline.GetItemListInTrack("video", source_track)
    if not source_items or source_index >= len(source_items):
        return error("Source clip not found")
    
    source_clip = source_items[source_index]
    
    # Get target clips
    target_track = target_selector.get("track", 1)
    target_clips = []
    
    if target_selector.get("all"):
        items = timeline.GetItemListInTrack("video", target_track)
        if items:
            target_clips = [item for item in items if item != source_clip]
    elif "indices" in target_selector:
        items = timeline.GetItemListInTrack("video", target_track)
        if items:
            for idx in target_selector["indices"]:
                if 0 <= idx < len(items) and items[idx] != source_clip:
                    target_clips.append(items[idx])
    
    if not target_clips:
        return error("No target clips found")
    
    result = source_clip.CopyGrades(target_clips)
    if result:
        return success({"copied_to": len(target_clips)})
    return error("Failed to copy grades")


def op_reset_grades(resolve, params):
    """Reset all grades on a clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    graph = clip.GetNodeGraph()
    if not graph:
        return error("Could not get node graph")
    
    result = graph.ResetAllGrades()
    if result:
        return success({"grades_reset": True})
    return error("Failed to reset grades")


def op_add_color_version(resolve, params):
    """Add a new color version to a clip."""
    selector = params.get("selector", {})
    version_name = params.get("name", "Version")
    version_type = params.get("type", 0)  # 0=local, 1=remote
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.AddVersion(version_name, version_type)
    if result:
        return success({"version_added": version_name, "type": "local" if version_type == 0 else "remote"})
    return error(f"Failed to add color version: {version_name}")


def op_load_color_version(resolve, params):
    """Load a color version on a clip."""
    selector = params.get("selector", {})
    version_name = params.get("name", "")
    version_type = params.get("type", 0)  # 0=local, 1=remote
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.LoadVersionByName(version_name, version_type)
    if result:
        return success({"version_loaded": version_name})
    return error(f"Failed to load color version: {version_name}")


def op_get_color_versions(resolve, params):
    """Get list of color versions for a clip."""
    selector = params.get("selector", {})
    version_type = params.get("type", 0)  # 0=local, 1=remote
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    versions = clip.GetVersionNameList(version_type)
    current = clip.GetCurrentVersion()
    
    return success({
        "versions": versions or [],
        "current": current,
        "type": "local" if version_type == 0 else "remote"
    })


def op_delete_color_version(resolve, params):
    """Delete a color version from a clip."""
    selector = params.get("selector", {})
    version_name = params.get("name", "")
    version_type = params.get("type", 0)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.DeleteVersionByName(version_name, version_type)
    if result:
        return success({"version_deleted": version_name})
    return error(f"Failed to delete color version: {version_name}")


# =============================================================================
# Color Group Operations
# =============================================================================

def op_create_color_group(resolve, params):
    """Create a new color group."""
    name = params.get("name", "Color Group")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.AddColorGroup(name)
    if result:
        return success({"color_group_created": name})
    return error(f"Failed to create color group: {name}")


def op_get_color_groups(resolve, params):
    """Get list of color groups."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    groups = project.GetColorGroupsList()
    group_names = [g.GetName() for g in groups] if groups else []
    
    return success({"color_groups": group_names})


def op_assign_to_color_group(resolve, params):
    """Assign a clip to a color group."""
    selector = params.get("selector", {})
    group_name = params.get("group", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Find the color group
    groups = project.GetColorGroupsList()
    target_group = None
    if groups:
        for g in groups:
            if g.GetName() == group_name:
                target_group = g
                break
    
    if not target_group:
        return error(f"Color group not found: {group_name}")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.AssignToColorGroup(target_group)
    if result:
        return success({"assigned_to": group_name})
    return error(f"Failed to assign clip to color group: {group_name}")


def op_remove_from_color_group(resolve, params):
    """Remove a clip from its color group."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.RemoveFromColorGroup()
    if result:
        return success({"removed_from_group": True})
    return error("Failed to remove clip from color group")


def op_delete_color_group(resolve, params):
    """Delete a color group."""
    name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    groups = project.GetColorGroupsList()
    target_group = None
    if groups:
        for g in groups:
            if g.GetName() == name:
                target_group = g
                break
    
    if not target_group:
        return error(f"Color group not found: {name}")
    
    result = project.DeleteColorGroup(target_group)
    if result:
        return success({"color_group_deleted": name})
    return error(f"Failed to delete color group: {name}")


# =============================================================================
# Media Pool Operations
# =============================================================================

def op_create_media_pool_folder(resolve, params):
    """Create a folder in the media pool."""
    name = params.get("name", "New Folder")
    parent = params.get("parent", None)  # None = current folder
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    
    if parent:
        # Find parent folder
        root = media_pool.GetRootFolder()
        folders = root.GetSubFolderList() or []
        target_folder = None
        for f in folders:
            if f.GetName() == parent:
                target_folder = f
                break
        if not target_folder:
            target_folder = media_pool.GetCurrentFolder()
    else:
        target_folder = media_pool.GetCurrentFolder()
    
    result = media_pool.AddSubFolder(target_folder, name)
    if result:
        return success({"folder_created": name})
    return error(f"Failed to create folder: {name}")


def op_set_current_media_pool_folder(resolve, params):
    """Set the current media pool folder."""
    name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    if not name or name == "Root":
        media_pool.SetCurrentFolder(root)
        return success({"current_folder": "Root"})
    
    # Find folder
    folders = root.GetSubFolderList() or []
    for f in folders:
        if f.GetName() == name:
            media_pool.SetCurrentFolder(f)
            return success({"current_folder": name})
    
    return error(f"Folder not found: {name}")


def op_move_media_pool_clips(resolve, params):
    """Move clips between media pool folders."""
    clip_names = params.get("clips", [])
    target_folder = params.get("target_folder", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    # Find target folder
    target = None
    if not target_folder or target_folder == "Root":
        target = root
    else:
        folders = root.GetSubFolderList() or []
        for f in folders:
            if f.GetName() == target_folder:
                target = f
                break
    
    if not target:
        return error(f"Target folder not found: {target_folder}")
    
    # Find clips
    clips_to_move = []
    all_clips = root.GetClipList() or []
    for clip in all_clips:
        if clip.GetName() in clip_names:
            clips_to_move.append(clip)
    
    if not clips_to_move:
        return error("No clips found to move")
    
    result = media_pool.MoveClips(clips_to_move, target)
    if result:
        return success({"moved": len(clips_to_move), "to": target_folder or "Root"})
    return error("Failed to move clips")


def op_delete_media_pool_clips(resolve, params):
    """Delete clips from media pool."""
    clip_names = params.get("clips", [])
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    clips_to_delete = []
    all_clips = root.GetClipList() or []
    for clip in all_clips:
        if clip.GetName() in clip_names:
            clips_to_delete.append(clip)
    
    if not clips_to_delete:
        return error("No clips found to delete")
    
    result = media_pool.DeleteClips(clips_to_delete)
    if result:
        return success({"deleted": len(clips_to_delete)})
    return error("Failed to delete clips from media pool")


def op_set_clip_metadata(resolve, params):
    """Set metadata on a media pool clip."""
    clip_name = params.get("clip", "")
    metadata = params.get("metadata", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    target_clip = None
    all_clips = root.GetClipList() or []
    for clip in all_clips:
        if clip.GetName() == clip_name:
            target_clip = clip
            break
    
    if not target_clip:
        return error(f"Clip not found: {clip_name}")
    
    result = target_clip.SetMetadata(metadata)
    if result:
        return success({"metadata_set": True, "clip": clip_name})
    return error("Failed to set metadata")


def op_get_clip_metadata(resolve, params):
    """Get metadata from a media pool clip."""
    clip_name = params.get("clip", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    target_clip = None
    all_clips = root.GetClipList() or []
    for clip in all_clips:
        if clip.GetName() == clip_name:
            target_clip = clip
            break
    
    if not target_clip:
        return error(f"Clip not found: {clip_name}")
    
    metadata = target_clip.GetMetadata()
    return success({"metadata": metadata or {}, "clip": clip_name})


def op_relink_clips(resolve, params):
    """Relink offline clips to a new folder path."""
    clip_names = params.get("clips", [])
    folder_path = params.get("folder_path", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    clips_to_relink = []
    all_clips = root.GetClipList() or []
    for clip in all_clips:
        if clip.GetName() in clip_names:
            clips_to_relink.append(clip)
    
    if not clips_to_relink:
        return error("No clips found to relink")
    
    result = media_pool.RelinkClips(clips_to_relink, folder_path)
    if result:
        return success({"relinked": len(clips_to_relink), "path": folder_path})
    return error("Failed to relink clips")


def op_delete_media_pool_folders(resolve, params):
    """Delete folders from media pool."""
    folder_names = params.get("folders", [])
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    
    folders_to_delete = []
    all_folders = root.GetSubFolderList() or []
    for folder in all_folders:
        if folder.GetName() in folder_names:
            folders_to_delete.append(folder)
    
    if not folders_to_delete:
        return error("No folders found to delete")
    
    result = media_pool.DeleteFolders(folders_to_delete)
    if result:
        return success({"deleted": len(folders_to_delete)})
    return error("Failed to delete folders")


# =============================================================================
# Flag Operations
# =============================================================================

def op_add_flag(resolve, params):
    """Add a flag to a timeline clip."""
    selector = params.get("selector", {})
    color = params.get("color", "Red")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    track_type = selector.get("track_type", "video")
    modified = 0
    
    items = timeline.GetItemListInTrack(track_type, track)
    if not items:
        return error("No clips found")
    
    if selector.get("all"):
        for item in items:
            if item.AddFlag(color):
                modified += 1
    elif "index" in selector:
        idx = selector["index"]
        if 0 <= idx < len(items):
            if items[idx].AddFlag(color):
                modified = 1
    
    return success({"flags_added": modified, "color": color})


def op_get_flags(resolve, params):
    """Get flags from a timeline clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    flags = items[index].GetFlagList()
    return success({"flags": flags or []})


def op_clear_flags(resolve, params):
    """Clear flags from a timeline clip."""
    selector = params.get("selector", {})
    color = params.get("color", "All")  # specific color or "All"
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    track_type = selector.get("track_type", "video")
    modified = 0
    
    items = timeline.GetItemListInTrack(track_type, track)
    if not items:
        return error("No clips found")
    
    if selector.get("all"):
        for item in items:
            if item.ClearFlags(color):
                modified += 1
    elif "index" in selector:
        idx = selector["index"]
        if 0 <= idx < len(items):
            if items[idx].ClearFlags(color):
                modified = 1
    
    return success({"flags_cleared": modified, "color": color})


# =============================================================================
# Take Operations
# =============================================================================

def op_add_take(resolve, params):
    """Add a take to a timeline clip."""
    selector = params.get("selector", {})
    media_pool_clip = params.get("media_pool_clip", "")
    start_frame = params.get("start_frame", None)
    end_frame = params.get("end_frame", None)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Find media pool clip
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    mp_clip = None
    for clip in root.GetClipList() or []:
        if clip.GetName() == media_pool_clip:
            mp_clip = clip
            break
    
    if not mp_clip:
        return error(f"Media pool clip not found: {media_pool_clip}")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    
    if start_frame is not None and end_frame is not None:
        result = clip.AddTake(mp_clip, start_frame, end_frame)
    else:
        result = clip.AddTake(mp_clip)
    
    if result:
        return success({"take_added": True, "media": media_pool_clip})
    return error("Failed to add take")


def op_select_take(resolve, params):
    """Select a take on a timeline clip."""
    selector = params.get("selector", {})
    take_index = params.get("take_index", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.SelectTakeByIndex(take_index)
    if result:
        return success({"take_selected": take_index})
    return error(f"Failed to select take {take_index}")


def op_get_takes(resolve, params):
    """Get takes info for a timeline clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    takes_count = clip.GetTakesCount()
    selected = clip.GetSelectedTakeIndex()
    
    takes = []
    for i in range(1, takes_count + 1):
        take_info = clip.GetTakeByIndex(i)
        if take_info:
            takes.append({
                "index": i,
                "start_frame": take_info.get("startFrame"),
                "end_frame": take_info.get("endFrame")
            })
    
    return success({"takes": takes, "selected": selected, "count": takes_count})


def op_finalize_take(resolve, params):
    """Finalize take selection on a clip."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.FinalizeTake()
    if result:
        return success({"take_finalized": True})
    return error("Failed to finalize take")


def op_delete_take(resolve, params):
    """Delete a take from a clip."""
    selector = params.get("selector", {})
    take_index = params.get("take_index", 1)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    result = clip.DeleteTakeByIndex(take_index)
    if result:
        return success({"take_deleted": take_index})
    return error(f"Failed to delete take {take_index}")


# =============================================================================
# Timeline Import
# =============================================================================

def op_import_timeline_from_file(resolve, params):
    """Import timeline from AAF/EDL/XML/FCPXML file."""
    file_path = params.get("path", "")
    timeline_name = params.get("name", None)
    import_source_clips = params.get("import_source_clips", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    media_pool = project.GetMediaPool()
    
    import_options = {
        "importSourceClips": import_source_clips,
    }
    if timeline_name:
        import_options["timelineName"] = timeline_name
    
    result = media_pool.ImportTimelineFromFile(file_path, import_options)
    if result:
        return success({"timeline_imported": result.GetName() if result else timeline_name or file_path})
    return error(f"Failed to import timeline from: {file_path}")


# =============================================================================
# Enhanced Render Operations
# =============================================================================

def op_set_render_settings(resolve, params):
    """Set detailed render settings."""
    settings = params.get("settings", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.SetRenderSettings(settings)
    if result:
        return success({"settings_applied": True})
    return error("Failed to set render settings")


def op_get_render_formats(resolve, params):
    """Get available render formats."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    formats = project.GetRenderFormats()
    return success({"formats": formats or {}})


def op_get_render_codecs(resolve, params):
    """Get available codecs for a render format."""
    format_name = params.get("format", "mp4")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    codecs = project.GetRenderCodecs(format_name)
    return success({"codecs": codecs or {}, "format": format_name})


def op_set_render_format_and_codec(resolve, params):
    """Set render format and codec."""
    format_name = params.get("format", "mp4")
    codec = params.get("codec", "H264")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.SetCurrentRenderFormatAndCodec(format_name, codec)
    if result:
        return success({"format": format_name, "codec": codec})
    return error(f"Failed to set format/codec: {format_name}/{codec}")


def op_get_render_presets(resolve, params):
    """Get available render presets."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    presets = project.GetRenderPresetList()
    return success({"presets": presets or []})


def op_load_render_preset(resolve, params):
    """Load a render preset."""
    preset_name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.LoadRenderPreset(preset_name)
    if result:
        return success({"preset_loaded": preset_name})
    return error(f"Failed to load render preset: {preset_name}")


def op_save_render_preset(resolve, params):
    """Save current render settings as a preset."""
    preset_name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.SaveAsNewRenderPreset(preset_name)
    if result:
        return success({"preset_saved": preset_name})
    return error(f"Failed to save render preset: {preset_name}")


def op_delete_render_preset(resolve, params):
    """Delete a render preset."""
    preset_name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.DeleteRenderPreset(preset_name)
    if result:
        return success({"preset_deleted": preset_name})
    return error(f"Failed to delete render preset: {preset_name}")


def op_get_render_jobs(resolve, params):
    """Get list of render jobs in queue."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    jobs = project.GetRenderJobList()
    return success({"jobs": jobs or []})


def op_delete_render_job(resolve, params):
    """Delete a render job."""
    job_id = params.get("job_id", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.DeleteRenderJob(job_id)
    if result:
        return success({"job_deleted": job_id})
    return error(f"Failed to delete render job: {job_id}")


def op_delete_all_render_jobs(resolve, params):
    """Delete all render jobs."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.DeleteAllRenderJobs()
    if result:
        return success({"all_jobs_deleted": True})
    return error("Failed to delete all render jobs")


def op_get_render_job_status(resolve, params):
    """Get status of a render job."""
    job_id = params.get("job_id", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    status = project.GetRenderJobStatus(job_id)
    return success({"status": status or {}})


# =============================================================================
# Project Operations
# =============================================================================

def op_save_project(resolve, params):
    """Save the current project."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    pm = resolve.GetProjectManager()
    result = pm.SaveProject()
    if result:
        return success({"saved": True, "project": project.GetName()})
    return error("Failed to save project")


def op_export_project(resolve, params):
    """Export project to .drp file."""
    file_path = params.get("path", "")
    with_stills_and_luts = params.get("with_stills_and_luts", True)
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    pm = resolve.GetProjectManager()
    result = pm.ExportProject(project.GetName(), file_path, with_stills_and_luts)
    if result:
        return success({"exported": True, "path": file_path})
    return error(f"Failed to export project to: {file_path}")


def op_get_project_setting(resolve, params):
    """Get a project setting."""
    setting_name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    if setting_name:
        value = project.GetSetting(setting_name)
        return success({"setting": setting_name, "value": value})
    else:
        # Get all settings
        settings = project.GetSetting()
        return success({"settings": settings or {}})


def op_set_project_setting(resolve, params):
    """Set a project setting."""
    setting_name = params.get("name", "")
    setting_value = params.get("value", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.SetSetting(setting_name, setting_value)
    if result:
        return success({"setting": setting_name, "value": setting_value})
    return error(f"Failed to set project setting: {setting_name}")


def op_get_timeline_setting(resolve, params):
    """Get a timeline setting."""
    setting_name = params.get("name", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    if setting_name:
        value = timeline.GetSetting(setting_name)
        return success({"setting": setting_name, "value": value})
    else:
        settings = timeline.GetSetting()
        return success({"settings": settings or {}})


def op_set_timeline_setting(resolve, params):
    """Set a timeline setting."""
    setting_name = params.get("name", "")
    setting_value = params.get("value", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    result = timeline.SetSetting(setting_name, setting_value)
    if result:
        return success({"setting": setting_name, "value": setting_value})
    return error(f"Failed to set timeline setting: {setting_name}")


# =============================================================================
# Keyframe Mode
# =============================================================================

def op_set_keyframe_mode(resolve, params):
    """Set the keyframe mode."""
    mode = params.get("mode", 0)  # 0=All, 1=Color, 2=Sizing
    
    if resolve is None:
        return error("DaVinci Resolve is not running", "RESOLVE_NOT_RUNNING")
    
    result = resolve.SetKeyframeMode(mode)
    mode_names = {0: "All", 1: "Color", 2: "Sizing"}
    if result:
        return success({"keyframe_mode": mode_names.get(mode, str(mode))})
    return error("Failed to set keyframe mode")


def op_get_keyframe_mode(resolve, params):
    """Get the current keyframe mode."""
    if resolve is None:
        return error("DaVinci Resolve is not running", "RESOLVE_NOT_RUNNING")
    
    mode = resolve.GetKeyframeMode()
    mode_names = {0: "All", 1: "Color", 2: "Sizing"}
    return success({"keyframe_mode": mode_names.get(mode, str(mode)), "value": mode})


# =============================================================================
# Gallery & Stills
# =============================================================================

def op_export_still(resolve, params):
    """Export current frame as a still image."""
    file_path = params.get("path", "")
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.ExportCurrentFrameAsStill(file_path)
    if result:
        return success({"exported": True, "path": file_path})
    return error(f"Failed to export still to: {file_path}")


def op_apply_grade_from_drx(resolve, params):
    """Apply grade from a DRX file."""
    selector = params.get("selector", {})
    drx_path = params.get("path", "")
    grade_mode = params.get("grade_mode", 0)  # 0=No keyframes, 1=Source timecode, 2=Start frames
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    graph = clip.GetNodeGraph()
    if not graph:
        return error("Could not get node graph")
    
    result = graph.ApplyGradeFromDRX(drx_path, grade_mode)
    if result:
        return success({"grade_applied": True, "path": drx_path})
    return error(f"Failed to apply grade from: {drx_path}")


def op_get_gallery_albums(resolve, params):
    """Get list of gallery albums."""
    album_type = params.get("type", "stills")  # stills or powergrade
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    gallery = project.GetGallery()
    if not gallery:
        return error("Could not get gallery")
    
    if album_type == "powergrade":
        albums = gallery.GetGalleryPowerGradeAlbums()
    else:
        albums = gallery.GetGalleryStillAlbums()
    
    album_names = []
    if albums:
        for album in albums:
            album_names.append(gallery.GetAlbumName(album))
    
    return success({"albums": album_names, "type": album_type})


# =============================================================================
# Cache Operations
# =============================================================================

def op_set_clip_cache_mode(resolve, params):
    """Set clip render cache mode."""
    selector = params.get("selector", {})
    cache_type = params.get("cache_type", "color")  # color or fusion
    enabled = params.get("enabled", True)  # or "auto" for fusion
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    
    if cache_type == "fusion":
        # Fusion cache can be "auto", True, or False
        result = clip.SetFusionOutputCache(enabled)
    else:
        result = clip.SetColorOutputCache(enabled)
    
    if result:
        return success({"cache_set": True, "type": cache_type, "enabled": enabled})
    return error(f"Failed to set {cache_type} cache mode")


def op_get_clip_cache_mode(resolve, params):
    """Get clip render cache mode."""
    selector = params.get("selector", {})
    
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    track = selector.get("track", 1)
    index = selector.get("index", 0)
    
    items = timeline.GetItemListInTrack("video", track)
    if not items or index >= len(items):
        return error("Clip not found")
    
    clip = items[index]
    
    color_cache = clip.GetIsColorOutputCacheEnabled()
    fusion_cache = clip.GetIsFusionOutputCacheEnabled()
    
    return success({
        "color_cache_enabled": color_cache,
        "fusion_cache_enabled": fusion_cache
    })


def op_refresh_lut_list(resolve, params):
    """Refresh the LUT list."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    result = project.RefreshLUTList()
    if result:
        return success({"lut_list_refreshed": True})
    return error("Failed to refresh LUT list")


# =============================================================================
# Beat Detection Operations
# =============================================================================

def ensure_audio_deps():
    """Check and import audio dependencies.
    
    Checks for BeatNet (accurate neural network beat/downbeat detection).
    Falls back to librosa if BeatNet not available.
    Returns (BeatNet_class_or_None, librosa).
    """
    beatnet_class = None
    librosa = None
    
    # Check for BeatNet (accurate downbeat detection)
    try:
        from BeatNet.BeatNet import BeatNet
        beatnet_class = BeatNet
    except ImportError:
        print("BeatNet not installed. Will use librosa fallback (less accurate).", file=sys.stderr)
        print("For accurate beat detection, install: pip install BeatNet", file=sys.stderr)
    
    # Check librosa (required for fallback and audio loading)
    try:
        import librosa
    except ImportError:
        raise RuntimeError(
            "Missing required dependency: librosa\n\n"
            "Please install dependencies:\n"
            "  pip install librosa\n\n"
            "For accurate beat detection (recommended):\n"
            "  pip install 'numpy<2.0' cython\n"
            "  pip install git+https://github.com/CPJKU/madmom.git\n"
            "  pip install BeatNet librosa pyaudio\n\n"
            "Then set python_path in ~/.config/magic-agent/config.toml:\n"
            "  [resolve]\n"
            "  python_path = \"~/.magic-agent-venv/bin/python\""
        )
    
    return beatnet_class, librosa


def get_clip_file_path(timeline_item):
    """Get source file path from a timeline item."""
    try:
        media_pool_item = timeline_item.GetMediaPoolItem()
        if not media_pool_item:
            return None
        return media_pool_item.GetClipProperty("File Path")
    except Exception:
        return None


def get_clip_source_offset(timeline_item):
    """Get the source in-point offset for a timeline item.
    
    Returns the frame offset into the source media where this clip starts.
    This is needed to correctly map beat timestamps when a clip is trimmed.
    """
    try:
        # GetLeftOffset returns how many frames from source start the clip begins
        left_offset = timeline_item.GetLeftOffset()
        return left_offset if left_offset else 0
    except Exception:
        return 0


def op_detect_beats(resolve, params):
    """Detect beats in audio and add markers to clips.
    
    Uses BeatNet (neural network) for accurate beat/downbeat detection.
    Falls back to librosa if BeatNet is not installed.
    
    Adds markers directly to clips:
    - Red markers: Downbeats (first beat of each bar)
    - Blue markers: Regular beats (if enabled)
    """
    track = params.get("track", 1)
    track_type = params.get("track_type", "audio")
    mark_beats = params.get("mark_beats", False)  # Regular beats off by default
    mark_downbeats = params.get("mark_downbeats", True)  # Bar starts (default)
    
    # Get project and timeline
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return error("No project is open", "NO_PROJECT")
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return error("No timeline is active", "NO_TIMELINE")
    
    # Get timeline FPS
    settings = timeline.GetSetting()
    fps = float(settings.get("timelineFrameRate", 24))
    
    # Get clips on track
    items = timeline.GetItemListInTrack(track_type, track)
    if not items:
        return error(f"No clips on {track_type} track {track}", "NO_CLIPS")
    
    # Check dependencies
    try:
        BeatNetClass, librosa = ensure_audio_deps()
    except Exception as e:
        return error(f"{e}", "DEPS_FAILED")
    
    markers_added = {"beats": 0, "downbeats": 0}
    processed_clips = 0
    skipped_clips = []
    using_beatnet = BeatNetClass is not None

    def record_marker(frame_markers, counters, clip_frame, color, name, note):
        existing = frame_markers.get(clip_frame)
        if existing:
            if existing["color"] == color:
                return
            if existing["color"] == "Red" and color != "Red":
                return
            if existing["color"] == "Blue" and color == "Red":
                counters["beats"] = max(0, counters["beats"] - 1)
        if color == "Red":
            counters["downbeats"] += 1
        else:
            counters["beats"] += 1
        frame_markers[clip_frame] = {
            "color": color,
            "name": name,
            "note": note
        }
    
    for item in items:
        clip_name = item.GetName()
        file_path = get_clip_file_path(item)
        
        if not file_path:
            skipped_clips.append({"name": clip_name, "reason": "no file path"})
            continue
        
        if not os.path.exists(file_path):
            skipped_clips.append({"name": clip_name, "reason": "file not found"})
            continue
        
        # Get clip timing info
        source_offset = get_clip_source_offset(item)  # Source frame offset (in-point)
        clip_duration = item.GetDuration()  # Clip duration in frames
        
        # Calculate source in/out in seconds for analysis bounds
        source_in_sec = source_offset / fps
        source_out_sec = (source_offset + clip_duration) / fps
        
        try:
            print(f"Analyzing audio: {clip_name}", file=sys.stderr)
            
            # Dictionary to collect markers by CLIP-RELATIVE frame
            frame_markers = {}
            
            if using_beatnet:
                # Use BeatNet for accurate beat/downbeat detection
                print("Using BeatNet (neural network) for beat detection", file=sys.stderr)
                estimator = BeatNetClass(
                    1,  # Model number
                    mode='offline',
                    inference_model='DBN',
                    plot=[]  # No plotting
                )
                
                # BeatNet.process returns numpy array: [[time, beat_position], ...]
                # beat_position: 1 = downbeat, 2/3/4 = other beats in bar
                output = estimator.process(file_path)
                
                if output is not None and len(output) > 0:
                    for beat_time, beat_pos in output:
                        # Skip beats outside the clip's source range
                        if beat_time < source_in_sec or beat_time >= source_out_sec:
                            continue
                        
                        # Calculate clip-relative frame (0-based from clip start)
                        source_frame = beat_time * fps
                        clip_frame = int(source_frame - source_offset)
                        
                        # Ensure frame is within clip bounds
                        if clip_frame < 0 or clip_frame >= clip_duration:
                            continue
                        
                        is_downbeat = (int(beat_pos) == 1)
                        
                        if is_downbeat and mark_downbeats:
                            record_marker(
                                frame_markers,
                                markers_added,
                                clip_frame,
                                "Red",
                                "Downbeat",
                                "Bar start"
                            )
                        elif mark_beats:
                            record_marker(
                                frame_markers,
                                markers_added,
                                clip_frame,
                                "Blue",
                                "Beat",
                                f"Beat {int(beat_pos)}"
                            )
            else:
                # Fallback: Use librosa beat_track (less accurate)
                print("Using librosa fallback (less accurate)", file=sys.stderr)
                segment_offset = source_in_sec
                segment_duration = source_out_sec - source_in_sec
                if segment_duration <= 0:
                    skipped_clips.append({"name": clip_name, "reason": "zero duration"})
                    continue
                y, sr = librosa.load(
                    file_path,
                    sr=22050,
                    offset=segment_offset,
                    duration=segment_duration
                )
                tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
                beat_times = librosa.frames_to_time(beat_frames, sr=sr)

                for i, beat_time in enumerate(beat_times):
                    beat_time += segment_offset
                    # Skip beats outside the clip's source range
                    if beat_time < source_in_sec or beat_time >= source_out_sec:
                        continue
                    
                    # Calculate clip-relative frame
                    source_frame = beat_time * fps
                    clip_frame = int(source_frame - source_offset)
                    
                    # Ensure frame is within clip bounds
                    if clip_frame < 0 or clip_frame >= clip_duration:
                        continue
                    
                    # Estimate downbeats (every 4 beats) - not accurate
                    is_downbeat = (i % 4 == 0)
                    
                    if is_downbeat and mark_downbeats:
                        record_marker(
                            frame_markers,
                            markers_added,
                            clip_frame,
                            "Red",
                            "Downbeat",
                            "Bar start (estimated)"
                        )
                    elif mark_beats:
                        record_marker(
                            frame_markers,
                            markers_added,
                            clip_frame,
                            "Blue",
                            "Beat",
                            f"Beat {(i % 4) + 1}"
                        )
            
            # Add all markers to the CLIP
            for frame, marker_info in frame_markers.items():
                result = item.AddMarker(
                    frame,
                    marker_info["color"],
                    marker_info["name"],
                    marker_info["note"],
                    1  # duration
                )
                if not result:
                    print(f"Failed to add marker at frame {frame}", file=sys.stderr)
            
            processed_clips += 1
            print(f"Added {len(frame_markers)} markers to {clip_name}", file=sys.stderr)
            
        except Exception as e:
            skipped_clips.append({"name": clip_name, "reason": str(e)})
            print(f"Failed to process {clip_name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
    
    total = markers_added["beats"] + markers_added["downbeats"]
    
    return success({
        "markers_added": total,
        "beats": markers_added["beats"],
        "downbeats": markers_added["downbeats"],
        "clips_processed": processed_clips,
        "clips_skipped": skipped_clips if skipped_clips else None,
        "engine": "BeatNet" if using_beatnet else "librosa"
    })


def op_check_audio_deps(resolve, params):
    """Check if audio analysis dependencies are installed."""
    deps = {
        "beatnet": False,
        "librosa": False,
        "madmom": False,
        "numpy": False,
        "ffmpeg": False
    }
    
    # Check Python packages
    try:
        from BeatNet.BeatNet import BeatNet
        deps["beatnet"] = True
    except ImportError:
        pass
    
    try:
        import librosa
        deps["librosa"] = True
    except ImportError:
        pass
    
    try:
        import madmom
        deps["madmom"] = True
    except ImportError:
        pass
    
    try:
        import numpy
        deps["numpy"] = True
    except ImportError:
        pass
    
    # Check ffmpeg
    import subprocess
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            deps["ffmpeg"] = True
    except Exception:
        pass
    
    all_installed = all(deps.values())
    
    return success({
        "all_installed": all_installed,
        "dependencies": deps
    })


# =============================================================================
# Main
# =============================================================================

OPERATIONS = {
    # Core
    "check_connection": op_check_connection,
    "get_context": op_get_context,
    
    # Media
    "import_media": op_import_media,
    "append_to_timeline": op_append_to_timeline,
    "create_timeline": op_create_timeline,
    
    # Clip Properties
    "set_clip_property": op_set_clip_property,
    "set_clip_enabled": op_set_clip_enabled,
    "set_clip_color": op_set_clip_color,
    
    # Markers
    "add_marker": op_add_marker,
    "add_clip_marker": op_add_clip_marker,
    "delete_marker": op_delete_marker,
    "clear_markers": op_clear_markers,
    
    # Tracks
    "add_track": op_add_track,
    "delete_track": op_delete_track,
    "set_track_name": op_set_track_name,
    "enable_track": op_enable_track,
    "lock_track": op_lock_track,
    
    # Render
    "add_render_job": op_add_render_job,
    "start_render": op_start_render,
    "set_render_settings": op_set_render_settings,
    "get_render_formats": op_get_render_formats,
    "get_render_codecs": op_get_render_codecs,
    "set_render_format_and_codec": op_set_render_format_and_codec,
    "get_render_presets": op_get_render_presets,
    "load_render_preset": op_load_render_preset,
    "save_render_preset": op_save_render_preset,
    "delete_render_preset": op_delete_render_preset,
    "get_render_jobs": op_get_render_jobs,
    "delete_render_job": op_delete_render_job,
    "delete_all_render_jobs": op_delete_all_render_jobs,
    "get_render_job_status": op_get_render_job_status,
    
    # Timeline
    "set_timeline": op_set_timeline,
    "duplicate_timeline": op_duplicate_timeline,
    "export_timeline": op_export_timeline,
    "import_timeline_from_file": op_import_timeline_from_file,
    
    # Fusion & Compositions
    "insert_fusion_composition": op_insert_fusion_composition,
    "create_fusion_clip": op_create_fusion_clip,
    "add_fusion_comp_to_clip": op_add_fusion_comp_to_clip,
    "create_compound_clip": op_create_compound_clip,
    
    # Generators & Titles
    "insert_generator": op_insert_generator,
    "insert_title": op_insert_title,

    # Text+ Operations
    "add_text_to_timeline": op_add_text_to_timeline,
    "set_text_content": op_set_text_content,
    "set_text_style": op_set_text_style,
    "get_text_properties": op_get_text_properties,
    
    # AI/Processing
    "stabilize_clip": op_stabilize_clip,
    "smart_reframe": op_smart_reframe,
    "create_magic_mask": op_create_magic_mask,
    "detect_scene_cuts": op_detect_scene_cuts,
    
    # Clip Management
    "delete_clips": op_delete_clips,
    "set_clips_linked": op_set_clips_linked,
    
    # Navigation
    "set_current_timecode": op_set_current_timecode,
    "get_current_timecode": op_get_current_timecode,
    "open_page": op_open_page,
    "get_current_page": op_get_current_page,
    
    # Audio
    "create_subtitles_from_audio": op_create_subtitles_from_audio,
    "detect_beats": op_detect_beats,
    "check_audio_deps": op_check_audio_deps,
    
    # Stills & Gallery
    "grab_still": op_grab_still,
    "export_still": op_export_still,
    "apply_grade_from_drx": op_apply_grade_from_drx,
    "get_gallery_albums": op_get_gallery_albums,
    
    # Color Grading
    "apply_lut": op_apply_lut,
    "get_lut": op_get_lut,
    "set_cdl": op_set_cdl,
    "copy_grades": op_copy_grades,
    "reset_grades": op_reset_grades,
    "add_color_version": op_add_color_version,
    "load_color_version": op_load_color_version,
    "get_color_versions": op_get_color_versions,
    "delete_color_version": op_delete_color_version,
    
    # Color Groups
    "create_color_group": op_create_color_group,
    "get_color_groups": op_get_color_groups,
    "assign_to_color_group": op_assign_to_color_group,
    "remove_from_color_group": op_remove_from_color_group,
    "delete_color_group": op_delete_color_group,
    
    # Media Pool
    "create_media_pool_folder": op_create_media_pool_folder,
    "set_current_media_pool_folder": op_set_current_media_pool_folder,
    "move_media_pool_clips": op_move_media_pool_clips,
    "delete_media_pool_clips": op_delete_media_pool_clips,
    "delete_media_pool_folders": op_delete_media_pool_folders,
    "set_clip_metadata": op_set_clip_metadata,
    "get_clip_metadata": op_get_clip_metadata,
    "relink_clips": op_relink_clips,
    
    # Flags
    "add_flag": op_add_flag,
    "get_flags": op_get_flags,
    "clear_flags": op_clear_flags,
    
    # Takes
    "add_take": op_add_take,
    "select_take": op_select_take,
    "get_takes": op_get_takes,
    "finalize_take": op_finalize_take,
    "delete_take": op_delete_take,
    
    # Project Settings
    "save_project": op_save_project,
    "export_project": op_export_project,
    "get_project_setting": op_get_project_setting,
    "set_project_setting": op_set_project_setting,
    "get_timeline_setting": op_get_timeline_setting,
    "set_timeline_setting": op_set_timeline_setting,
    
    # Keyframe Mode
    "set_keyframe_mode": op_set_keyframe_mode,
    "get_keyframe_mode": op_get_keyframe_mode,
    
    # Cache
    "set_clip_cache_mode": op_set_clip_cache_mode,
    "get_clip_cache_mode": op_get_clip_cache_mode,
    "refresh_lut_list": op_refresh_lut_list,
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
