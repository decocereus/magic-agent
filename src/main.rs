mod cli;
mod config;
mod error;
mod interpreter;
mod resolve;

use clap::{Parser, Subcommand};
use std::path::PathBuf;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[derive(Parser)]
#[command(name = "magic-agent")]
#[command(about = "Natural-language editing CLI for DaVinci Resolve")]
#[command(version)]
struct Cli {
    /// Use alternate config file
    #[arg(long, global = true)]
    config: Option<PathBuf>,

    /// Human-readable output instead of JSON
    #[arg(long, global = true)]
    pretty: bool,

    /// Enable debug logging
    #[arg(long, global = true)]
    verbose: bool,

    /// Select AI provider interactively
    #[arg(long)]
    provider: bool,

    /// List available models from current provider
    #[arg(long)]
    list_models: bool,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Check Resolve, Python, and API key status
    Doctor,

    /// Show current project/timeline state
    Status,

    /// Generate an execution plan from natural language
    Plan {
        /// The editing request in natural language
        request: String,
    },

    /// Execute a plan (generate + run, or run from file)
    Apply {
        /// The editing request in natural language
        request: Option<String>,

        /// Execute from saved plan file
        #[arg(long)]
        plan: Option<PathBuf>,

        /// Required to actually execute (safety flag)
        #[arg(long)]
        yes: bool,

        /// Validate plan without executing
        #[arg(long)]
        dry_run: bool,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    // Initialize tracing
    let filter = if cli.verbose { "debug" } else { "info" };
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| filter.into()),
        )
        .with(tracing_subscriber::fmt::layer().with_target(false))
        .init();

    // Load config
    let mut config = config::Config::load(cli.config.as_deref())?;

    // Handle --provider flag (interactive selection)
    if cli.provider {
        return cli::commands::select_provider(&mut config);
    }

    // Handle --list-models flag
    if cli.list_models {
        return cli::commands::list_models(&config, cli.pretty).await;
    }

    // Require a subcommand if no special flags were used
    let command = cli.command.ok_or_else(|| {
        anyhow::anyhow!(
            "No command specified. Use --help for usage, or:\n  \
             --provider    Select AI provider\n  \
             --list-models List available models"
        )
    })?;

    match command {
        Commands::Doctor => cli::commands::doctor(&config, cli.pretty).await,
        Commands::Status => cli::commands::status(&config, cli.pretty).await,
        Commands::Plan { request } => cli::commands::plan(&config, &request, cli.pretty).await,
        Commands::Apply {
            request,
            plan,
            yes,
            dry_run,
        } => {
            cli::commands::apply(
                &config,
                request.as_deref(),
                plan.as_deref(),
                yes,
                dry_run,
                cli.pretty,
            )
            .await
        }
    }
}
