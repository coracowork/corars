// Core agent infrastructure: engine, session, orchestration, output sinks.

pub mod agents_md;
pub mod bootstrap;
pub mod cache_diagnostics;
pub mod commands;
pub mod compact;
pub mod confirm;
pub mod context;
pub mod engine;
pub mod error;
pub mod orchestration;
pub mod output;
pub mod plan;
pub mod session;
pub mod skill_tool;
pub mod spawn_tool;
pub mod spawner;
mod stream;
mod tool_call;
mod turn;
pub mod vcr;

// Re-export the skills crate so existing callers (CORA-cli, tests) can use
// `cora_agent::skills::` without changing their import paths.
pub use cora_skills as skills;
