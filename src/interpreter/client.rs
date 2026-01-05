use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use super::prompt;
use super::schema::Plan;
use crate::config::Config;
use crate::resolve::context::ResolveContext;

/// LLM client for plan generation
#[derive(Clone)]
pub struct LlmClient {
    api_key: String,
    model: String,
    provider: String,
    base_url: String,
}

#[derive(Debug, Serialize)]
struct AnthropicRequest {
    model: String,
    max_tokens: u32,
    messages: Vec<Message>,
}

#[derive(Debug, Serialize)]
struct Message {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct AnthropicResponse {
    content: Vec<ContentBlock>,
}

#[derive(Debug, Deserialize)]
struct ContentBlock {
    text: Option<String>,
}

impl LlmClient {
    pub fn new(config: &Config) -> Result<Self> {
        let api_key = config.api_key()?.to_string();
        Ok(Self {
            api_key,
            model: config.llm.model().to_string(),
            provider: config.llm.provider.clone(),
            base_url: config.llm.base_url().to_string(),
        })
    }

    /// Create client without requiring API key (for model listing)
    pub fn new_without_auth(config: &Config) -> Self {
        Self {
            api_key: config.llm.api_key.clone().unwrap_or_default(),
            model: config.llm.model().to_string(),
            provider: config.llm.provider.clone(),
            base_url: config.llm.base_url().to_string(),
        }
    }

    /// Fetch available models from the provider
    pub async fn fetch_available_models(&self) -> Result<Vec<String>> {
        let url = format!("{}/models", self.base_url.trim_end_matches('/'));
        let client = reqwest::Client::new();

        let mut request = client.get(&url);
        if !self.api_key.is_empty() && self.api_key != "dummy" {
            request = request.header("Authorization", format!("Bearer {}", self.api_key));
        }

        let response = request
            .send()
            .await
            .with_context(|| format!("Failed to connect to {}", url))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "Failed to fetch models ({}): {}",
                status,
                body
            ));
        }

        let parsed: serde_json::Value = response
            .json()
            .await
            .context("Failed to parse models response")?;

        // Handle OpenAI format: { data: [ { id: "..." }, ... ] }
        let mut models = Vec::new();
        if let Some(data) = parsed.get("data").and_then(|d| d.as_array()) {
            for entry in data {
                if let Some(id) = entry.get("id").and_then(|i| i.as_str()) {
                    models.push(id.to_string());
                }
            }
        }

        Ok(models)
    }

    /// Generate an execution plan from a natural language request
    pub async fn generate_plan(&self, context: &ResolveContext, request: &str) -> Result<Plan> {
        let full_prompt = prompt::build_prompt(context, request);

        let response_text = match self.provider.as_str() {
            "anthropic" => self.call_anthropic(&full_prompt).await?,
            "openai" | "lmstudio" | "custom" => self.call_openai_compatible(&full_prompt).await?,
            "openrouter" => self.call_openrouter(&full_prompt).await?,
            _ => return Err(anyhow::anyhow!("Unknown provider: {}", self.provider)),
        };

        // Strip markdown code blocks if present
        let json_text = Self::extract_json(&response_text);

        // Parse the response as JSON
        let plan: Plan = serde_json::from_str(&json_text)
            .with_context(|| format!("Failed to parse LLM response as plan: {}", response_text))?;

        // Validate the plan
        plan.validate()
            .map_err(|e| anyhow::anyhow!("Invalid plan: {}", e))?;

        Ok(plan)
    }

    /// Extract JSON from a response that might be wrapped in markdown code blocks
    fn extract_json(text: &str) -> String {
        let trimmed = text.trim();

        // Check for ```json ... ``` or ``` ... ```
        if let Some(without_start) = trimmed
            .strip_prefix("```json")
            .or_else(|| trimmed.strip_prefix("```"))
        {
            if let Some(end_pos) = without_start.rfind("```") {
                return without_start[..end_pos].trim().to_string();
            }
        }

        trimmed.to_string()
    }

    async fn call_anthropic(&self, prompt: &str) -> Result<String> {
        let client = reqwest::Client::new();

        let request = AnthropicRequest {
            model: self.model.clone(),
            max_tokens: 4096,
            messages: vec![Message {
                role: "user".to_string(),
                content: prompt.to_string(),
            }],
        };

        let response = client
            .post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to Anthropic API")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "Anthropic API error ({}): {}",
                status,
                body
            ));
        }

        let response: AnthropicResponse = response
            .json()
            .await
            .context("Failed to parse Anthropic response")?;

        response
            .content
            .first()
            .and_then(|block| block.text.clone())
            .ok_or_else(|| anyhow::anyhow!("Empty response from Anthropic"))
    }

    /// Call OpenAI-compatible API (OpenAI, LM Studio, custom endpoints)
    async fn call_openai_compatible(&self, prompt: &str) -> Result<String> {
        let client = reqwest::Client::new();
        let url = format!("{}/chat/completions", self.base_url.trim_end_matches('/'));

        let request = serde_json::json!({
            "model": self.model,
            "messages": [
                { "role": "user", "content": prompt }
            ],
            "max_tokens": 4096
        });

        let mut req_builder = client
            .post(&url)
            .header("content-type", "application/json")
            .json(&request);

        // Add auth header if we have an API key (LM Studio doesn't need it)
        if !self.api_key.is_empty() && self.api_key != "dummy" {
            req_builder = req_builder.header("Authorization", format!("Bearer {}", self.api_key));
        }

        let response = req_builder
            .send()
            .await
            .with_context(|| format!("Failed to send request to {}", url))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "API error ({}) from {}: {}",
                status,
                url,
                body
            ));
        }

        let response: serde_json::Value = response
            .json()
            .await
            .context("Failed to parse API response")?;

        response["choices"][0]["message"]["content"]
            .as_str()
            .map(|s| s.to_string())
            .ok_or_else(|| anyhow::anyhow!("Empty response from {}", self.provider))
    }

    async fn call_openrouter(&self, prompt: &str) -> Result<String> {
        let client = reqwest::Client::new();

        let request = serde_json::json!({
            "model": self.model,
            "messages": [
                { "role": "user", "content": prompt }
            ]
        });

        let response = client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to OpenRouter API")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "OpenRouter API error ({}): {}",
                status,
                body
            ));
        }

        let response: serde_json::Value = response
            .json()
            .await
            .context("Failed to parse OpenRouter response")?;

        response["choices"][0]["message"]["content"]
            .as_str()
            .map(|s| s.to_string())
            .ok_or_else(|| anyhow::anyhow!("Empty response from OpenRouter"))
    }
}
