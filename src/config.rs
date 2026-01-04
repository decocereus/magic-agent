use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Deserialize, Serialize, Default)]
#[allow(dead_code)]
pub struct Config {
    #[serde(default)]
    pub llm: LlmConfig,
    #[serde(default)]
    pub resolve: ResolveConfig,
    #[serde(default)]
    pub output: OutputConfig,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct LlmConfig {
    #[serde(default = "default_provider")]
    pub provider: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_url: Option<String>,
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            provider: default_provider(),
            api_key: None,
            model: None,
            base_url: None,
        }
    }
}

impl LlmConfig {
    /// Get the model, using provider-specific defaults if not set
    pub fn model(&self) -> &str {
        self.model
            .as_deref()
            .unwrap_or_else(|| match self.provider.as_str() {
                "anthropic" => "claude-sonnet-4-20250514",
                "openai" => "gpt-4o",
                "openrouter" => "anthropic/claude-sonnet-4-20250514",
                "lmstudio" => "",
                _ => "gpt-4o",
            })
    }

    /// Get the base URL, using provider-specific defaults if not set
    pub fn base_url(&self) -> &str {
        self.base_url
            .as_deref()
            .unwrap_or_else(|| match self.provider.as_str() {
                "anthropic" => "https://api.anthropic.com/v1",
                "openai" => "https://api.openai.com/v1",
                "openrouter" => "https://openrouter.ai/api/v1",
                "lmstudio" => "http://localhost:1234/v1",
                _ => "https://api.openai.com/v1",
            })
    }

    /// Check if this provider requires an API key
    pub fn requires_api_key(&self) -> bool {
        self.provider != "lmstudio"
    }
}

fn default_provider() -> String {
    "anthropic".to_string()
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
            let mut config: Config = toml::from_str(&contents)
                .with_context(|| format!("Failed to parse config from {:?}", config_path))?;

            // Apply environment variable fallbacks
            config.apply_env_fallbacks();
            Ok(config)
        } else {
            let mut config = Config::default();
            config.apply_env_fallbacks();
            Ok(config)
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

    /// Apply environment variable fallbacks for API keys
    fn apply_env_fallbacks(&mut self) {
        if self.llm.api_key.is_none() {
            self.llm.api_key = match self.llm.provider.as_str() {
                "anthropic" => std::env::var("ANTHROPIC_API_KEY").ok(),
                "openai" => std::env::var("OPENAI_API_KEY").ok(),
                "openrouter" => std::env::var("OPENROUTER_API_KEY").ok(),
                "lmstudio" => Some("dummy".to_string()),
                _ => None,
            };
        }
    }

    /// Get the API key, returning an error if not set (except for lmstudio)
    pub fn api_key(&self) -> Result<&str> {
        // LM Studio doesn't need API key
        if self.llm.provider == "lmstudio" {
            return Ok(self.llm.api_key.as_deref().unwrap_or("dummy"));
        }

        self.llm.api_key.as_deref().ok_or_else(|| {
            let env_var = match self.llm.provider.as_str() {
                "anthropic" => "ANTHROPIC_API_KEY",
                "openai" => "OPENAI_API_KEY",
                "openrouter" => "OPENROUTER_API_KEY",
                _ => "API_KEY",
            };
            anyhow::anyhow!(
                "API key not configured for {}.\n\nSet environment variable:\n   export {}=your-key-here\n\nOr add to config file:\n   {}",
                self.llm.provider,
                env_var,
                Self::default_path().display()
            )
        })
    }

    /// Set the provider and reset base_url to use defaults
    pub fn set_provider(&mut self, provider: &str) {
        self.llm.provider = provider.to_string();
        // Clear base_url to use default for new provider
        self.llm.base_url = None;
        // Clear model to use provider default
        self.llm.model = None;
        // For lmstudio, set dummy API key
        if provider == "lmstudio" {
            self.llm.api_key = Some("dummy".to_string());
        }
    }

    /// Write config to file
    pub fn write(&self) -> Result<()> {
        let path = Self::default_path();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create config directory: {:?}", parent))?;
        }
        let toml_str = toml::to_string_pretty(self).context("Failed to serialize config")?;
        std::fs::write(&path, toml_str)
            .with_context(|| format!("Failed to write config to {:?}", path))?;
        Ok(())
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
