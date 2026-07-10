use clap::{CommandFactory, Parser};

use super::{Cli, Commands, ConfigAction};

#[test]
fn cli_definition_is_valid() {
    Cli::command().debug_assert();
}

#[test]
fn no_subcommand_parses_prompt_as_trailing_args() {
    let cli = Cli::try_parse_from(["CORArs", "write", "a", "function"]).unwrap();
    assert!(cli.command.is_none());
    assert_eq!(cli.prompt, vec!["write", "a", "function"]);
}

#[test]
fn config_init_parses_to_config_action() {
    let cli = Cli::try_parse_from(["CORArs", "config", "init"]).unwrap();
    assert!(matches!(
        cli.command,
        Some(Commands::Config {
            action: ConfigAction::Init
        })
    ));
}

#[test]
fn deleted_flags_are_rejected() {
    assert!(Cli::try_parse_from(["CORArs", "--config-path"]).is_err());
    assert!(Cli::try_parse_from(["CORArs", "--login"]).is_err());
    assert!(Cli::try_parse_from(["CORArs", "--list-sessions"]).is_err());
    assert!(Cli::try_parse_from(["CORArs", "--skills-path"]).is_err());
    assert!(Cli::try_parse_from(["CORArs", "--init-config"]).is_err());
    assert!(Cli::try_parse_from(["CORArs", "--logout"]).is_err());
}
