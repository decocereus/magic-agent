use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::Read;
use std::path::Path;

use crate::config::Config;
use crate::resolve::operations::ALL as ALL_OPERATIONS;
use crate::resolve::ResolveBridge;

const OPS_SCHEMA: &str = include_str!("../../docs/ops.json");

use super::{
    BatchArgs, ClipCommands, Commands, GalleryCommands, LayoutCommands, MarkerCommands,
    MediaCommands, NodeCommands, OpArgs, OpsCommands, OpsSchemaArgs, OpsSchemaFormat, PageCommands,
    ProjectCommands, RenderCommands, StorageCommands, TimecodeCommands, TimelineCommands,
    TrackCommands,
};

#[derive(Debug, Deserialize, Serialize)]
struct BatchOperation {
    op: String,
    #[serde(default)]
    params: Value,
}

#[derive(Debug, Deserialize)]
struct BatchWrapper {
    operations: Vec<BatchOperation>,
}

pub async fn dispatch(config: &Config, command: Commands, pretty: bool) -> Result<()> {
    match command {
        Commands::Doctor => doctor(config, pretty).await,
        Commands::Status => status(config, pretty).await,
        Commands::Ops { command } => ops(command, pretty),
        Commands::Op(args) => op(config, &args, pretty).await,
        Commands::Batch(args) => batch(config, &args, pretty).await,
        Commands::Marker { command } => marker(config, command, pretty).await,
        Commands::Track { command } => track(config, command, pretty).await,
        Commands::Timeline { command } => timeline(config, command, pretty).await,
        Commands::Media { command } => media(config, command, pretty).await,
        Commands::Clip { command } => clip(config, command, pretty).await,
        Commands::Render { command } => render(config, command, pretty).await,
        Commands::Project { command } => project(config, command, pretty).await,
        Commands::Page { command } => page(config, command, pretty).await,
        Commands::Timecode { command } => timecode(config, command, pretty).await,
        Commands::Storage { command } => storage(config, command, pretty).await,
        Commands::Gallery { command } => gallery(config, command, pretty).await,
        Commands::Node { command } => node(config, command, pretty).await,
        Commands::Layout { command } => layout(config, command, pretty).await,
    }
}

fn print_json<T: Serialize>(value: &T, pretty: bool) -> Result<()> {
    if pretty {
        println!("{}", serde_json::to_string_pretty(value)?);
    } else {
        println!("{}", serde_json::to_string(value)?);
    }
    Ok(())
}

fn read_string_from_stdin() -> Result<String> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    Ok(input)
}

fn read_string_from_file(path: &Path) -> Result<String> {
    std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read file: {}", path.display()))
}

fn parse_params(args: &OpArgs) -> Result<Value> {
    let sources = [
        args.params.is_some(),
        args.params_file.is_some(),
        args.params_stdin,
    ];
    if sources.iter().filter(|v| **v).count() > 1 {
        anyhow::bail!("Use only one of --params, --params-file, or --params-stdin");
    }

    if let Some(params) = &args.params {
        return Ok(serde_json::from_str(params).with_context(|| "Failed to parse --params JSON")?);
    }

    if let Some(path) = &args.params_file {
        let input = read_string_from_file(path)?;
        return Ok(
            serde_json::from_str(&input).with_context(|| "Failed to parse --params-file JSON")?
        );
    }

    if args.params_stdin {
        let input = read_string_from_stdin()?;
        return Ok(serde_json::from_str(&input).with_context(|| "Failed to parse JSON from stdin")?);
    }

    Ok(json!({}))
}

fn parse_batch_input(args: &BatchArgs) -> Result<Vec<BatchOperation>> {
    if args.file.is_some() && args.stdin {
        anyhow::bail!("Use only one of --file or --stdin");
    }

    let input = if let Some(path) = &args.file {
        read_string_from_file(path)?
    } else if args.stdin {
        read_string_from_stdin()?
    } else {
        anyhow::bail!("Provide --file or --stdin for batch input");
    };

    let value: Value =
        serde_json::from_str(&input).with_context(|| "Failed to parse batch JSON")?;

    if value.is_array() {
        serde_json::from_value(value).with_context(|| "Failed to parse batch array")
    } else if value.get("operations").is_some() {
        let wrapper: BatchWrapper =
            serde_json::from_value(value).with_context(|| "Failed to parse batch wrapper")?;
        Ok(wrapper.operations)
    } else {
        anyhow::bail!("Batch JSON must be an array or {{\"operations\": [...]}} object");
    }
}

fn parse_property_value(raw: &str) -> Value {
    let trimmed = raw.trim();
    if trimmed.eq_ignore_ascii_case("true") {
        return Value::Bool(true);
    }
    if trimmed.eq_ignore_ascii_case("false") {
        return Value::Bool(false);
    }
    if let Ok(int_val) = trimmed.parse::<i64>() {
        return Value::Number(int_val.into());
    }
    if let Ok(float_val) = trimmed.parse::<f64>() {
        if let Some(number) = serde_json::Number::from_f64(float_val) {
            return Value::Number(number);
        }
    }
    if trimmed.starts_with('{') || trimmed.starts_with('[') || trimmed.starts_with('"') {
        if let Ok(parsed) = serde_json::from_str(trimmed) {
            return parsed;
        }
    }
    Value::String(trimmed.to_string())
}

fn parse_key_value_pairs(items: &[String]) -> Result<Value> {
    let mut map = serde_json::Map::new();
    for item in items {
        let mut parts = item.splitn(2, '=');
        let key = parts.next().unwrap_or("").trim();
        let raw = parts.next().unwrap_or("").trim();
        if key.is_empty() || raw.is_empty() {
            anyhow::bail!("Invalid property format: {} (use KEY=VALUE)", item);
        }
        map.insert(key.to_string(), parse_property_value(raw));
    }
    Ok(Value::Object(map))
}

fn require_toggle(enable: bool, disable: bool, label: &str) -> Result<bool> {
    match (enable, disable) {
        (true, false) => Ok(true),
        (false, true) => Ok(false),
        _ => anyhow::bail!("Specify exactly one of --enable/--disable for {}", label),
    }
}

fn require_link_toggle(link: bool, unlink: bool) -> Result<bool> {
    match (link, unlink) {
        (true, false) => Ok(true),
        (false, true) => Ok(false),
        _ => anyhow::bail!("Specify exactly one of --link/--unlink"),
    }
}

fn require_single_selector(all: bool, index: bool, name: bool) -> Result<()> {
    let mut count = 0;
    if all {
        count += 1;
    }
    if index {
        count += 1;
    }
    if name {
        count += 1;
    }
    if count != 1 {
        anyhow::bail!("Specify exactly one of --all, --index, or --name");
    }
    Ok(())
}

fn build_clip_selector(
    track: i32,
    index: Option<i32>,
    name: Option<&str>,
    all: bool,
) -> Result<Value> {
    let mut selector = serde_json::Map::new();
    selector.insert("track".to_string(), json!(track));

    require_single_selector(all, index.is_some(), name.is_some())?;

    if all {
        selector.insert("all".to_string(), json!(true));
        return Ok(Value::Object(selector));
    }

    if let Some(idx) = index {
        selector.insert("index".to_string(), json!(idx));
        return Ok(Value::Object(selector));
    }

    if let Some(name) = name {
        selector.insert("name".to_string(), json!(name));
        return Ok(Value::Object(selector));
    }

    anyhow::bail!("Specify one of --all, --index, or --name")
}

pub async fn doctor(config: &Config, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    let mut checks = vec![];

    let python_status = match bridge.check_python().await {
        Ok(version) => {
            json!({
                "name": "python",
                "status": "ok",
                "message": version,
                "path": config.python_path()
            })
        }
        Err(e) => {
            json!({
                "name": "python",
                "status": "error",
                "message": e.to_string(),
                "path": config.python_path()
            })
        }
    };
    checks.push(python_status);

    let script_status = if bridge.script_exists() {
        json!({
            "name": "bridge_script",
            "status": "ok",
            "message": "Found",
            "path": bridge.script_path()
        })
    } else {
        json!({
            "name": "bridge_script",
            "status": "error",
            "message": "Not found",
            "path": bridge.script_path()
        })
    };
    checks.push(script_status);

    let resolve_status = match bridge.check_connection().await {
        Ok(info) => {
            json!({
                "name": "resolve",
                "status": "ok",
                "message": format!("{} {}", info.product, info.version)
            })
        }
        Err(e) => {
            let msg = e.to_string();
            json!({
                "name": "resolve",
                "status": if msg.contains("RESOLVE_NOT_RUNNING") { "warning" } else { "error" },
                "message": msg
            })
        }
    };
    checks.push(resolve_status);

    let ffmpeg_status = match std::process::Command::new("ffmpeg")
        .arg("-version")
        .output()
    {
        Ok(output) if output.status.success() => {
            let version = String::from_utf8_lossy(&output.stdout);
            let first_line = version.lines().next().unwrap_or("ffmpeg installed");
            json!({
                "name": "ffmpeg",
                "status": "ok",
                "message": first_line.chars().take(50).collect::<String>()
            })
        }
        _ => {
            json!({
                "name": "ffmpeg",
                "status": "warning",
                "message": "Not found (optional, required for beat detection)"
            })
        }
    };
    checks.push(ffmpeg_status);

    let result = json!({ "checks": checks });

    if pretty {
        println!("Magic Agent Doctor\n");
        for check in checks {
            let status = check["status"].as_str().unwrap_or("unknown");
            let icon = match status {
                "ok" => "\u{2714}",
                "warning" => "\u{26A0}",
                "error" => "\u{2718}",
                _ => "?",
            };
            println!(
                "{} {}: {}",
                icon,
                check["name"].as_str().unwrap_or(""),
                check["message"].as_str().unwrap_or("")
            );
            if let Some(path) = check["path"].as_str() {
                println!("    Path: {}", path);
            }
        }
    } else {
        print_json(&result, false)?;
    }

    Ok(())
}

pub async fn status(config: &Config, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    let context = bridge.get_context().await?;

    if pretty {
        println!("Resolve Status\n");
        println!("Product: {} {}", context.product, context.version);

        if let Some(project) = &context.project {
            println!("\nProject: {}", project.name);
            println!("Timelines: {}", project.timeline_count);
        } else {
            println!("\nNo project open");
        }

        if let Some(timeline) = &context.timeline {
            println!("\nActive Timeline: {}", timeline.name);
            println!(
                "Resolution: {}x{} @ {} fps",
                timeline.resolution[0], timeline.resolution[1], timeline.frame_rate
            );
            println!(
                "Duration: {} frames ({} - {})",
                timeline.end_frame - timeline.start_frame,
                timeline.start_frame,
                timeline.end_frame
            );

            println!("\nVideo Tracks:");
            for track in &timeline.tracks.video {
                println!(
                    "  Track {}: {} ({} clips)",
                    track.index,
                    track.name,
                    track.clips.len()
                );
            }

            println!("\nAudio Tracks:");
            for track in &timeline.tracks.audio {
                println!(
                    "  Track {}: {} ({} clips)",
                    track.index,
                    track.name,
                    track.clips.len()
                );
            }

            if !timeline.markers.is_empty() {
                println!("\nMarkers: {}", timeline.markers.len());
            }
        }

        if let Some(pool) = &context.media_pool {
            println!(
                "\nMedia Pool: {} clips, {} folders",
                pool.clips.len(),
                pool.folders.len()
            );
        }
    } else {
        print_json(&context, false)?;
    }

    Ok(())
}

fn ops(command: OpsCommands, pretty: bool) -> Result<()> {
    match command {
        OpsCommands::List => {
            if pretty {
                println!("Supported Operations:\n");
                for op in ALL_OPERATIONS {
                    println!("- {}", op);
                }
            } else {
                print_json(&json!({ "operations": ALL_OPERATIONS }), false)?;
            }
            Ok(())
        }
        OpsCommands::Schema(args) => {
            let format = resolve_schema_format(&args, pretty);
            match format {
                OpsSchemaFormat::Raw => {
                    print!("{}", OPS_SCHEMA);
                    if !OPS_SCHEMA.ends_with('\n') {
                        println!();
                    }
                    Ok(())
                }
                OpsSchemaFormat::Json => {
                    let schema: Value = serde_json::from_str(OPS_SCHEMA)
                        .with_context(|| "Failed to parse embedded ops schema")?;
                    print_json(&schema, false)
                }
                OpsSchemaFormat::Pretty => {
                    let schema: Value = serde_json::from_str(OPS_SCHEMA)
                        .with_context(|| "Failed to parse embedded ops schema")?;
                    print_json(&schema, true)
                }
            }
        }
    }
}

fn resolve_schema_format(args: &OpsSchemaArgs, pretty: bool) -> OpsSchemaFormat {
    args.format.clone().unwrap_or_else(|| {
        if pretty {
            OpsSchemaFormat::Pretty
        } else {
            OpsSchemaFormat::Json
        }
    })
}

async fn op(config: &Config, args: &OpArgs, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);
    let params = parse_params(args)?;
    let result = bridge.execute_operation(&args.op, params).await?;
    print_json(&result, pretty)
}

async fn batch(config: &Config, args: &BatchArgs, pretty: bool) -> Result<()> {
    let operations = parse_batch_input(args)?;

    if args.dry_run {
        if pretty {
            println!("Batch valid: {} operations", operations.len());
        } else {
            print_json(&json!({ "valid": true, "count": operations.len() }), false)?;
        }
        return Ok(());
    }

    let bridge = ResolveBridge::new(config);
    let mut results = vec![];

    for (index, op) in operations.iter().enumerate() {
        match bridge.execute_operation(&op.op, op.params.clone()).await {
            Ok(result) => {
                results.push(json!({
                    "index": index,
                    "op": op.op.clone(),
                    "status": "success",
                    "result": result
                }));
            }
            Err(e) => {
                results.push(json!({
                    "index": index,
                    "op": op.op.clone(),
                    "status": "error",
                    "error": e.to_string()
                }));
            }
        }
    }

    let output = json!({
        "executed": true,
        "results": results
    });

    print_json(&output, pretty)
}

async fn marker(config: &Config, command: MarkerCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        MarkerCommands::Add(args) => {
            let mut params = json!({
                "frame": args.frame,
                "color": args.color,
            });
            if args.relative {
                params["relative"] = json!(true);
            }
            if let Some(name) = args.name {
                params["name"] = json!(name);
            }
            if let Some(note) = args.note {
                params["note"] = json!(note);
            }
            if let Some(duration) = args.duration {
                params["duration"] = json!(duration);
            }

            let result = bridge.execute_operation("add_marker", params).await?;
            print_json(&result, pretty)
        }
        MarkerCommands::Delete(args) => {
            if args.frame.is_none() && args.color.is_none() {
                anyhow::bail!("Specify --frame or --color for marker delete");
            }
            let mut params = json!({});
            if let Some(frame) = args.frame {
                params["frame"] = json!(frame);
            }
            if let Some(color) = args.color {
                params["color"] = json!(color);
            }
            if args.relative {
                params["relative"] = json!(true);
            }
            let result = bridge.execute_operation("delete_marker", params).await?;
            print_json(&result, pretty)
        }
    }
}

async fn track(config: &Config, command: TrackCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        TrackCommands::Add(args) => {
            let params = json!({ "type": args.track_type });
            let result = bridge.execute_operation("add_track", params).await?;
            print_json(&result, pretty)
        }
        TrackCommands::Delete(args) => {
            let params = json!({ "type": args.track_type, "index": args.index });
            let result = bridge.execute_operation("delete_track", params).await?;
            print_json(&result, pretty)
        }
        TrackCommands::Name(args) => {
            let params = json!({ "type": args.track_type, "index": args.index, "name": args.name });
            let result = bridge.execute_operation("set_track_name", params).await?;
            print_json(&result, pretty)
        }
        TrackCommands::Enable(args) => {
            let enabled = require_toggle(args.enable, args.disable, "track")?;
            let params = json!({
                "type": args.track_type,
                "index": args.index,
                "enabled": enabled
            });
            let result = bridge.execute_operation("enable_track", params).await?;
            print_json(&result, pretty)
        }
        TrackCommands::Lock(args) => {
            let locked = require_toggle(args.lock, args.unlock, "track")?;
            let params = json!({
                "type": args.track_type,
                "index": args.index,
                "locked": locked
            });
            let result = bridge.execute_operation("lock_track", params).await?;
            print_json(&result, pretty)
        }
    }
}

async fn timeline(config: &Config, command: TimelineCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        TimelineCommands::Set(args) => {
            if args.name.is_some() && args.index.is_some() {
                anyhow::bail!("Use only one of --name or --index");
            }
            if args.name.is_none() && args.index.is_none() {
                anyhow::bail!("Specify --name or --index");
            }
            let mut params = json!({});
            if let Some(name) = args.name {
                params["name"] = json!(name);
            }
            if let Some(index) = args.index {
                params["index"] = json!(index);
            }
            let result = bridge.execute_operation("set_timeline", params).await?;
            print_json(&result, pretty)
        }
        TimelineCommands::Duplicate(args) => {
            let params = json!({ "name": args.name });
            let result = bridge
                .execute_operation("duplicate_timeline", params)
                .await?;
            print_json(&result, pretty)
        }
        TimelineCommands::Export(args) => {
            let params = json!({
                "path": args.path.to_string_lossy(),
                "format": args.format
            });
            let result = bridge.execute_operation("export_timeline", params).await?;
            print_json(&result, pretty)
        }
        TimelineCommands::Import(args) => {
            let mut params = json!({
                "path": args.path.to_string_lossy()
            });
            if let Some(name) = args.name {
                params["name"] = json!(name);
            }
            if args.no_import_source_clips {
                params["import_source_clips"] = json!(false);
            }
            let result = bridge
                .execute_operation("import_timeline_from_file", params)
                .await?;
            print_json(&result, pretty)
        }
        TimelineCommands::Thumbnail(args) => {
            let params = json!({ "path": args.path.to_string_lossy() });
            let result = bridge
                .execute_operation("get_current_clip_thumbnail", params)
                .await?;
            print_json(&result, pretty)
        }
        TimelineCommands::GrabAllStills => {
            let result = bridge
                .execute_operation("grab_all_stills", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        TimelineCommands::ConvertStereo => {
            let result = bridge
                .execute_operation("convert_timeline_to_stereo", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        TimelineCommands::AnalyzeDolby => {
            let result = bridge
                .execute_operation("analyze_dolby_vision", json!({}))
                .await?;
            print_json(&result, pretty)
        }
    }
}

async fn media(config: &Config, command: MediaCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        MediaCommands::Import(args) => {
            let paths: Vec<String> = args
                .paths
                .into_iter()
                .map(|p| p.to_string_lossy().to_string())
                .collect();
            let params = json!({ "paths": paths });
            let result = bridge.execute_operation("import_media", params).await?;
            print_json(&result, pretty)
        }
        MediaCommands::Append(args) => {
            let mut params = json!({ "clips": args.clips });
            if let Some(track) = args.track {
                params["track"] = json!(track);
            }
            let result = bridge
                .execute_operation("append_to_timeline", params)
                .await?;
            print_json(&result, pretty)
        }
        MediaCommands::SyncAudio(args) => {
            let params = json!({
                "clips": args.clips,
                "mode": args.mode
            });
            let result = bridge.execute_operation("auto_sync_audio", params).await?;
            print_json(&result, pretty)
        }
        MediaCommands::MoveFolder(args) => {
            let params = json!({
                "folder": args.folder,
                "dest": args.dest
            });
            let result = bridge.execute_operation("move_folder", params).await?;
            print_json(&result, pretty)
        }
        MediaCommands::ExportMetadata(args) => {
            let mut params = json!({
                "path": args.path.to_string_lossy()
            });
            if !args.clips.is_empty() {
                params["clips"] = json!(args.clips);
            }
            let result = bridge.execute_operation("export_metadata", params).await?;
            print_json(&result, pretty)
        }
        MediaCommands::CreateStereo(args) => {
            let params = json!({
                "left": args.left,
                "right": args.right
            });
            let result = bridge
                .execute_operation("create_stereo_clip", params)
                .await?;
            print_json(&result, pretty)
        }
        MediaCommands::GetSelected => {
            let result = bridge
                .execute_operation("get_selected_clips", json!({}))
                .await?;
            print_json(&result, pretty)
        }
    }
}

async fn clip(config: &Config, command: ClipCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        ClipCommands::SetProperty(args) => {
            let selector =
                build_clip_selector(args.track, args.index, args.name.as_deref(), args.all)?;
            let properties = parse_key_value_pairs(&args.sets)?;
            let params = json!({
                "selector": selector,
                "properties": properties
            });
            let result = bridge
                .execute_operation("set_clip_property", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::Enable(args) => {
            let enabled = require_toggle(args.enable, args.disable, "clip")?;
            require_single_selector(args.all, args.index.is_some(), args.name.is_some())?;
            let mut selector = json!({
                "track": args.track,
                "track_type": args.track_type,
            });
            if args.all {
                selector["all"] = json!(true);
            } else if let Some(index) = args.index {
                selector["index"] = json!(index);
            } else if let Some(name) = args.name {
                selector["name"] = json!(name);
            }
            let params = json!({ "selector": selector, "enabled": enabled });
            let result = bridge.execute_operation("set_clip_enabled", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::Color(args) => {
            if args.clear && args.color.is_some() {
                anyhow::bail!("Use only one of --color or --clear");
            }
            if !args.clear && args.color.is_none() {
                anyhow::bail!("Specify --color or --clear");
            }
            require_single_selector(args.all, args.index.is_some(), args.name.is_some())?;
            let mut selector = json!({
                "track": args.track,
                "track_type": args.track_type,
            });
            if args.all {
                selector["all"] = json!(true);
            } else if let Some(index) = args.index {
                selector["index"] = json!(index);
            } else if let Some(name) = args.name {
                selector["name"] = json!(name);
            }
            let mut params = json!({ "selector": selector });
            if let Some(color) = args.color {
                params["color"] = json!(color);
            }
            let result = bridge.execute_operation("set_clip_color", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::Delete(args) => {
            if args.all && !args.index.is_empty() {
                anyhow::bail!("Use only one of --all or --index");
            }
            if !args.all && args.index.is_empty() {
                anyhow::bail!("Specify --all or at least one --index");
            }
            let mut selector = json!({
                "track": args.track,
                "track_type": args.track_type,
            });
            if args.all {
                selector["all"] = json!(true);
            } else if args.index.len() == 1 {
                selector["index"] = json!(args.index[0]);
            } else {
                selector["indices"] = json!(args.index);
            }
            let params = json!({ "selector": selector, "ripple": args.ripple });
            let result = bridge.execute_operation("delete_clips", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::Link(args) => {
            let linked = require_link_toggle(args.link, args.unlink)?;
            if args.indices.len() < 2 {
                anyhow::bail!("Provide at least two --indices values to link/unlink");
            }
            let selector = json!({
                "track": args.track,
                "indices": args.indices
            });
            let params = json!({ "selector": selector, "linked": linked });
            let result = bridge.execute_operation("set_clips_linked", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::LinkProxy(args) => {
            let params = json!({
                "clip": args.clip,
                "proxy_path": args.proxy.to_string_lossy()
            });
            let result = bridge.execute_operation("link_proxy_media", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::UnlinkProxy(args) => {
            let params = json!({ "clip": args.clip });
            let result = bridge
                .execute_operation("unlink_proxy_media", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::Replace(args) => {
            let params = json!({
                "clip": args.clip,
                "path": args.path.to_string_lossy()
            });
            let result = bridge.execute_operation("replace_clip", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::SetInOut(args) => {
            let mut params = json!({ "clip": args.clip });
            if let Some(in_point) = args.r#in {
                params["in_point"] = json!(in_point);
            }
            if let Some(out_point) = args.out {
                params["out_point"] = json!(out_point);
            }
            let result = bridge.execute_operation("set_clip_in_out", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::Transcribe(args) => {
            let params = json!({ "clip": args.clip });
            let result = bridge.execute_operation("transcribe_audio", params).await?;
            print_json(&result, pretty)
        }
        ClipCommands::ImportFusion(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index,
                "path": args.path.to_string_lossy()
            });
            let result = bridge
                .execute_operation("import_fusion_comp", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::ExportFusion(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index,
                "comp_index": args.comp_index,
                "path": args.path.to_string_lossy()
            });
            let result = bridge
                .execute_operation("export_fusion_comp", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::RenameFusion(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index,
                "comp_index": args.comp_index,
                "name": args.name
            });
            let result = bridge
                .execute_operation("rename_fusion_comp", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::ExportLut(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index,
                "lut_type": args.lut_type,
                "path": args.path.to_string_lossy()
            });
            let result = bridge
                .execute_operation("export_lut_from_clip", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::RegenerateMask(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index
            });
            let result = bridge
                .execute_operation("regenerate_magic_mask", params)
                .await?;
            print_json(&result, pretty)
        }
        ClipCommands::GetLinked(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index
            });
            let result = bridge.execute_operation("get_linked_items", params).await?;
            print_json(&result, pretty)
        }
    }
}

async fn render(config: &Config, command: RenderCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        RenderCommands::AddJob(args) => {
            let mut params = json!({});
            if let Some(format) = args.format {
                params["format"] = json!(format);
            }
            if let Some(codec) = args.codec {
                params["codec"] = json!(codec);
            }
            if let Some(path) = args.path {
                params["path"] = json!(path.to_string_lossy());
            }
            if let Some(filename) = args.filename {
                params["filename"] = json!(filename);
            }
            let result = bridge.execute_operation("add_render_job", params).await?;
            print_json(&result, pretty)
        }
        RenderCommands::Start(args) => {
            let mut params = json!({});
            if args.no_wait {
                params["wait"] = json!(false);
            }
            let result = bridge.execute_operation("start_render", params).await?;
            print_json(&result, pretty)
        }
        RenderCommands::Formats => {
            let result = bridge
                .execute_operation("get_render_formats", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        RenderCommands::Codecs(args) => {
            let params = json!({ "format": args.format });
            let result = bridge
                .execute_operation("get_render_codecs", params)
                .await?;
            print_json(&result, pretty)
        }
    }
}

async fn project(config: &Config, command: ProjectCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        ProjectCommands::Save => {
            let result = bridge.execute_operation("save_project", json!({})).await?;
            print_json(&result, pretty)
        }
        ProjectCommands::Export(args) => {
            let mut params = json!({ "path": args.path.to_string_lossy() });
            if args.without_stills_and_luts {
                params["with_stills_and_luts"] = json!(false);
            }
            let result = bridge.execute_operation("export_project", params).await?;
            print_json(&result, pretty)
        }
        ProjectCommands::GetSetting(args) => {
            let mut params = json!({});
            if let Some(name) = args.name {
                params["name"] = json!(name);
            }
            let result = bridge
                .execute_operation("get_project_setting", params)
                .await?;
            print_json(&result, pretty)
        }
        ProjectCommands::SetSetting(args) => {
            let params = json!({ "name": args.name, "value": args.value });
            let result = bridge
                .execute_operation("set_project_setting", params)
                .await?;
            print_json(&result, pretty)
        }
        ProjectCommands::Create(args) => {
            let params = json!({ "name": args.name });
            let result = bridge.execute_operation("create_project", params).await?;
            print_json(&result, pretty)
        }
        ProjectCommands::Delete(args) => {
            let params = json!({ "name": args.name });
            let result = bridge.execute_operation("delete_project", params).await?;
            print_json(&result, pretty)
        }
        ProjectCommands::Archive(args) => {
            let mut params = json!({
                "name": args.name,
                "path": args.path.to_string_lossy(),
                "with_stills_and_luts": args.with_stills_and_luts
            });
            if let Some(filename) = args.filename {
                params["filename"] = json!(filename);
            }
            let result = bridge.execute_operation("archive_project", params).await?;
            print_json(&result, pretty)
        }
        ProjectCommands::Load(args) => {
            let params = json!({ "name": args.name });
            let result = bridge.execute_operation("load_project", params).await?;
            print_json(&result, pretty)
        }
        ProjectCommands::List => {
            let result = bridge
                .execute_operation("get_project_list", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        ProjectCommands::Close => {
            let result = bridge.execute_operation("close_project", json!({})).await?;
            print_json(&result, pretty)
        }
    }
}

async fn page(config: &Config, command: PageCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        PageCommands::Get => {
            let result = bridge
                .execute_operation("get_current_page", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        PageCommands::Open(args) => {
            let params = json!({ "page": args.page });
            let result = bridge.execute_operation("open_page", params).await?;
            print_json(&result, pretty)
        }
    }
}

async fn timecode(config: &Config, command: TimecodeCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        TimecodeCommands::Get => {
            let result = bridge
                .execute_operation("get_current_timecode", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        TimecodeCommands::Set(args) => {
            let params = json!({ "timecode": args.timecode });
            let result = bridge
                .execute_operation("set_current_timecode", params)
                .await?;
            print_json(&result, pretty)
        }
    }
}

async fn storage(config: &Config, command: StorageCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        StorageCommands::Volumes => {
            let result = bridge
                .execute_operation("get_mounted_volumes", json!({}))
                .await?;
            print_json(&result, pretty)
        }
        StorageCommands::Browse(args) => {
            let params = json!({ "path": args.path.to_string_lossy() });
            let result = bridge
                .execute_operation("get_subfolder_list", params)
                .await?;
            print_json(&result, pretty)
        }
        StorageCommands::Reveal(args) => {
            let params = json!({ "path": args.path.to_string_lossy() });
            let result = bridge
                .execute_operation("reveal_in_storage", params)
                .await?;
            print_json(&result, pretty)
        }
        StorageCommands::AddMatte(args) => {
            let params = json!({
                "media_path": args.media_path.to_string_lossy(),
                "matte_path": args.matte_path.to_string_lossy()
            });
            let result = bridge.execute_operation("add_clip_matte", params).await?;
            print_json(&result, pretty)
        }
    }
}

async fn gallery(config: &Config, command: GalleryCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        GalleryCommands::ListAlbums(args) => {
            let params = json!({ "type": args.album_type });
            let result = bridge
                .execute_operation("get_gallery_albums", params)
                .await?;
            print_json(&result, pretty)
        }
        GalleryCommands::CreateAlbum(args) => {
            let params = json!({
                "name": args.name,
                "type": args.album_type
            });
            let result = bridge
                .execute_operation("create_gallery_album", params)
                .await?;
            print_json(&result, pretty)
        }
        GalleryCommands::DeleteAlbum(args) => {
            let params = json!({
                "name": args.name,
                "type": args.album_type
            });
            let result = bridge
                .execute_operation("delete_gallery_album", params)
                .await?;
            print_json(&result, pretty)
        }
        GalleryCommands::Import(args) => {
            let paths: Vec<String> = args
                .paths
                .into_iter()
                .map(|p| p.to_string_lossy().to_string())
                .collect();
            let params = json!({
                "album": args.album,
                "paths": paths
            });
            let result = bridge.execute_operation("import_stills", params).await?;
            print_json(&result, pretty)
        }
        GalleryCommands::Export(args) => {
            let mut params = json!({
                "album": args.album,
                "path": args.path.to_string_lossy()
            });
            if let Some(prefix) = args.prefix {
                params["prefix"] = json!(prefix);
            }
            let result = bridge.execute_operation("export_stills", params).await?;
            print_json(&result, pretty)
        }
        GalleryCommands::GetLabel(args) => {
            let params = json!({
                "album": args.album,
                "index": args.index
            });
            let result = bridge.execute_operation("get_still_label", params).await?;
            print_json(&result, pretty)
        }
        GalleryCommands::SetLabel(args) => {
            let params = json!({
                "album": args.album,
                "index": args.index,
                "label": args.label
            });
            let result = bridge.execute_operation("set_still_label", params).await?;
            print_json(&result, pretty)
        }
    }
}

async fn node(config: &Config, command: NodeCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        NodeCommands::Enable(args) => {
            let enabled = require_toggle(args.enable, args.disable, "node")?;
            let params = json!({
                "track": args.track,
                "index": args.index,
                "node": args.node,
                "enabled": enabled
            });
            let result = bridge.execute_operation("set_node_enabled", params).await?;
            print_json(&result, pretty)
        }
        NodeCommands::GetTools(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index,
                "node": args.node
            });
            let result = bridge
                .execute_operation("get_tools_in_node", params)
                .await?;
            print_json(&result, pretty)
        }
        NodeCommands::ApplyArriCdl(args) => {
            let params = json!({
                "track": args.track,
                "index": args.index
            });
            let result = bridge
                .execute_operation("apply_arri_cdl_lut", params)
                .await?;
            print_json(&result, pretty)
        }
    }
}

async fn layout(config: &Config, command: LayoutCommands, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);

    match command {
        LayoutCommands::Save(args) => {
            let params = json!({ "name": args.name });
            let result = bridge
                .execute_operation("save_layout_preset", params)
                .await?;
            print_json(&result, pretty)
        }
        LayoutCommands::Load(args) => {
            let params = json!({ "name": args.name });
            let result = bridge
                .execute_operation("load_layout_preset", params)
                .await?;
            print_json(&result, pretty)
        }
        LayoutCommands::Export(args) => {
            let params = json!({
                "name": args.name,
                "path": args.path.to_string_lossy()
            });
            let result = bridge
                .execute_operation("export_layout_preset", params)
                .await?;
            print_json(&result, pretty)
        }
        LayoutCommands::Import(args) => {
            let params = json!({ "path": args.path.to_string_lossy() });
            let result = bridge
                .execute_operation("import_layout_preset", params)
                .await?;
            print_json(&result, pretty)
        }
        LayoutCommands::Delete(args) => {
            let params = json!({ "name": args.name });
            let result = bridge
                .execute_operation("delete_layout_preset", params)
                .await?;
            print_json(&result, pretty)
        }
        LayoutCommands::List => {
            let result = bridge
                .execute_operation("get_layout_presets", json!({}))
                .await?;
            print_json(&result, pretty)
        }
    }
}
