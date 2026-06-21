// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

//! # Capability-based policy enforcement
//!
//! Every satellite (agent, MCP, adapter) acts only within an explicitly granted
//! set of capabilities. A capability is a namespaced string `"<domain>.<action>"`
//! (e.g. `"vault.request_credential"`, `"trust.read"`). Grants may use wildcards:
//! `"trust.*"` grants every `trust.*` action, and `"*"` grants everything
//! (reserved for the daemon itself).
//!
//! This module is the Rust-side enforcement arm. The Python SDK
//! (`synapse.security.capabilities`) maintains the canonical capability registry;
//! the string vocabulary must stay in sync across both.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Capability strings the policy enforcer understands.
pub mod cap {
    pub const FS_READ: &str = "fs.read";
    pub const FS_WRITE: &str = "fs.write";
    pub const SHELL_EXEC: &str = "shell.exec";
    pub const NET_PROXIED: &str = "net.proxied";
    pub const TRUST_READ: &str = "trust.read";
    pub const TRUST_WRITE: &str = "trust.write";
    pub const VAULT_REQUEST: &str = "vault.request_credential";
    pub const VAULT_STORE: &str = "vault.store_secret";
    pub const IDENTITY_VERIFY: &str = "identity.verify";
}

/// Commands permitted by default when `shell.exec` is granted.
pub const DEFAULT_COMMAND_WHITELIST: &[&str] = &[
    "ls", "cat", "echo", "pwd", "head", "tail", "grep", "find", "wc", "sort",
    "uniq", "node", "python", "python3", "cargo", "go", "npm", "pnpm", "yarn",
    "git", "bash", "sh",
];

/// Errors raised by capability enforcement.
#[derive(Debug, thiserror::Error)]
pub enum CapabilityError {
    #[error("command not allowed by policy: {0}")]
    CommandNotAllowed(String),
    #[error("path escapes allowed scope: {0}")]
    PathNotAllowed(String),
    #[error("empty command")]
    EmptyCommand,
    #[error("capability not granted: {0}")]
    NotGranted(String),
}

/// Network policy derived from capabilities.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NetworkPolicy {
    None,
    Proxied,
}

/// Whether `capabilities` grants `required` (supports `*` and `ns.*`).
pub fn is_granted(capabilities: &[String], required: &str) -> bool {
    capabilities.iter().any(|granted| {
        granted == "*"
            || granted == required
            || granted
                .strip_suffix(".*")
                .is_some_and(|ns| required.split('.').next() == Some(ns))
    })
}

/// A filesystem/command/network policy derived from granted capabilities.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CapabilityPolicy {
    pub project_root: PathBuf,
    pub writable: bool,
    pub allowed_commands: Vec<String>,
    pub network: NetworkPolicy,
}

impl CapabilityPolicy {
    pub fn from_capabilities(capabilities: &[String], project_root: impl Into<PathBuf>) -> Self {
        let writable = is_granted(capabilities, cap::FS_WRITE);
        let allowed_commands = if is_granted(capabilities, cap::SHELL_EXEC) {
            DEFAULT_COMMAND_WHITELIST.iter().map(|s| s.to_string()).collect()
        } else {
            Vec::new()
        };
        let network = if is_granted(capabilities, cap::NET_PROXIED) {
            NetworkPolicy::Proxied
        } else {
            NetworkPolicy::None
        };
        Self {
            project_root: project_root.into(),
            writable,
            allowed_commands,
            network,
        }
    }

    pub fn is_command_allowed(&self, command: &[String]) -> bool {
        match command.first() {
            Some(exe) => self.allowed_commands.iter().any(|a| a == exe),
            None => false,
        }
    }

    pub fn is_path_allowed(&self, path: &Path) -> bool {
        if path.is_absolute() {
            path.starts_with(&self.project_root)
        } else {
            !path
                .components()
                .any(|c| matches!(c, std::path::Component::ParentDir))
        }
    }

    pub fn validate_command(&self, command: &[String]) -> Result<(), CapabilityError> {
        if command.is_empty() {
            return Err(CapabilityError::EmptyCommand);
        }
        if !self.is_command_allowed(command) {
            return Err(CapabilityError::CommandNotAllowed(command[0].clone()));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn caps(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn policy_reflects_granted_capabilities() {
        let policy = CapabilityPolicy::from_capabilities(
            &caps(&["fs.write", "shell.exec", "net.proxied"]),
            "/repo",
        );
        assert!(policy.writable);
        assert!(!policy.allowed_commands.is_empty());
        assert_eq!(policy.network, NetworkPolicy::Proxied);
    }

    #[test]
    fn read_only_when_no_write_capability() {
        let policy = CapabilityPolicy::from_capabilities(
            &caps(&["fs.read", "shell.exec"]),
            "/repo",
        );
        assert!(!policy.writable);
        assert!(policy.is_command_allowed(&caps(&["ls"])));
    }

    #[test]
    fn rejects_non_whitelisted_command() {
        let policy = CapabilityPolicy::from_capabilities(
            &caps(&["shell.exec"]),
            "/repo",
        );
        let err = policy.validate_command(&caps(&["rm", "-rf", "/"])).unwrap_err();
        assert!(matches!(err, CapabilityError::CommandNotAllowed(_)));
    }

    #[test]
    fn rejects_command_without_shell_exec() {
        let policy = CapabilityPolicy::from_capabilities(
            &caps(&["fs.read"]),
            "/repo",
        );
        assert!(!policy.is_command_allowed(&caps(&["ls"])));
    }

    #[test]
    fn rejects_empty_command() {
        let policy = CapabilityPolicy::from_capabilities(
            &caps(&["shell.exec"]),
            "/repo",
        );
        assert!(matches!(
            policy.validate_command(&[]).unwrap_err(),
            CapabilityError::EmptyCommand
        ));
    }

    #[test]
    fn path_policy_blocks_escapes() {
        let policy = CapabilityPolicy::from_capabilities(
            &caps(&["fs.read"]),
            "/repo",
        );
        assert!(policy.is_path_allowed(Path::new("/repo/src/main.rs")));
        assert!(!policy.is_path_allowed(Path::new("/etc/passwd")));
        assert!(!policy.is_path_allowed(Path::new("../secrets")));
        assert!(policy.is_path_allowed(Path::new("src/main.rs")));
    }

    #[test]
    fn wildcard_grants_all() {
        assert!(is_granted(&caps(&["*"]), "anything.goes"));
        assert!(is_granted(&caps(&["trust.*"]), "trust.read"));
        assert!(!is_granted(&caps(&["trust.*"]), "vault.read"));
    }
}
