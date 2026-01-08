use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Deserialize, Serialize, Default)]
#[allow(dead_code)]
pub struct Config {
    #[serde(default)]
    pub resolve: ResolveConfig,
    #[serde(default)]
    pub output: OutputConfig,
}

#[derive(Debug, Deserialize, Serialize, Default, Clone)]
pub struct ResolveConfig {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub python_path: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[allow(dead_code)]
pub struct OutputConfig {
    #[serde(default = "default_format")]
    pub default_format: String,
}

impl Default for OutputConfig {
    fn default() -> Self {
        Self {
            default_format: default_format(),
        }
    }
}

fn default_format() -> String {
    "json".to_string()
}

impl Config {
    /// Load config from file or default location
    pub fn load(path: Option<&Path>) -> Result<Self> {
        let config_path = if let Some(p) = path {
            p.to_path_buf()
        } else {
            Self::default_path()
        };

        if config_path.exists() {
            let contents = std::fs::read_to_string(&config_path)
                .with_context(|| format!("Failed to read config from {:?}", config_path))?;
            let config: Config = toml::from_str(&contents)
                .with_context(|| format!("Failed to parse config from {:?}", config_path))?;
            Ok(config)
        } else {
            Ok(Config::default())
        }
    }

    /// Default config path: ~/.config/magic-agent/config.toml
    pub fn default_path() -> std::path::PathBuf {
        // Prefer ~/.config on all platforms for consistency
        if let Some(home) = dirs::home_dir() {
            let xdg_path = home.join(".config").join("magic-agent").join("config.toml");
            if xdg_path.exists() {
                return xdg_path;
            }
        }

        // Fall back to platform-specific config dir
        dirs::config_dir()
            .unwrap_or_else(|| std::path::PathBuf::from("."))
            .join("magic-agent")
            .join("config.toml")
    }

    /// Get the Python path, auto-detecting if not set
    pub fn python_path(&self) -> String {
        self.resolve.python_path.clone().unwrap_or_else(|| {
            // Try common locations
            for path in &[
                "/opt/homebrew/bin/python3",
                "/usr/local/bin/python3",
                "/usr/bin/python3",
                "python3",
            ] {
                if std::process::Command::new(path)
                    .arg("--version")
                    .output()
                    .is_ok()
                {
                    return path.to_string();
                }
            }
            "python3".to_string()
        })
    }
}
