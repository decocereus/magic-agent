pub const ALL: &[&str] = &[
    // Core
    "check_connection",
    "get_context",
    // Media
    "import_media",
    "append_to_timeline",
    "create_timeline",
    // Clip Properties
    "set_clip_property",
    "set_clip_enabled",
    "set_clip_color",
    // Markers
    "add_marker",
    "add_clip_marker",
    "delete_marker",
    "clear_markers",
    // Tracks
    "add_track",
    "set_track_name",
    "enable_track",
    "lock_track",
    "delete_track",
    // Render
    "add_render_job",
    "start_render",
    "set_render_settings",
    "get_render_formats",
    "get_render_codecs",
    "set_render_format_and_codec",
    "get_render_presets",
    "load_render_preset",
    "save_render_preset",
    "delete_render_preset",
    "get_render_jobs",
    "delete_render_job",
    "delete_all_render_jobs",
    "get_render_job_status",
    // Timeline
    "set_timeline",
    "duplicate_timeline",
    "export_timeline",
    "import_timeline_from_file",
    // Fusion & Compositions
    "insert_fusion_composition",
    "create_fusion_clip",
    "add_fusion_comp_to_clip",
    "create_compound_clip",
    // Generators & Titles
    "insert_generator",
    "insert_title",
    // Text+ Operations
    "set_text_content",
    "set_text_style",
    "get_text_properties",
    "add_text_to_timeline",
    // AI/Processing
    "stabilize_clip",
    "smart_reframe",
    "create_magic_mask",
    "detect_scene_cuts",
    // Clip Management
    "delete_clips",
    "set_clips_linked",
    // Navigation
    "set_current_timecode",
    "get_current_timecode",
    "open_page",
    "get_current_page",
    // Audio
    "create_subtitles_from_audio",
    "detect_beats",
    "check_audio_deps",
    // Stills & Gallery
    "grab_still",
    "export_still",
    "apply_grade_from_drx",
    "get_gallery_albums",
    // Color Grading
    "apply_lut",
    "get_lut",
    "set_cdl",
    "copy_grades",
    "reset_grades",
    "add_color_version",
    "load_color_version",
    "get_color_versions",
    "delete_color_version",
    // Color Groups
    "create_color_group",
    "get_color_groups",
    "assign_to_color_group",
    "remove_from_color_group",
    "delete_color_group",
    // Media Pool
    "create_media_pool_folder",
    "set_current_media_pool_folder",
    "move_media_pool_clips",
    "delete_media_pool_clips",
    "delete_media_pool_folders",
    "set_clip_metadata",
    "get_clip_metadata",
    "relink_clips",
    // Flags
    "add_flag",
    "get_flags",
    "clear_flags",
    // Takes
    "add_take",
    "select_take",
    "get_takes",
    "finalize_take",
    "delete_take",
    // Project Settings
    "save_project",
    "export_project",
    "get_project_setting",
    "set_project_setting",
    "get_timeline_setting",
    "set_timeline_setting",
    // Keyframe Mode
    "set_keyframe_mode",
    "get_keyframe_mode",
    // Cache
    "set_clip_cache_mode",
    "get_clip_cache_mode",
    "refresh_lut_list",
];
