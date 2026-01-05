pub mod cli;
pub mod config;
pub mod error;
pub mod interpreter;
pub mod resolve;

use anyhow::Result;

pub use config::Config;
pub use error::MagicError as MagicAgentError;
pub use interpreter::schema::Plan;
pub use interpreter::LlmClient;
pub use resolve::context::{ConnectionInfo, ResolveContext};
pub use resolve::ResolveBridge;

/// Main Magic Agent library
/// Provides interface to DaVinci Resolve operations via natural language
pub struct MagicAgent {
    config: Config,
    bridge: ResolveBridge,
    llm_client: Option<LlmClient>,
}

impl MagicAgent {
    /// Create a new MagicAgent instance
    pub fn new() -> Result<Self> {
        let config = Config::load(None)?;
        let bridge = ResolveBridge::new(&config);
        Ok(Self {
            config,
            bridge,
            llm_client: None,
        })
    }

    /// Create a new MagicAgent instance with custom config
    pub fn with_config(config: Config) -> Self {
        let bridge = ResolveBridge::new(&config);
        Self {
            config,
            bridge,
            llm_client: None,
        }
    }

    /// Execute a natural language request
    /// This will:
    /// 1. Get current Resolve context
    /// 2. Generate execution plan via LLM
    /// 3. Execute operations in Resolve
    /// 4. Return result as JSON string
    pub async fn execute_request(&mut self, request: &str) -> Result<String> {
        tracing::info!("Executing request: {}", request);

        let context = self.bridge.get_context().await?;
        tracing::debug!(
            "Got context: {} timelines",
            context
                .project
                .as_ref()
                .map(|p| p.timeline_count)
                .unwrap_or(0)
        );

        if self.llm_client.is_none() {
            self.llm_client = Some(LlmClient::new(&self.config)?);
        }

        let plan: Plan = self
            .llm_client
            .as_ref()
            .unwrap()
            .generate_plan(&context, request)
            .await?;

        if plan.is_error() {
            let error = plan.error.unwrap_or_else(|| "Unknown error".to_string());
            let suggestion = plan.suggestion.unwrap_or_default();
            return Err(anyhow::anyhow!("{} Suggestion: {}", error, suggestion));
        }

        let mut results = vec![];
        for op in &plan.operations {
            match self
                .bridge
                .execute_operation(&op.op, op.params.clone())
                .await
            {
                Ok(result) => {
                    results.push(serde_json::json!({
                        "op": op.op,
                        "status": "success",
                        "result": result
                    }));
                }
                Err(e) => {
                    results.push(serde_json::json!({
                        "op": op.op,
                        "status": "error",
                        "error": e.to_string()
                    }));
                }
            }
        }

        let success_count = results.iter().filter(|r| r["status"] == "success").count();
        let output = serde_json::json!({
            "executed": true,
            "total_operations": results.len(),
            "successful_operations": success_count,
            "results": results
        });

        Ok(serde_json::to_string(&output)?)
    }

    /// Get current DaVinci Resolve context
    pub async fn get_context(&self) -> Result<ResolveContext> {
        self.bridge.get_context().await
    }

    /// Check if Resolve is running and accessible
    pub async fn check_connection(&self) -> Result<ConnectionInfo> {
        self.bridge.check_connection().await
    }

    /// Get the ResolveBridge instance for direct operations
    pub fn bridge(&self) -> &ResolveBridge {
        &self.bridge
    }

    /// Get the LLM client for direct plan generation
    pub async fn llm_client(&mut self) -> Result<&LlmClient> {
        if self.llm_client.is_none() {
            self.llm_client = Some(LlmClient::new(&self.config)?);
        }
        Ok(self.llm_client.as_ref().unwrap())
    }

    /// Update the configuration
    pub fn update_config(&mut self, config: Config) {
        self.config = config;
    }
}
