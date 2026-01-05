use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::process::Stdio;
use tokio::io::AsyncWriteExt;
use tokio::process::Command;

use super::context::{ConnectionInfo, ResolveContext};
use crate::config::Config;

/// Bridge to communicate with DaVinci Resolve via Python
pub struct ResolveBridge {
    python_path: String,
    script_path: String,
}

#[derive(Debug, Serialize)]
struct BridgeCommand {
    op: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    params: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct BridgeResponse {
    success: bool,
    #[serde(default)]
    result: Value,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    code: Option<String>,
}

impl ResolveBridge {
    /// Create a new bridge instance
    pub fn new(config: &Config) -> Self {
        let python_path = config.python_path();

        // Get the path to the bundled Python script
        // Try multiple locations: next to executable, CARGO_MANIFEST_DIR, or cwd
        let script_path = Self::find_script_path();

        Self {
            python_path,
            script_path,
        }
    }

    fn find_script_path() -> String {
        let script_name = "python/resolve_bridge.py";

        // 1. Check next to executable (for installed binaries)
        if let Ok(exe) = std::env::current_exe() {
            if let Some(parent) = exe.parent() {
                let path = parent.join(script_name);
                if path.exists() {
                    return path.to_string_lossy().to_string();
                }
            }
        }

        // 2. Check CARGO_MANIFEST_DIR (for development with cargo run)
        if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
            let path = std::path::Path::new(&manifest_dir).join(script_name);
            if path.exists() {
                return path.to_string_lossy().to_string();
            }
        }

        // 3. Check current working directory
        let cwd_path = std::path::Path::new(script_name);
        if cwd_path.exists() {
            return cwd_path.to_string_lossy().to_string();
        }

        // 4. Fallback - return a path that will be reported as not found
        script_name.to_string()
    }

    /// Execute a command via the Python bridge
    async fn execute(&self, op: &str, params: Option<Value>) -> Result<Value> {
        let command = BridgeCommand {
            op: op.to_string(),
            params,
        };

        let input = serde_json::to_string(&command)?;

        tracing::debug!("Executing bridge command: {}", op);
        tracing::trace!("Command input: {}", input);

        let mut child = Command::new(&self.python_path)
            .arg(&self.script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .with_context(|| format!("Failed to spawn Python at {}", self.python_path))?;

        // Write command to stdin
        if let Some(mut stdin) = child.stdin.take() {
            stdin.write_all(input.as_bytes()).await?;
            stdin.shutdown().await?;
        }

        // Wait for completion and read output
        let output = child.wait_with_output().await?;

        // Log stderr if any
        if !output.stderr.is_empty() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            tracing::warn!("Python stderr: {}", stderr);
        }

        // Parse response
        let stdout = String::from_utf8_lossy(&output.stdout);
        tracing::trace!("Bridge response: {}", stdout);

        let response: BridgeResponse = serde_json::from_str(&stdout)
            .with_context(|| format!("Failed to parse bridge response: {}", stdout))?;

        if response.success {
            Ok(response.result)
        } else {
            let error_msg = response
                .error
                .unwrap_or_else(|| "Unknown error".to_string());
            let code = response.code.unwrap_or_else(|| "PYTHON_ERROR".to_string());
            Err(anyhow::anyhow!("[{}] {}", code, error_msg))
        }
    }

    /// Check if Resolve is running and accessible
    pub async fn check_connection(&self) -> Result<ConnectionInfo> {
        let result = self.execute("check_connection", None).await?;
        let info: ConnectionInfo = serde_json::from_value(result)?;
        Ok(info)
    }

    /// Get full Resolve context
    pub async fn get_context(&self) -> Result<ResolveContext> {
        let result = self.execute("get_context", None).await?;
        let context: ResolveContext = serde_json::from_value(result)?;
        Ok(context)
    }

    /// Execute an operation with parameters
    pub async fn execute_operation(&self, op: &str, params: Value) -> Result<Value> {
        self.execute(op, Some(params)).await
    }

    /// Check if Python is available
    pub async fn check_python(&self) -> Result<String> {
        let output = Command::new(&self.python_path)
            .arg("--version")
            .output()
            .await
            .with_context(|| format!("Python not found at {}", self.python_path))?;

        let version = String::from_utf8_lossy(&output.stdout);
        let version = version.trim();

        // Sometimes --version goes to stderr
        if version.is_empty() {
            let version = String::from_utf8_lossy(&output.stderr);
            Ok(version.trim().to_string())
        } else {
            Ok(version.to_string())
        }
    }

    /// Check if the bridge script exists
    pub fn script_exists(&self) -> bool {
        std::path::Path::new(&self.script_path).exists()
    }

    /// Get the script path
    pub fn script_path(&self) -> &str {
        &self.script_path
    }
}
