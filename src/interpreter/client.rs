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
        })
    }

    /// Generate an execution plan from a natural language request
    pub async fn generate_plan(
        &self,
        context: &ResolveContext,
        request: &str,
    ) -> Result<Plan> {
        let full_prompt = prompt::build_prompt(context, request);

        let response_text = match self.provider.as_str() {
            "anthropic" => self.call_anthropic(&full_prompt).await?,
            "openai" => self.call_openai(&full_prompt).await?,
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
        if trimmed.starts_with("```") {
            let without_start = if trimmed.starts_with("```json") {
                &trimmed[7..]
            } else {
                &trimmed[3..]
            };
            
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

    async fn call_openai(&self, prompt: &str) -> Result<String> {
        let client = reqwest::Client::new();

        let request = serde_json::json!({
            "model": self.model,
            "messages": [
                { "role": "user", "content": prompt }
            ],
            "max_tokens": 4096
        });

        let response = client
            .post("https://api.openai.com/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await
            .context("Failed to send request to OpenAI API")?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("OpenAI API error ({}): {}", status, body));
        }

        let response: serde_json::Value = response
            .json()
            .await
            .context("Failed to parse OpenAI response")?;

        response["choices"][0]["message"]["content"]
            .as_str()
            .map(|s| s.to_string())
            .ok_or_else(|| anyhow::anyhow!("Empty response from OpenAI"))
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
