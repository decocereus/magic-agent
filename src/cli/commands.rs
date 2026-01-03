use anyhow::{Context, Result};
use serde_json::json;
use std::path::Path;

use crate::config::Config;
use crate::interpreter::{LlmClient, Plan};
use crate::resolve::ResolveBridge;

/// Doctor command - check system status
pub async fn doctor(config: &Config, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);
    
    let mut checks = vec![];
    
    // Check Python
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
    
    // Check bridge script
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
    
    // Check Resolve connection
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
    
    // Check API key
    let api_status = match config.api_key() {
        Ok(_) => {
            json!({
                "name": "api_key",
                "status": "ok",
                "message": format!("Configured for {}", config.llm.provider)
            })
        }
        Err(e) => {
            json!({
                "name": "api_key",
                "status": "warning",
                "message": e.to_string()
            })
        }
    };
    checks.push(api_status);
    
    // Output
    let result = json!({ "checks": checks });
    
    if pretty {
        println!("Magic Agent Doctor\n");
        for check in checks {
            let status = check["status"].as_str().unwrap_or("unknown");
            let icon = match status {
                "ok" => "\u{2714}",      // ✔
                "warning" => "\u{26A0}", // ⚠
                "error" => "\u{2718}",   // ✘
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
        println!("{}", serde_json::to_string(&result)?);
    }
    
    Ok(())
}

/// Status command - show current project/timeline
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
            println!("\nMedia Pool: {} clips, {} folders", pool.clips.len(), pool.folders.len());
        }
    } else {
        println!("{}", serde_json::to_string(&context)?);
    }
    
    Ok(())
}

/// Plan command - generate execution plan from natural language
pub async fn plan(config: &Config, request: &str, pretty: bool) -> Result<()> {
    let bridge = ResolveBridge::new(config);
    
    // Get current Resolve context
    let context = bridge.get_context().await
        .context("Failed to get Resolve context. Is Resolve running?")?;
    
    // Create LLM client
    let client = LlmClient::new(config)?;
    
    // Generate plan
    let plan = client.generate_plan(&context, request).await?;
    
    if pretty {
        print_plan_pretty(&plan);
    } else {
        println!("{}", serde_json::to_string(&plan)?);
    }
    
    Ok(())
}

fn print_plan_pretty(plan: &Plan) {
    if let Some(error) = &plan.error {
        println!("Error: {}", error);
        if let Some(suggestion) = &plan.suggestion {
            println!("Suggestion: {}", suggestion);
        }
        return;
    }
    
    println!("Execution Plan (v{})\n", plan.version);
    
    if let Some(target) = &plan.target {
        if let Some(project) = &target.project {
            println!("Target Project: {}", project);
        }
        if let Some(timeline) = &target.timeline {
            println!("Target Timeline: {}", timeline);
        }
        println!();
    }
    
    if !plan.preconditions.is_empty() {
        println!("Preconditions:");
        for pre in &plan.preconditions {
            println!("  - {:?}", pre);
        }
        println!();
    }
    
    println!("Operations:");
    for (i, op) in plan.operations.iter().enumerate() {
        println!("  {}. {}", i + 1, op.op);
        if !op.params.is_null() {
            let params_str = serde_json::to_string_pretty(&op.params)
                .unwrap_or_else(|_| "{}".to_string());
            for line in params_str.lines() {
                println!("      {}", line);
            }
        }
    }
}

/// Apply command - execute a plan
pub async fn apply(
    config: &Config,
    request: Option<&str>,
    plan_path: Option<&Path>,
    yes: bool,
    dry_run: bool,
    pretty: bool,
) -> Result<()> {
    // Safety check
    if !yes && !dry_run {
        if pretty {
            println!("Error: --yes flag required to execute changes");
            println!("Use --dry-run to validate without executing");
        } else {
            println!("{}", json!({
                "error": "--yes flag required to execute changes"
            }));
        }
        return Ok(());
    }
    
    let bridge = ResolveBridge::new(config);
    
    // Get the plan - either from file or generate from request
    let plan: Plan = if let Some(path) = plan_path {
        // Load plan from file
        let contents = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read plan file: {:?}", path))?;
        serde_json::from_str(&contents)
            .with_context(|| "Failed to parse plan file")?
    } else if let Some(req) = request {
        // Generate plan from request
        let context = bridge.get_context().await
            .context("Failed to get Resolve context")?;
        let client = LlmClient::new(config)?;
        client.generate_plan(&context, req).await?
    } else {
        anyhow::bail!("Either a request or --plan file must be provided");
    };
    
    // Check for error plan
    if plan.is_error() {
        if pretty {
            println!("Cannot execute - plan contains error:");
            println!("  {}", plan.error.as_deref().unwrap_or("Unknown error"));
            if let Some(suggestion) = &plan.suggestion {
                println!("  Suggestion: {}", suggestion);
            }
        } else {
            println!("{}", serde_json::to_string(&plan)?);
        }
        return Ok(());
    }
    
    // Validate plan
    plan.validate().map_err(|e| anyhow::anyhow!("Invalid plan: {}", e))?;
    
    if dry_run {
        if pretty {
            println!("Dry run - plan is valid:\n");
            print_plan_pretty(&plan);
        } else {
            println!("{}", json!({
                "valid": true,
                "plan": plan
            }));
        }
        return Ok(());
    }
    
    // Execute operations
    if pretty {
        println!("Executing {} operations...\n", plan.operations.len());
    }
    
    let mut results = vec![];
    for (i, op) in plan.operations.iter().enumerate() {
        if pretty {
            print!("  {}. {}... ", i + 1, op.op);
        }
        
        match bridge.execute_operation(&op.op, op.params.clone()).await {
            Ok(result) => {
                if pretty {
                    println!("OK");
                }
                results.push(json!({
                    "op": op.op,
                    "status": "success",
                    "result": result
                }));
            }
            Err(e) => {
                if pretty {
                    println!("FAILED: {}", e);
                }
                results.push(json!({
                    "op": op.op,
                    "status": "error",
                    "error": e.to_string()
                }));
            }
        }
    }
    
    if pretty {
        let success_count = results.iter().filter(|r| r["status"] == "success").count();
        println!("\nCompleted: {}/{} operations succeeded", success_count, results.len());
    } else {
        println!("{}", json!({
            "executed": true,
            "results": results
        }));
    }
    
    Ok(())
}
