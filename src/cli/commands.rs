use anyhow::{Context, Result};
use serde_json::json;
use std::io::{self, Write};
use std::path::Path;

use crate::config::Config;
use crate::interpreter::{LlmClient, Plan};
use crate::resolve::ResolveBridge;

/// Provider info for the selection menu
struct ProviderInfo {
    id: &'static str,
    label: &'static str,
    description: &'static str,
}

const PROVIDERS: &[ProviderInfo] = &[
    ProviderInfo {
        id: "openai",
        label: "OpenAI",
        description: "GPT-4, GPT-4o",
    },
    ProviderInfo {
        id: "anthropic",
        label: "Anthropic",
        description: "Claude",
    },
    ProviderInfo {
        id: "openrouter",
        label: "OpenRouter",
        description: "Multiple models",
    },
    ProviderInfo {
        id: "lmstudio",
        label: "LM Studio",
        description: "Local models",
    },
    ProviderInfo {
        id: "custom",
        label: "Custom",
        description: "OpenAI-compatible API",
    },
];

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
            println!(
                "\nMedia Pool: {} clips, {} folders",
                pool.clips.len(),
                pool.folders.len()
            );
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
    let context = bridge
        .get_context()
        .await
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
            let params_str =
                serde_json::to_string_pretty(&op.params).unwrap_or_else(|_| "{}".to_string());
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
            println!(
                "{}",
                json!({
                    "error": "--yes flag required to execute changes"
                })
            );
        }
        return Ok(());
    }

    let bridge = ResolveBridge::new(config);

    // Get the plan - either from file or generate from request
    let plan: Plan = if let Some(path) = plan_path {
        // Load plan from file
        let contents = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read plan file: {:?}", path))?;
        serde_json::from_str(&contents).with_context(|| "Failed to parse plan file")?
    } else if let Some(req) = request {
        // Generate plan from request
        let context = bridge
            .get_context()
            .await
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
    plan.validate()
        .map_err(|e| anyhow::anyhow!("Invalid plan: {}", e))?;

    if dry_run {
        if pretty {
            println!("Dry run - plan is valid:\n");
            print_plan_pretty(&plan);
        } else {
            println!(
                "{}",
                json!({
                    "valid": true,
                    "plan": plan
                })
            );
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
        println!(
            "\nCompleted: {}/{} operations succeeded",
            success_count,
            results.len()
        );
    } else {
        println!(
            "{}",
            json!({
                "executed": true,
                "results": results
            })
        );
    }

    Ok(())
}

/// Interactive provider selection
pub fn select_provider(config: &mut Config) -> Result<()> {
    println!("\n\u{1F527} Select AI Provider:\n");

    for (i, p) in PROVIDERS.iter().enumerate() {
        let current = if p.id == config.llm.provider {
            " (current)"
        } else {
            ""
        };
        println!("  {}. {:12} - {}{}", i + 1, p.id, p.description, current);
    }

    print!("\nEnter number (1-5) or 'q' to cancel: ");
    io::stdout().flush()?;

    let mut input = String::new();
    io::stdin().read_line(&mut input)?;
    let input = input.trim();

    if input == "q" || input.is_empty() {
        println!("Cancelled.");
        return Ok(());
    }

    let choice: usize = input
        .parse()
        .map_err(|_| anyhow::anyhow!("Invalid selection: {}", input))?;

    if choice < 1 || choice > PROVIDERS.len() {
        return Err(anyhow::anyhow!(
            "Invalid selection: {}. Please enter 1-{}",
            choice,
            PROVIDERS.len()
        ));
    }

    let selected = &PROVIDERS[choice - 1];
    config.set_provider(selected.id);

    // Save config
    config.write()?;

    println!("\n\u{2714} Provider set to: {}", selected.label);
    println!("\n\u{1F4DD} Configuration saved to:");
    println!("   {}", Config::default_path().display());

    // Check API key requirement
    if !config.llm.requires_api_key() {
        println!("\n\u{2714} {} doesn't require an API key.", selected.label);
    } else if config.llm.api_key.is_none() {
        let env_var = match selected.id {
            "anthropic" => "ANTHROPIC_API_KEY",
            "openai" => "OPENAI_API_KEY",
            "openrouter" => "OPENROUTER_API_KEY",
            _ => "API_KEY",
        };

        println!(
            "\n\u{26A0}\u{FE0F}  API key not configured for {}.",
            selected.label
        );
        println!("\n\u{1F4DD} Add your API key to:");
        println!("   {}", Config::default_path().display());
        println!("\n   [llm]");
        println!("   provider = \"{}\"", selected.id);
        println!("   api_key = \"your-key-here\"");
        println!("\nOr set environment variable:");
        println!("   export {}=your-key-here", env_var);
    } else {
        println!("\n\u{2714} API key configured.");
    }

    Ok(())
}

/// List available models from the current provider
pub async fn list_models(config: &Config, pretty: bool) -> Result<()> {
    // Check API key (skip for lmstudio)
    if config.llm.requires_api_key() {
        if let Err(e) = config.api_key() {
            if pretty {
                eprintln!("\u{26A0}\u{FE0F}  {}", e);
            } else {
                println!(
                    "{}",
                    json!({
                        "status": "error",
                        "error": e.to_string(),
                        "config_path": Config::default_path().to_string_lossy()
                    })
                );
            }
            return Ok(());
        }
    }

    let client = LlmClient::new_without_auth(config);

    if pretty {
        println!(
            "\u{1F4E1} Fetching models from {}...\n",
            config.llm.base_url()
        );
    }

    match client.fetch_available_models().await {
        Ok(models) => {
            if pretty {
                if models.is_empty() {
                    println!("\u{26A0}\u{FE0F}  No models found.");
                    if config.llm.base_url().contains("localhost") {
                        println!("\n\u{1F4A1} Troubleshooting:");
                        println!("  - Make sure LM Studio is running");
                        println!("  - Load a model in LM Studio");
                        println!("  - Start the server: Server \u{2192} Start Server");
                    }
                } else {
                    println!("\u{2714} Found {} model(s):\n", models.len());
                    for (i, model) in models.iter().enumerate() {
                        println!("  {}. {}", i + 1, model);
                    }
                }
            } else {
                println!(
                    "{}",
                    json!({
                        "status": "success",
                        "provider": config.llm.provider,
                        "base_url": config.llm.base_url(),
                        "models": models,
                        "count": models.len()
                    })
                );
            }
            Ok(())
        }
        Err(e) => {
            if pretty {
                eprintln!("\u{2718} Failed to fetch models: {}", e);
                if config.llm.base_url().contains("localhost") {
                    eprintln!("\n\u{1F4A1} Troubleshooting:");
                    eprintln!("  - Make sure LM Studio is running");
                    eprintln!(
                        "  - Start the server: LM Studio \u{2192} Server \u{2192} Start Server"
                    );
                    eprintln!("  - Check URL matches: {}", config.llm.base_url());
                } else {
                    eprintln!("\n\u{1F4A1} Troubleshooting:");
                    eprintln!("  - Check API key is valid");
                    eprintln!("  - Check network connection");
                }
            } else {
                println!(
                    "{}",
                    json!({
                        "status": "error",
                        "error": e.to_string()
                    })
                );
            }
            Err(e)
        }
    }
}
