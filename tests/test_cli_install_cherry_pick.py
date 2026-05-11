"""Integration tests for cherry-pick installation feature."""

import yaml
from lola.__main__ import main as cli
from lola.cli.install import install_cmd


def test_install_with_skills_flag(integration_env):
    """Install with --skills flag installs only selected skills."""
    env = integration_env
    project = env["project"]

    result = env["runner"].invoke(
        install_cmd,
        ["test-module", "--skills", "git-review", "-a", "claude-code", str(project)],
    )

    assert result.exit_code == 0

    # Check that skill was installed
    skill_dir = project / ".claude" / "skills" / "git-review"
    assert skill_dir.exists()

    # Check that commands and agents were NOT installed
    cmd_file = project / ".claude" / "commands" / "review-pr.md"
    assert not cmd_file.exists()
    agent_file = project / ".claude" / "agents" / "code-reviewer.md"
    assert not agent_file.exists()


def test_install_with_commands_flag(integration_env):
    """Install with --commands flag installs only selected commands."""
    env = integration_env
    project = env["project"]

    result = env["runner"].invoke(
        install_cmd,
        ["test-module", "--commands", "review-pr", "-a", "claude-code", str(project)],
    )

    assert result.exit_code == 0

    # Check that command was installed
    cmd_file = project / ".claude" / "commands" / "review-pr.md"
    assert cmd_file.exists()

    # Check that skills and agents were NOT installed
    skill_dir = project / ".claude" / "skills" / "git-review"
    assert not skill_dir.exists()
    agent_file = project / ".claude" / "agents" / "code-reviewer.md"
    assert not agent_file.exists()


def test_install_with_invalid_skill(integration_env):
    """Install with invalid skill name shows error."""
    env = integration_env
    project = env["project"]

    result = env["runner"].invoke(
        install_cmd,
        ["test-module", "--skills", "nonexistent", "-a", "claude-code", str(project)],
    )

    assert result.exit_code != 0
    assert "Unknown skills: nonexistent" in result.output


def test_install_with_empty_selection(integration_env):
    """Install with empty selection shows error."""
    env = integration_env
    project = env["project"]

    result = env["runner"].invoke(
        install_cmd,
        ["test-module", "--skills", "", "-a", "claude-code", str(project)],
    )

    assert result.exit_code != 0
    assert "at least one component" in result.output


def test_install_always_includes_mcps(integration_env):
    """Install always includes MCPs regardless of selection."""
    env = integration_env
    project = env["project"]

    result = env["runner"].invoke(
        install_cmd,
        ["test-module", "--skills", "git-review", "-a", "claude-code", str(project)],
    )

    assert result.exit_code == 0

    # Check that MCP config was created
    # ClaudeCodeTarget uses .mcp.json (not .claude/claude_desktop_config.json)
    mcp_file = project / ".mcp.json"
    assert mcp_file.exists()


def test_update_preserves_selection(integration_env):
    """Update preserves previously selected components."""
    env = integration_env
    project = env["project"]

    # First install with selection
    result = env["runner"].invoke(
        cli,
        ["install", "test-module", "--skills", "git-review", "-a", "claude-code", str(project)],
    )
    assert result.exit_code == 0

    # Update without flags (non-interactive)
    result = env["runner"].invoke(
        cli,
        ["update", "test-module", "-a", "claude-code"],
    )
    assert result.exit_code == 0

    # Should still have only git-review skill
    with open(env["installed_file"]) as f:
        data = yaml.safe_load(f)

    inst = data["installations"][0]
    assert "git-review" in inst["skills"]
    # Other components should not be added automatically
    assert "review-pr" not in inst.get("commands", [])
    assert "quick-commit" not in inst.get("commands", [])
    assert "code-reviewer" not in inst.get("agents", [])


def test_update_with_new_selection_flags(integration_env):
    """Update with component flags applies new selection."""
    env = integration_env
    project = env["project"]

    # First install with git-review skill
    result = env["runner"].invoke(
        cli,
        ["install", "test-module", "--skills", "git-review", "-a", "claude-code", str(project)],
    )
    assert result.exit_code == 0

    # Update with different selection
    result = env["runner"].invoke(
        cli,
        ["update", "test-module", "--commands", "review-pr,quick-commit", "-a", "claude-code"],
    )
    assert result.exit_code == 0

    # Should now have commands instead of skill
    cmd1 = project / ".claude" / "commands" / "review-pr.md"
    cmd2 = project / ".claude" / "commands" / "quick-commit.md"
    assert cmd1.exists()
    assert cmd2.exists()

    # Skill should be removed (orphaned)
    skill_dir = project / ".claude" / "skills" / "git-review"
    assert not skill_dir.exists()

    # Check registry reflects new selection
    with open(env["installed_file"]) as f:
        data = yaml.safe_load(f)

    inst = data["installations"][0]
    assert "review-pr" in inst["commands"]
    assert "quick-commit" in inst["commands"]
    assert "git-review" not in inst.get("skills", [])
