pub mod config;
pub mod error;
pub mod resolve;

pub use config::Config;
pub use error::MagicError as MagicAgentError;
pub use resolve::context::{ConnectionInfo, ResolveContext};
pub use resolve::operations::ALL as OPERATIONS;
pub use resolve::ResolveBridge;
