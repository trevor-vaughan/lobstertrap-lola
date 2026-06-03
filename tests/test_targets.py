"""Tests for concrete target implementations in targets.py.

This module tests:
- ClaudeCodeTarget: skill directory copying, command passthrough, agent frontmatter
- CursorTarget: MDC format conversion, path rewriting, skill removal
- GeminiTarget: managed section generation, TOML command format
- OpenCodeTarget: file-based skill installation, agent frontmatter
- Helper functions: path rewriting, skill description extraction
"""

import shutil
from pathlib import Path

import click
import pytest
import tomllib

from lola.cli.install import _resolve_install_path
from lola.exceptions import UnknownAssistantError
from lola.models import Installation, InstallationRegistry, Module
from lola.targets import (
    ClaudeCodeTarget,
    CursorTarget,
    GeminiTarget,
    OpenClawTarget,
    OpenCodeTarget,
    _convert_to_gemini_args,
    _get_skill_description,
    get_target,
)
from lola.targets.install import (
    _install_module_tree,
    _uninstall_module_tree,
    install_to_assistant,
    uninstall_from_assistant,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def skill_source(tmp_path: Path) -> Path:
    """Create a skill source directory with SKILL.md and supporting files."""
    skill_dir = tmp_path / "source" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    # Main skill file
    (skill_dir / "SKILL.md").write_text("""---
description: Test skill for unit testing
---

# Test Skill

This is a test skill with some content.

## Usage

Read the helper file at ./scripts/helper.py for more info.
""")

    # Supporting files
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "helper.py").write_text("# Helper script\nprint('hello')")
    (skill_dir / "notes.md").write_text("# Notes\nSome notes here.")

    return skill_dir


@pytest.fixture
def command_source(tmp_path: Path) -> Path:
    """Create a command source file."""
    cmd_dir = tmp_path / "source" / "commands"
    cmd_dir.mkdir(parents=True)
    cmd_file = cmd_dir / "test-cmd.md"
    cmd_file.write_text("""---
description: Test command description
argument-hint: "[type]"
---

Execute a task with $ARGUMENTS.

Use $1 for the first argument and $2 for the second.
""")
    return cmd_file


@pytest.fixture
def agent_source(tmp_path: Path) -> Path:
    """Create an agent source file."""
    agent_dir = tmp_path / "source" / "agents"
    agent_dir.mkdir(parents=True)
    agent_file = agent_dir / "test-agent.md"
    agent_file.write_text("""---
description: Test agent for troubleshooting
---

# Test Agent

You are a helpful assistant.

## Workflow

1. Understand the problem
2. Propose a solution
""")
    return agent_file


@pytest.fixture
def dest_path(tmp_path: Path) -> Path:
    """Create a destination directory for generated files."""
    dest = tmp_path / "dest"
    dest.mkdir()
    return dest


# =============================================================================
# ClaudeCodeTarget Tests
# =============================================================================


class TestClaudeCodeTarget:
    """Tests for ClaudeCodeTarget implementation."""

    def test_name_and_attributes(self):
        """Verify target name and capability attributes."""
        target = ClaudeCodeTarget()
        assert target.name == "claude-code"
        assert target.supports_agents is True
        assert target.uses_managed_section is False

    def test_get_skill_path(self, tmp_path: Path):
        """Skill path should be .claude/skills."""
        target = ClaudeCodeTarget()
        path = target.get_skill_path(str(tmp_path))
        assert path == tmp_path / ".claude" / "skills"

    def test_get_command_path(self, tmp_path: Path):
        """Command path should be .claude/commands."""
        target = ClaudeCodeTarget()
        path = target.get_command_path(str(tmp_path))
        assert path == tmp_path / ".claude" / "commands"

    def test_get_agent_path(self, tmp_path: Path):
        """Agent path should be .claude/agents."""
        target = ClaudeCodeTarget()
        path = target.get_agent_path(str(tmp_path))
        assert path == tmp_path / ".claude" / "agents"

    def test_generate_skill_copies_skill_md(self, skill_source: Path, dest_path: Path):
        """generate_skill should copy SKILL.md to destination."""
        target = ClaudeCodeTarget()
        result = target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        assert result is True
        skill_dest = dest_path / "mymod-test-skill"
        assert skill_dest.exists()
        assert (skill_dest / "SKILL.md").exists()

        content = (skill_dest / "SKILL.md").read_text()
        assert "Test skill for unit testing" in content

    def test_generate_skill_copies_supporting_files(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should copy supporting files and directories."""
        target = ClaudeCodeTarget()
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        skill_dest = dest_path / "mymod-test-skill"
        assert (skill_dest / "scripts" / "helper.py").exists()
        assert (skill_dest / "notes.md").exists()

    def test_generate_skill_returns_false_for_missing_source(
        self,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_skill should return False when source doesn't exist."""
        target = ClaudeCodeTarget()
        missing = tmp_path / "nonexistent"
        result = target.generate_skill(missing, dest_path, "missing-skill")
        assert result is False

    def test_generate_skill_overwrites_existing_directories(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should overwrite existing supporting directories."""
        target = ClaudeCodeTarget()
        skill_dest = dest_path / "mymod-test-skill"

        # First generation
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        # Modify source
        (skill_source / "scripts" / "new_file.py").write_text("new content")

        # Second generation should overwrite
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        assert (skill_dest / "scripts" / "new_file.py").exists()

    def test_generate_command_creates_file(self, command_source: Path, dest_path: Path):
        """generate_command should create properly named markdown file."""
        target = ClaudeCodeTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        cmd_file = dest_path / "test-cmd.md"
        assert cmd_file.exists()

        content = cmd_file.read_text()
        assert "Test command description" in content
        assert "$ARGUMENTS" in content

    def test_generate_command_returns_false_for_missing_source(
        self,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_command should return False when source doesn't exist."""
        target = ClaudeCodeTarget()
        missing = tmp_path / "nonexistent.md"
        result = target.generate_command(missing, dest_path, "missing", "mymod")
        assert result is False

    def test_generate_command_copies_sidecar_directory(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """A co-named sidecar directory (commands/test-cmd/ next to
        commands/test-cmd.md) holding supporting procedure files must be
        copied alongside the command file so ${COMMAND_DIR}/test-cmd/* resolves.
        """
        sidecar = command_source.parent / "test-cmd"
        (sidecar / "nested").mkdir(parents=True)
        (sidecar / "phase.md").write_text("# Phase\nProcedure content.")
        (sidecar / "nested" / "data.md").write_text("nested data")

        target = ClaudeCodeTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        assert (dest_path / "test-cmd.md").exists()
        assert (
            dest_path / "test-cmd" / "phase.md"
        ).read_text() == "# Phase\nProcedure content."
        assert (dest_path / "test-cmd" / "nested" / "data.md").exists()

    def test_generate_command_without_sidecar_creates_no_directory(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """When no co-named sidecar directory exists, only the command file is
        created (no spurious directory)."""
        target = ClaudeCodeTarget()
        target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert (dest_path / "test-cmd.md").exists()
        assert not (dest_path / "test-cmd").exists()

    def test_generate_command_overwrites_existing_sidecar(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """Reinstall (the update path) must replace a stale sidecar directory:
        files removed from the source disappear, and changed files update."""
        sidecar = command_source.parent / "test-cmd"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("v1")
        (sidecar / "stale.md").write_text("removed next time")

        target = ClaudeCodeTarget()
        target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        # Source changes between installs: phase.md updated, stale.md deleted.
        (sidecar / "phase.md").write_text("v2")
        (sidecar / "stale.md").unlink()
        target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert (dest_path / "test-cmd" / "phase.md").read_text() == "v2"
        assert not (dest_path / "test-cmd" / "stale.md").exists()

    def test_generate_command_removes_stale_sidecar_when_source_drops_it(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """When a module update drops the sidecar directory, reinstalling the
        command must remove the previously installed sidecar so stale files
        don't linger."""
        sidecar = command_source.parent / "test-cmd"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("procedure")

        target = ClaudeCodeTarget()
        target.generate_command(command_source, dest_path, "test-cmd", "mymod")
        assert (dest_path / "test-cmd" / "phase.md").exists()

        # Source drops the sidecar between versions.
        shutil.rmtree(sidecar)
        target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert (dest_path / "test-cmd.md").exists()
        assert not (dest_path / "test-cmd").exists()

    def test_generate_command_with_module_dir_preamble(
        self,
        command_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_command should inject preamble into command file
        when module_dir provided."""
        target = ClaudeCodeTarget()
        module_dir = tmp_path / ".claude" / "modules" / "test-mod"
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
            module_dir=module_dir,
        )
        assert result is True
        content = (dest_path / "test-cmd.md").read_text()
        assert f"Module root: {module_dir}" in content

    def test_generate_command_without_module_dir_no_preamble(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """generate_command should NOT inject preamble when module_dir is None."""
        target = ClaudeCodeTarget()
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
        )
        assert result is True
        content = (dest_path / "test-cmd.md").read_text()
        assert "Module root:" not in content

    def test_generate_command_no_frontmatter_with_module_dir(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """Command without frontmatter should get preamble prepended at file start."""
        cmd_dir = tmp_path / "source" / "commands"
        cmd_dir.mkdir(parents=True, exist_ok=True)
        cmd_file = cmd_dir / "plain-cmd.md"
        cmd_file.write_text("# Plain command\n\nDo the thing with $ARGUMENTS.")

        target = ClaudeCodeTarget()
        module_dir = tmp_path / ".claude" / "modules" / "test-mod"
        result = target.generate_command(
            cmd_file,
            dest_path,
            "plain-cmd",
            "test-mod",
            module_dir=module_dir,
        )
        assert result is True
        content = (dest_path / "plain-cmd.md").read_text()
        assert f"Module root: {module_dir}" in content
        assert content.index(f"Module root: {module_dir}") < content.index(
            "# Plain command",
        )

    def test_generate_agent_adds_model_inherit(
        self,
        agent_source: Path,
        dest_path: Path,
    ):
        """generate_agent should add model: inherit to frontmatter."""
        target = ClaudeCodeTarget()
        result = target.generate_agent(agent_source, dest_path, "test-agent", "mymod")

        assert result is True
        agent_file = dest_path / "test-agent.md"
        assert agent_file.exists()

        content = agent_file.read_text()
        assert "model: inherit" in content
        assert "description: Test agent for troubleshooting" in content
        assert "# Test Agent" in content

    def test_generate_agent_preserves_existing_frontmatter(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """generate_agent should preserve existing frontmatter fields."""
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        agent_file = agent_dir / "custom.md"
        agent_file.write_text("""---
description: Custom agent
custom_field: custom_value
tags:
  - tag1
  - tag2
---

Agent body content.
""")

        target = ClaudeCodeTarget()
        target.generate_agent(agent_file, dest_path, "custom", "mymod")

        result_file = dest_path / "custom.md"
        content = result_file.read_text()

        assert "model: inherit" in content
        assert "custom_field: custom_value" in content
        assert "tag1" in content

    def test_remove_skill_deletes_directory(self, dest_path: Path):
        """remove_skill should delete the skill directory."""
        target = ClaudeCodeTarget()
        skill_dir = dest_path / "mymod-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        result = target.remove_skill(dest_path, "mymod-skill")

        assert result is True
        assert not skill_dir.exists()

    def test_remove_skill_returns_false_when_not_exists(self, dest_path: Path):
        """remove_skill should return False when directory doesn't exist."""
        target = ClaudeCodeTarget()
        result = target.remove_skill(dest_path, "nonexistent")
        assert result is False

    def test_get_command_filename(self):
        """Command filename should be cmd.md (no prefix)."""
        target = ClaudeCodeTarget()
        filename = target.get_command_filename("mymod", "do-thing")
        assert filename == "do-thing.md"

    def test_get_agent_filename(self):
        """Agent filename should be agent.md (no prefix)."""
        target = ClaudeCodeTarget()
        filename = target.get_agent_filename("mymod", "helper")
        assert filename == "helper.md"

    def test_remove_command_deletes_file(self, dest_path: Path):
        """remove_command should delete the command file."""
        target = ClaudeCodeTarget()
        commands_dir = dest_path
        cmd_file = commands_dir / "review-pr.md"
        cmd_file.write_text("# Review PR Command")

        result = target.remove_command(commands_dir, "review-pr", "mymod")

        assert result is True
        assert not cmd_file.exists()

    def test_remove_command_idempotent_when_file_missing(self, dest_path: Path):
        """remove_command should succeed even if file doesn't exist."""
        target = ClaudeCodeTarget()
        commands_dir = dest_path

        result = target.remove_command(commands_dir, "nonexistent", "mymod")

        assert result is True  # Idempotent - no error

    def test_remove_command_removes_sidecar_directory(self, dest_path: Path):
        """remove_command should also remove the co-named sidecar directory
        installed alongside the command file."""
        target = ClaudeCodeTarget()
        commands_dir = dest_path
        (commands_dir / "review-pr.md").write_text("# entry")
        sidecar = commands_dir / "review-pr"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("procedure")

        result = target.remove_command(commands_dir, "review-pr", "mymod")

        assert result is True
        assert not (commands_dir / "review-pr.md").exists()
        assert not sidecar.exists()

    def test_remove_agent_deletes_file(self, dest_path: Path):
        """remove_agent should delete the agent file."""
        target = ClaudeCodeTarget()
        agents_dir = dest_path
        agent_file = agents_dir / "code-reviewer.md"
        agent_file.write_text("# Code Reviewer Agent")

        result = target.remove_agent(agents_dir, "code-reviewer", "mymod")

        assert result is True
        assert not agent_file.exists()

    def test_remove_agent_idempotent_when_file_missing(self, dest_path: Path):
        """remove_agent should succeed even if file doesn't exist."""
        target = ClaudeCodeTarget()
        agents_dir = dest_path

        result = target.remove_agent(agents_dir, "nonexistent", "mymod")

        assert result is True  # Idempotent - no error

    def test_remove_command_falls_back_to_legacy_prefixed_name(self, dest_path: Path):
        """remove_command should delete old prefixed files
        from pre-migration installs."""
        target = ClaudeCodeTarget()
        commands_dir = dest_path
        # Simulate file created by old lola (mymod.review-pr.md)
        legacy_file = commands_dir / "mymod.review-pr.md"
        legacy_file.write_text("# Review PR Command")

        result = target.remove_command(commands_dir, "review-pr", "mymod")

        assert result is True
        assert not legacy_file.exists()

    def test_remove_agent_falls_back_to_legacy_prefixed_name(self, dest_path: Path):
        """remove_agent should delete old prefixed files from pre-migration installs."""
        target = ClaudeCodeTarget()
        agents_dir = dest_path
        # Simulate file created by old lola (mymod.code-reviewer.md)
        legacy_file = agents_dir / "mymod.code-reviewer.md"
        legacy_file.write_text("# Code Reviewer Agent")

        result = target.remove_agent(agents_dir, "code-reviewer", "mymod")

        assert result is True
        assert not legacy_file.exists()

    def test_remove_command_removes_both_when_both_exist(self, dest_path: Path):
        """remove_command should remove both new-style and legacy
        files when both exist."""
        target = ClaudeCodeTarget()
        commands_dir = dest_path
        new_file = commands_dir / "review-pr.md"
        new_file.write_text("# New style")
        legacy_file = commands_dir / "mymod.review-pr.md"
        legacy_file.write_text("# Legacy style")

        result = target.remove_command(commands_dir, "review-pr", "mymod")

        assert result is True
        assert not new_file.exists()
        assert not legacy_file.exists()  # Also removed when both coexist

    def test_generate_agent_with_module_dir_preamble(
        self,
        agent_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_agent should inject MODULE_DIR preamble when module_dir provided."""
        target = ClaudeCodeTarget()
        module_dir = tmp_path / ".claude" / "modules" / "test-mod"
        result = target.generate_agent(
            agent_source,
            dest_path,
            "test-agent",
            "test-mod",
            module_dir=module_dir,
        )
        assert result is True

        content = (dest_path / "test-agent.md").read_text()
        assert f"Module root: {module_dir}" in content
        # Preamble should be between frontmatter and body
        lines = content.split("\n")
        closing_idx = None
        found_first = False
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if not found_first:
                    found_first = True
                else:
                    closing_idx = i
                    break
        assert closing_idx is not None
        remaining = "\n".join(lines[closing_idx + 1 :])
        assert f"Module root: {module_dir}" in remaining

    def test_generate_agent_without_module_dir_no_preamble(
        self,
        agent_source: Path,
        dest_path: Path,
    ):
        """generate_agent should NOT inject preamble when module_dir is None."""
        target = ClaudeCodeTarget()
        result = target.generate_agent(
            agent_source,
            dest_path,
            "test-agent",
            "test-mod",
        )
        assert result is True

        content = (dest_path / "test-agent.md").read_text()
        assert "Module root:" not in content

    def test_get_module_path(self, tmp_path: Path):
        """Module path should be .claude/modules."""
        target = ClaudeCodeTarget()
        path = target.get_module_path(str(tmp_path))
        assert path == tmp_path / ".claude" / "modules"

    def test_generate_skill_with_module_dir_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_skill should inject preamble into SKILL.md
        when module_dir provided."""
        target = ClaudeCodeTarget()
        module_dir = tmp_path / ".claude" / "modules" / "test-mod"
        result = target.generate_skill(
            skill_source,
            dest_path,
            "test-skill",
            module_dir=module_dir,
        )
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert f"Module root: {module_dir}" in content
        # Preamble between frontmatter and body
        assert content.index("---", 4) < content.index(f"Module root: {module_dir}")
        assert content.index(f"Module root: {module_dir}") < content.index(
            "# Test Skill",
        )

    def test_generate_skill_without_module_dir_no_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should NOT inject preamble when module_dir is None."""
        target = ClaudeCodeTarget()
        result = target.generate_skill(skill_source, dest_path, "test-skill")
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert "Module root:" not in content


# =============================================================================
# CursorTarget Tests
# =============================================================================


class TestCursorTarget:
    """Tests for CursorTarget implementation (Cursor 2.4+)."""

    def test_name_and_attributes(self):
        """Verify target name and capability attributes."""
        target = CursorTarget()
        assert target.name == "cursor"
        assert target.supports_agents is True  # Cursor 2.4+ supports subagents
        assert target.uses_managed_section is False

    def test_get_skill_path(self, tmp_path: Path):
        """Skill path should be .cursor/skills (Cursor 2.4+)."""
        target = CursorTarget()
        path = target.get_skill_path(str(tmp_path))
        assert path == tmp_path / ".cursor" / "skills"

    def test_get_command_path(self, tmp_path: Path):
        """Command path should be .cursor/commands."""
        target = CursorTarget()
        path = target.get_command_path(str(tmp_path))
        assert path == tmp_path / ".cursor" / "commands"

    def test_get_agent_path(self, tmp_path: Path):
        """Agent path should be .cursor/agents (Cursor 2.4+ supports subagents)."""
        target = CursorTarget()
        path = target.get_agent_path(str(tmp_path))
        assert path == tmp_path / ".cursor" / "agents"

    def test_generate_skill_copies_skill_md(self, skill_source: Path, dest_path: Path):
        """generate_skill should copy SKILL.md to destination (Cursor 2.4+)."""
        target = CursorTarget()
        result = target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        assert result is True
        skill_dest = dest_path / "mymod-test-skill"
        assert skill_dest.exists()
        assert (skill_dest / "SKILL.md").exists()

        content = (skill_dest / "SKILL.md").read_text()
        assert "Test skill for unit testing" in content

    def test_generate_skill_copies_supporting_files(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should copy supporting files and directories."""
        target = CursorTarget()
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        skill_dest = dest_path / "mymod-test-skill"
        assert (skill_dest / "scripts" / "helper.py").exists()
        assert (skill_dest / "notes.md").exists()

    def test_generate_skill_returns_false_for_missing_skill_md(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """generate_skill should return False when SKILL.md is missing."""
        empty_dir = tmp_path / "empty_skill"
        empty_dir.mkdir()

        target = CursorTarget()
        result = target.generate_skill(empty_dir, dest_path, "empty", str(tmp_path))
        assert result is False

    def test_generate_skill_overwrites_existing_directories(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should overwrite existing supporting directories."""
        target = CursorTarget()
        skill_dest = dest_path / "mymod-test-skill"

        # First generation
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        # Modify source
        (skill_source / "scripts" / "new_file.py").write_text("new content")

        # Second generation should overwrite
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        assert (skill_dest / "scripts" / "new_file.py").exists()

    def test_generate_command_creates_file(self, command_source: Path, dest_path: Path):
        """generate_command should create properly named markdown file."""
        target = CursorTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        cmd_file = dest_path / "test-cmd.md"
        assert cmd_file.exists()

    def test_generate_command_with_module_dir_preamble(
        self,
        command_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_command should inject preamble into command file
        when module_dir provided."""
        target = CursorTarget()
        module_dir = tmp_path / ".cursor" / "modules" / "test-mod"
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
            module_dir=module_dir,
        )
        assert result is True
        content = (dest_path / "test-cmd.md").read_text()
        assert f"Module root: {module_dir}" in content

    def test_generate_command_without_module_dir_no_preamble(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """generate_command should NOT inject preamble when module_dir is None."""
        target = CursorTarget()
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
        )
        assert result is True
        content = (dest_path / "test-cmd.md").read_text()
        assert "Module root:" not in content

    def test_generate_agent_adds_model_inherit(
        self,
        agent_source: Path,
        dest_path: Path,
    ):
        """generate_agent should add model: inherit to frontmatter (Cursor 2.4+)."""
        target = CursorTarget()
        result = target.generate_agent(agent_source, dest_path, "test-agent", "mymod")

        assert result is True
        agent_file = dest_path / "test-agent.md"
        assert agent_file.exists()

        content = agent_file.read_text()
        assert "model: inherit" in content
        assert "description: Test agent for troubleshooting" in content
        assert "# Test Agent" in content

    def test_generate_agent_preserves_existing_frontmatter(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """generate_agent should preserve existing frontmatter fields."""
        agent_dir = tmp_path / "agents"
        agent_dir.mkdir()
        agent_file = agent_dir / "custom.md"
        agent_file.write_text("""---
description: Custom agent
custom_field: custom_value
tags:
  - tag1
  - tag2
---

Agent body content.
""")

        target = CursorTarget()
        target.generate_agent(agent_file, dest_path, "custom", "mymod")

        result_file = dest_path / "custom.md"
        content = result_file.read_text()

        assert "model: inherit" in content
        assert "custom_field: custom_value" in content
        assert "tag1" in content

    def test_remove_skill_deletes_directory(self, dest_path: Path):
        """remove_skill should delete the skill directory (Cursor 2.4+)."""
        target = CursorTarget()
        skill_dir = dest_path / "mymod-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        result = target.remove_skill(dest_path, "mymod-skill")

        assert result is True
        assert not skill_dir.exists()

    def test_remove_skill_returns_false_when_not_exists(self, dest_path: Path):
        """remove_skill should return False when directory doesn't exist."""
        target = CursorTarget()
        result = target.remove_skill(dest_path, "nonexistent")
        assert result is False

    def test_remove_agent_deletes_file(self, dest_path: Path):
        """remove_agent should delete the agent file (Cursor 2.4+)."""
        target = CursorTarget()
        agents_dir = dest_path
        agent_file = agents_dir / "code-reviewer.md"
        agent_file.write_text("# Code Reviewer Agent")

        result = target.remove_agent(agents_dir, "code-reviewer", "mymod")

        assert result is True
        assert not agent_file.exists()

    def test_remove_agent_idempotent_when_file_missing(self, dest_path: Path):
        """remove_agent should succeed even if file doesn't exist."""
        target = CursorTarget()
        agents_dir = dest_path

        result = target.remove_agent(agents_dir, "nonexistent", "mymod")

        assert result is True  # Idempotent - no error

    def test_get_module_path(self, tmp_path: Path):
        """Module path should be .cursor/modules."""
        target = CursorTarget()
        path = target.get_module_path(str(tmp_path))
        assert path == tmp_path / ".cursor" / "modules"

    def test_generate_skill_with_module_dir_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_skill should inject preamble into SKILL.md
        when module_dir provided."""
        target = CursorTarget()
        module_dir = tmp_path / ".cursor" / "modules" / "test-mod"
        result = target.generate_skill(
            skill_source,
            dest_path,
            "test-skill",
            module_dir=module_dir,
        )
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert f"Module root: {module_dir}" in content
        # Preamble between frontmatter and body
        assert content.index("---", 4) < content.index(f"Module root: {module_dir}")
        assert content.index(f"Module root: {module_dir}") < content.index(
            "# Test Skill",
        )

    def test_generate_skill_without_module_dir_no_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should NOT inject preamble when module_dir is None."""
        target = CursorTarget()
        result = target.generate_skill(skill_source, dest_path, "test-skill")
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert "Module root:" not in content

    def test_generate_command_copies_sidecar_directory(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """Cursor must also copy a co-named command sidecar directory."""
        sidecar = command_source.parent / "test-cmd"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("procedure")

        target = CursorTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        assert (dest_path / "test-cmd.md").exists()
        assert (dest_path / "test-cmd" / "phase.md").read_text() == "procedure"

    def test_remove_command_removes_sidecar_directory(self, dest_path: Path):
        """remove_command should also remove the co-named sidecar directory."""
        target = CursorTarget()
        commands_dir = dest_path
        (commands_dir / "review-pr.md").write_text("# entry")
        sidecar = commands_dir / "review-pr"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("procedure")

        result = target.remove_command(commands_dir, "review-pr", "mymod")

        assert result is True
        assert not (commands_dir / "review-pr.md").exists()
        assert not sidecar.exists()


# =============================================================================
# GeminiTarget Tests
# =============================================================================


class TestGeminiTarget:
    """Tests for GeminiTarget (ManagedSectionTarget) implementation."""

    def test_name_and_attributes(self):
        """Verify target name and capability attributes."""
        target = GeminiTarget()
        assert target.name == "gemini-cli"
        assert target.supports_agents is False
        assert target.uses_managed_section is True
        assert target.MANAGED_FILE == "GEMINI.md"

    def test_get_skill_path(self, tmp_path: Path):
        """Skill path should be GEMINI.md file."""
        target = GeminiTarget()
        path = target.get_skill_path(str(tmp_path))
        assert path == tmp_path / "GEMINI.md"

    def test_get_command_path(self, tmp_path: Path):
        """Command path should be .gemini/commands."""
        target = GeminiTarget()
        path = target.get_command_path(str(tmp_path))
        assert path == tmp_path / ".gemini" / "commands"

    def test_generate_skill_raises_not_implemented(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should raise NotImplementedError."""
        target = GeminiTarget()
        with pytest.raises(NotImplementedError):
            target.generate_skill(skill_source, dest_path, "skill", str(dest_path))

    def test_generate_skills_batch_creates_file(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """generate_skills_batch should create GEMINI.md with skill listings."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"

        skills = [
            ("test-skill", "Test skill description", skill_source),
        ]

        result = target.generate_skills_batch(dest_file, "mymod", skills, str(tmp_path))

        assert result is True
        assert dest_file.exists()

        content = dest_file.read_text()
        assert target.START_MARKER in content
        assert target.END_MARKER in content
        assert "### mymod" in content
        assert "#### test-skill" in content
        assert "Test skill description" in content

    def test_generate_skills_batch_updates_existing_file(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """generate_skills_batch should update existing file content."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"

        # Create existing content
        dest_file.write_text("""# My Project

Some existing content here.
""")

        skills = [("skill1", "Description 1", skill_source)]
        target.generate_skills_batch(dest_file, "mymod", skills, str(tmp_path))

        content = dest_file.read_text()
        assert "# My Project" in content
        assert "Some existing content here" in content
        assert target.START_MARKER in content
        assert "### mymod" in content

    def test_generate_skills_batch_replaces_module_section(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """generate_skills_batch should replace existing module section."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"

        # First batch
        skills1 = [("skill1", "Old description", skill_source)]
        target.generate_skills_batch(dest_file, "mymod", skills1, str(tmp_path))

        # Second batch with different skills
        skills2 = [("skill2", "New description", skill_source)]
        target.generate_skills_batch(dest_file, "mymod", skills2, str(tmp_path))

        content = dest_file.read_text()
        # Should have new skill, not old
        assert "skill2" in content
        assert "New description" in content
        # Old skill should be replaced
        assert content.count("### mymod") == 1

    def test_generate_skills_batch_preserves_other_modules(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """generate_skills_batch should preserve other modules' sections."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"

        # Add first module
        skills1 = [("skill1", "Module 1 skill", skill_source)]
        target.generate_skills_batch(dest_file, "module1", skills1, str(tmp_path))

        # Add second module
        skills2 = [("skill2", "Module 2 skill", skill_source)]
        target.generate_skills_batch(dest_file, "module2", skills2, str(tmp_path))

        content = dest_file.read_text()
        assert "### module1" in content
        assert "### module2" in content
        assert "Module 1 skill" in content
        assert "Module 2 skill" in content

    def test_generate_command_creates_toml_file(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """generate_command should create TOML file with proper format."""
        target = GeminiTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        toml_file = dest_path / "test-cmd.toml"
        assert toml_file.exists()

        content = toml_file.read_text()
        assert 'description = "Test command description"' in content
        assert 'prompt = """' in content
        assert "{{args}}" in content  # $ARGUMENTS should be converted

    def test_generate_command_escapes_special_chars_in_description(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """generate_command should escape special characters in description."""
        cmd_dir = tmp_path / "commands"
        cmd_dir.mkdir()
        cmd_file = cmd_dir / "special.md"
        cmd_file.write_text("""---
description: Test with "quotes" and \\backslash
---

Command body.
""")

        target = GeminiTarget()
        target.generate_command(cmd_file, dest_path, "special", "mymod")

        toml_file = dest_path / "special.toml"
        content = toml_file.read_text()
        assert '\\"quotes\\"' in content
        assert "\\\\backslash" in content

    def test_generate_command_escapes_triple_quotes_in_prompt(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """generate_command should escape triple quotes in prompt body."""
        cmd_dir = tmp_path / "commands"
        cmd_dir.mkdir()
        cmd_file = cmd_dir / "triplequotes.md"
        cmd_file.write_text('''---
description: Test triple quote escaping
---

Some text before.

comment = """This has
triple quotes
inside"""

Some text after.
''')

        target = GeminiTarget()
        target.generate_command(cmd_file, dest_path, "triplequotes", "mymod")

        toml_file = dest_path / "triplequotes.toml"
        content = toml_file.read_text()

        # Triple quotes should be escaped
        assert r'\"""' in content

        # Validate the TOML is parseable
        parsed = tomllib.loads(content)
        assert "prompt" in parsed
        # The prompt should contain the original triple quotes (unescaped)
        assert '"""' in parsed["prompt"]

    def test_generate_command_module_dir_skipped_in_toml(
        self,
        command_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """Gemini TOML commands should NOT contain preamble even
        when module_dir provided."""
        target = GeminiTarget()
        module_dir = tmp_path / ".gemini" / "modules" / "test-mod"
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
            module_dir=module_dir,
        )
        assert result is True
        content = (dest_path / "test-cmd.toml").read_text()
        assert "Module root:" not in content

    def test_get_command_filename_uses_toml_extension(self):
        """Command filename should use .toml extension (no prefix)."""
        target = GeminiTarget()
        filename = target.get_command_filename("mymod", "do-thing")
        assert filename == "do-thing.toml"

    def test_remove_skill_removes_module_section(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """remove_skill should remove module section from managed file."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"

        # Add two modules
        target.generate_skills_batch(
            dest_file,
            "module1",
            [("s1", "desc1", skill_source)],
            str(tmp_path),
        )
        target.generate_skills_batch(
            dest_file,
            "module2",
            [("s2", "desc2", skill_source)],
            str(tmp_path),
        )

        # Remove module1
        result = target.remove_skill(dest_file, "module1")

        assert result is True
        content = dest_file.read_text()
        assert "### module1" not in content
        assert "### module2" in content

    def test_remove_skill_returns_true_when_file_not_exists(self, tmp_path: Path):
        """remove_skill should return True when file doesn't exist."""
        target = GeminiTarget()
        dest_file = tmp_path / "nonexistent.md"
        result = target.remove_skill(dest_file, "mymod")
        assert result is True

    def test_remove_command_falls_back_to_legacy_toml(self, tmp_path: Path):
        """remove_command should delete old prefixed .toml files
        from pre-migration installs."""
        target = GeminiTarget()
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        # Simulate file created by old lola (mymod.build.toml)
        legacy_file = commands_dir / "mymod.build.toml"
        legacy_file.write_text('description = "Build"\nprompt = """\ndo it\n"""')

        result = target.remove_command(commands_dir, "build", "mymod")

        assert result is True
        assert not legacy_file.exists()

    def test_get_module_path(self, tmp_path: Path):
        """Module path should be .gemini/modules."""
        target = GeminiTarget()
        path = target.get_module_path(str(tmp_path))
        assert path == tmp_path / ".gemini" / "modules"

    def test_generate_skills_batch_with_module_dir(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """Skills batch should include module directory line
        when module_dir provided."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"
        dest_file.write_text("# GEMINI\n")

        module_dir = tmp_path / ".gemini" / "modules" / "test-mod"
        target.generate_skills_batch(
            dest_file,
            "test-mod",
            [("my-skill", "Do something cool", skill_source)],
            str(tmp_path),
            module_dir=module_dir,
        )

        content = dest_file.read_text()
        assert f"**Module root:** `{module_dir}`" in content

    def test_generate_skills_batch_without_module_dir(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """Skills batch should NOT include module directory line
        when module_dir is None."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"
        dest_file.write_text("# GEMINI\n")

        target.generate_skills_batch(
            dest_file,
            "test-mod",
            [("my-skill", "Do something cool", skill_source)],
            str(tmp_path),
        )

        content = dest_file.read_text()
        assert "Module root:" not in content


# =============================================================================
# OpenCodeTarget Tests
# =============================================================================


class TestOpenCodeTarget:
    """Tests for OpenCodeTarget (file-based skills) implementation."""

    def test_name_and_attributes(self):
        """Verify target name and capability attributes."""
        target = OpenCodeTarget()
        assert target.name == "opencode"
        assert target.supports_agents is True
        assert target.uses_managed_section is False

    def test_get_skill_path(self, tmp_path: Path):
        """Skill path should be .opencode/skills directory."""
        target = OpenCodeTarget()
        path = target.get_skill_path(str(tmp_path))
        assert path == tmp_path / ".opencode" / "skills"

    def test_get_command_path(self, tmp_path: Path):
        """Command path should be .opencode/commands."""
        target = OpenCodeTarget()
        path = target.get_command_path(str(tmp_path))
        assert path == tmp_path / ".opencode" / "commands"

    def test_get_agent_path(self, tmp_path: Path):
        """Agent path should be .opencode/agents."""
        target = OpenCodeTarget()
        path = target.get_agent_path(str(tmp_path))
        assert path == tmp_path / ".opencode" / "agents"

    def test_generate_skill_copies_skill_md(self, tmp_path: Path, skill_source: Path):
        """generate_skill should copy SKILL.md to .opencode/skills/<name>/."""
        target = OpenCodeTarget()
        dest_path = tmp_path / ".opencode" / "skills"

        result = target.generate_skill(skill_source, dest_path, "test-skill")

        assert result is True
        skill_file = dest_path / "test-skill" / "SKILL.md"
        assert skill_file.exists()
        content = skill_file.read_text()
        assert "description: Test skill for unit testing" in content

    def test_generate_skill_copies_supporting_files(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """generate_skill should copy supporting files alongside SKILL.md."""
        target = OpenCodeTarget()
        dest_path = tmp_path / ".opencode" / "skills"

        result = target.generate_skill(skill_source, dest_path, "test-skill")

        assert result is True
        # The fixture already includes scripts/helper.py and notes.md
        assert (dest_path / "test-skill" / "scripts" / "helper.py").exists()
        assert (dest_path / "test-skill" / "notes.md").exists()

    def test_generate_skill_returns_false_for_missing_skill_md(self, tmp_path: Path):
        """generate_skill should return False when SKILL.md is missing."""
        target = OpenCodeTarget()
        empty_source = tmp_path / "empty-skill"
        empty_source.mkdir()
        dest_path = tmp_path / ".opencode" / "skills"

        result = target.generate_skill(empty_source, dest_path, "test-skill")

        assert result is False

    def test_generate_command_creates_markdown_file(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """generate_command should create markdown file (passthrough)."""
        target = OpenCodeTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        cmd_file = dest_path / "test-cmd.md"
        assert cmd_file.exists()

        # Should be passthrough (not converted to TOML)
        content = cmd_file.read_text()
        assert "---" in content
        assert "description:" in content

    def test_generate_command_copies_sidecar_directory(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """OpenCode must also copy a co-named command sidecar directory."""
        sidecar = command_source.parent / "test-cmd"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("procedure")

        target = OpenCodeTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")

        assert result is True
        assert (dest_path / "test-cmd.md").exists()
        assert (dest_path / "test-cmd" / "phase.md").read_text() == "procedure"

    def test_generate_command_with_module_dir_preamble(
        self,
        command_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_command should inject preamble into command file
        when module_dir provided."""
        target = OpenCodeTarget()
        module_dir = tmp_path / ".opencode" / "modules" / "test-mod"
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
            module_dir=module_dir,
        )
        assert result is True
        content = (dest_path / "test-cmd.md").read_text()
        assert f"Module root: {module_dir}" in content

    def test_generate_command_without_module_dir_no_preamble(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """generate_command should NOT inject preamble when module_dir is None."""
        target = OpenCodeTarget()
        result = target.generate_command(
            command_source,
            dest_path,
            "test-cmd",
            "test-mod",
        )
        assert result is True
        content = (dest_path / "test-cmd.md").read_text()
        assert "Module root:" not in content

    def test_generate_agent_adds_mode_subagent(
        self,
        agent_source: Path,
        dest_path: Path,
    ):
        """generate_agent should add mode: subagent to frontmatter."""
        target = OpenCodeTarget()
        result = target.generate_agent(agent_source, dest_path, "test-agent", "mymod")

        assert result is True
        agent_file = dest_path / "test-agent.md"
        assert agent_file.exists()

        content = agent_file.read_text()
        assert "mode: subagent" in content
        assert "description: Test agent for troubleshooting" in content

    def test_remove_command_removes_sidecar_directory(self, dest_path: Path):
        """remove_command should also remove the co-named sidecar directory."""
        target = OpenCodeTarget()
        commands_dir = dest_path
        (commands_dir / "review-pr.md").write_text("# entry")
        sidecar = commands_dir / "review-pr"
        sidecar.mkdir()
        (sidecar / "phase.md").write_text("procedure")

        result = target.remove_command(commands_dir, "review-pr", "mymod")

        assert result is True
        assert not (commands_dir / "review-pr.md").exists()
        assert not sidecar.exists()

    def test_remove_command_cleans_up_legacy_singular_dir(self, tmp_path: Path):
        """remove_command removes files from old .opencode/command/
        (singular) directory."""
        target = OpenCodeTarget()
        opencode_dir = tmp_path / ".opencode"
        # New-style directory (current)
        new_dir = opencode_dir / "commands"
        new_dir.mkdir(parents=True)
        # Legacy directory (pre-rename singular path)
        legacy_dir = opencode_dir / "command"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "review-pr.md").write_text("legacy command")

        result = target.remove_command(new_dir, "review-pr", "mymod")

        assert result is True
        assert not (legacy_dir / "review-pr.md").exists()

    def test_remove_agent_cleans_up_legacy_singular_dir(self, tmp_path: Path):
        """remove_agent removes files from old .opencode/agent/ (singular) directory."""
        target = OpenCodeTarget()
        opencode_dir = tmp_path / ".opencode"
        new_dir = opencode_dir / "agents"
        new_dir.mkdir(parents=True)
        legacy_dir = opencode_dir / "agent"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "code-reviewer.md").write_text("legacy agent")

        result = target.remove_agent(new_dir, "code-reviewer", "mymod")

        assert result is True
        assert not (legacy_dir / "code-reviewer.md").exists()

    def test_get_module_path(self, tmp_path: Path):
        """Module path should be .opencode/modules."""
        target = OpenCodeTarget()
        path = target.get_module_path(str(tmp_path))
        assert path == tmp_path / ".opencode" / "modules"

    def test_generate_skill_with_module_dir_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_skill should inject preamble into SKILL.md
        when module_dir provided."""
        target = OpenCodeTarget()
        module_dir = tmp_path / ".opencode" / "modules" / "test-mod"
        result = target.generate_skill(
            skill_source,
            dest_path,
            "test-skill",
            module_dir=module_dir,
        )
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert f"Module root: {module_dir}" in content
        # Preamble between frontmatter and body
        assert content.index("---", 4) < content.index(f"Module root: {module_dir}")
        assert content.index(f"Module root: {module_dir}") < content.index(
            "# Test Skill",
        )

    def test_generate_skill_without_module_dir_no_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should NOT inject preamble when module_dir is None."""
        target = OpenCodeTarget()
        result = target.generate_skill(skill_source, dest_path, "test-skill")
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert "Module root:" not in content


# =============================================================================
# OpenClawTarget Tests
# =============================================================================


class TestOpenClawTarget:
    """Tests for OpenClawTarget implementation."""

    def test_name_and_attributes(self):
        """Verify target name and capability attributes."""
        target = OpenClawTarget()
        assert target.name == "openclaw"
        assert target.supports_agents is False
        assert target.uses_managed_section is False

    def test_get_skill_path(self, tmp_path: Path):
        """Skill path should be skills/ under the given workspace root."""
        target = OpenClawTarget()
        path = target.get_skill_path(str(tmp_path))
        assert path == tmp_path / "skills"

    def test_resolve_workspace_default(self):
        """resolve_workspace(None) should return ~/.openclaw/workspace."""
        result = OpenClawTarget.resolve_workspace(None)
        assert result == Path.home() / ".openclaw" / "workspace"

    def test_resolve_workspace_name(self):
        """resolve_workspace('work') should return ~/.openclaw/workspace-work."""
        result = OpenClawTarget.resolve_workspace("work")
        assert result == Path.home() / ".openclaw" / "workspace-work"

    def test_resolve_workspace_absolute(self, tmp_path: Path):
        """resolve_workspace with an absolute path should resolve it."""
        result = OpenClawTarget.resolve_workspace(str(tmp_path))
        assert result == tmp_path

    def test_resolve_workspace_relative(self, tmp_path: Path, monkeypatch):
        """resolve_workspace with ./path should resolve relative to CWD."""
        monkeypatch.chdir(tmp_path)
        result = OpenClawTarget.resolve_workspace("./myworkspace")
        assert result == tmp_path / "myworkspace"

    def test_resolve_workspace_home(self):
        """resolve_workspace with ~/path should expand home directory."""
        result = OpenClawTarget.resolve_workspace("~/.openclaw/workspace-custom")
        assert result == Path.home() / ".openclaw" / "workspace-custom"

    def test_get_command_path(self, tmp_path: Path):
        """Command path should be .openclaw/commands."""
        target = OpenClawTarget()
        path = target.get_command_path(str(tmp_path))
        assert path == tmp_path / ".openclaw" / "commands"

    def test_generate_skill_copies_skill_md(self, skill_source: Path, dest_path: Path):
        """generate_skill should copy SKILL.md to destination."""
        target = OpenClawTarget()
        result = target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        assert result is True
        skill_dest = dest_path / "mymod-test-skill"
        assert skill_dest.exists()
        assert (skill_dest / "SKILL.md").exists()

        content = (skill_dest / "SKILL.md").read_text()
        assert "Test skill for unit testing" in content

    def test_generate_skill_copies_supporting_files(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should copy supporting files and directories."""
        target = OpenClawTarget()
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        skill_dest = dest_path / "mymod-test-skill"
        assert (skill_dest / "scripts" / "helper.py").exists()
        assert (skill_dest / "notes.md").exists()

    def test_generate_skill_returns_false_for_missing_source(
        self,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_skill should return False when source doesn't exist."""
        target = OpenClawTarget()
        missing = tmp_path / "nonexistent"
        result = target.generate_skill(missing, dest_path, "missing-skill")
        assert result is False

    def test_generate_skill_returns_false_for_missing_skill_md(
        self,
        tmp_path: Path,
        dest_path: Path,
    ):
        """generate_skill should return False when SKILL.md is missing."""
        empty_dir = tmp_path / "empty_skill"
        empty_dir.mkdir()

        target = OpenClawTarget()
        result = target.generate_skill(empty_dir, dest_path, "empty")
        assert result is False

    def test_generate_skill_overwrites_existing(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should overwrite existing supporting directories."""
        target = OpenClawTarget()
        skill_dest = dest_path / "mymod-test-skill"

        target.generate_skill(skill_source, dest_path, "mymod-test-skill")
        (skill_source / "scripts" / "new_file.py").write_text("new content")
        target.generate_skill(skill_source, dest_path, "mymod-test-skill")

        assert (skill_dest / "scripts" / "new_file.py").exists()

    def test_generate_command_returns_false(
        self,
        command_source: Path,
        dest_path: Path,
    ):
        """generate_command should return False — commands not supported."""
        target = OpenClawTarget()
        result = target.generate_command(command_source, dest_path, "test-cmd", "mymod")
        assert result is False

    def test_generate_agent_returns_false(self, agent_source: Path, dest_path: Path):
        """generate_agent should return False — agents not supported."""
        target = OpenClawTarget()
        result = target.generate_agent(agent_source, dest_path, "test-agent", "mymod")
        assert result is False

    def test_remove_skill_deletes_directory(self, dest_path: Path):
        """remove_skill should delete the skill directory."""
        target = OpenClawTarget()
        skill_dir = dest_path / "mymod-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        result = target.remove_skill(dest_path, "mymod-skill")

        assert result is True
        assert not skill_dir.exists()

    def test_remove_skill_returns_false_when_not_exists(self, dest_path: Path):
        """remove_skill should return False when directory doesn't exist."""
        target = OpenClawTarget()
        result = target.remove_skill(dest_path, "nonexistent")
        assert result is False

    def test_get_module_path(self, tmp_path: Path):
        """Module path should be modules/ at project root."""
        target = OpenClawTarget()
        path = target.get_module_path(str(tmp_path))
        assert path == tmp_path / "modules"

    def test_generate_skill_with_module_dir_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
        tmp_path: Path,
    ):
        """generate_skill should inject preamble into SKILL.md
        when module_dir provided."""
        target = OpenClawTarget()
        module_dir = tmp_path / "modules" / "test-mod"
        result = target.generate_skill(
            skill_source,
            dest_path,
            "test-skill",
            module_dir=module_dir,
        )
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert f"Module root: {module_dir}" in content
        # Preamble between frontmatter and body
        assert content.index("---", 4) < content.index(f"Module root: {module_dir}")
        assert content.index(f"Module root: {module_dir}") < content.index(
            "# Test Skill",
        )

    def test_generate_skill_without_module_dir_no_preamble(
        self,
        skill_source: Path,
        dest_path: Path,
    ):
        """generate_skill should NOT inject preamble when module_dir is None."""
        target = OpenClawTarget()
        result = target.generate_skill(skill_source, dest_path, "test-skill")
        assert result is True

        content = (dest_path / "test-skill" / "SKILL.md").read_text()
        assert "Module root:" not in content

    def test_full_skill_installation_workflow(self, skill_source: Path, tmp_path: Path):
        """Test complete install and remove workflow for OpenClaw."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        target = OpenClawTarget()
        skill_dest = target.get_skill_path(str(project_path))
        skill_dest.mkdir(parents=True)

        result = target.generate_skill(
            skill_source,
            skill_dest,
            "mymod-test-skill",
            str(project_path),
        )

        assert result is True
        skill_dir = skill_dest / "mymod-test-skill"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "scripts" / "helper.py").exists()

        result = target.remove_skill(skill_dest, "mymod-test-skill")
        assert result is True
        assert not skill_dir.exists()


# =============================================================================
# _resolve_install_path Tests
# =============================================================================


class TestResolveInstallPath:
    """Tests for _resolve_install_path helper in cli/install.py."""

    def test_non_openclaw_returns_project_path(self, tmp_path: Path):
        """Non-openclaw assistants return project_path unchanged."""
        result = _resolve_install_path("claude-code", str(tmp_path), None)
        assert result == str(tmp_path)

    def test_openclaw_no_workspace_returns_default(self):
        """openclaw with no --workspace returns ~/.openclaw/workspace."""
        result = _resolve_install_path("openclaw", "./", None)
        assert result == str(Path.home() / ".openclaw" / "workspace")

    def test_openclaw_workspace_name_resolves(self):
        """openclaw with workspace name resolves to ~/.openclaw/workspace-{name}."""
        result = _resolve_install_path("openclaw", "./", "work")
        assert result == str(Path.home() / ".openclaw" / "workspace-work")

    def test_openclaw_workspace_absolute_path(self, tmp_path: Path):
        """openclaw with absolute workspace path resolves it."""
        result = _resolve_install_path("openclaw", "./", str(tmp_path))
        assert result == str(tmp_path)

    def test_openclaw_workspace_relative_path(self, tmp_path: Path, monkeypatch):
        """openclaw with relative workspace path resolves to absolute."""
        monkeypatch.chdir(tmp_path)
        result = _resolve_install_path("openclaw", "./", "./myworkspace")
        assert result == str(tmp_path / "myworkspace")

    def test_workspace_with_non_openclaw_raises(self, tmp_path: Path):
        """--workspace with a non-openclaw assistant raises UsageError."""
        with pytest.raises(click.UsageError, match="only valid with -a openclaw"):
            _resolve_install_path("claude-code", str(tmp_path), "work")

    def test_none_assistant_with_workspace_raises(self, tmp_path: Path):
        """--workspace with no assistant raises UsageError."""
        with pytest.raises(click.UsageError, match="only valid with -a openclaw"):
            _resolve_install_path(None, str(tmp_path), "work")


# =============================================================================
# ManagedSectionTarget Base Class Tests
# =============================================================================


class TestManagedSectionTarget:
    """Tests for ManagedSectionTarget base class functionality."""

    def test_start_and_end_markers(self):
        """Verify default markers."""
        target = GeminiTarget()  # Using concrete subclass
        assert target.START_MARKER == "<!-- lola:skills:start -->"
        assert target.END_MARKER == "<!-- lola:skills:end -->"

    def test_header_content(self):
        """Verify header contains usage instructions."""
        target = GeminiTarget()
        assert "## Lola Skills" in target.HEADER
        assert "read_file" in target.HEADER

    def test_generate_skills_batch_includes_relative_path(
        self,
        tmp_path: Path,
        skill_source: Path,
    ):
        """Skills should include relative path to SKILL.md."""
        target = GeminiTarget()
        dest_file = tmp_path / "GEMINI.md"

        skills = [("test-skill", "Description", skill_source)]
        target.generate_skills_batch(dest_file, "mymod", skills, str(tmp_path))

        content = dest_file.read_text()
        assert "SKILL.md" in content
        assert "**Instructions:**" in content


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestGetSkillDescription:
    """Tests for _get_skill_description helper."""

    def test_extracts_description_from_skill_md(self, skill_source: Path):
        """Should extract description from SKILL.md frontmatter."""
        description = _get_skill_description(skill_source)
        assert description == "Test skill for unit testing"

    def test_returns_empty_for_missing_skill_md(self, tmp_path: Path):
        """Should return empty string when SKILL.md doesn't exist."""
        description = _get_skill_description(tmp_path)
        assert description == ""

    def test_returns_empty_for_missing_description(self, tmp_path: Path):
        """Should return empty string when description field is missing."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
title: No description
---

Content here.
""")
        description = _get_skill_description(skill_dir)
        assert description == ""


class TestConvertToGeminiArgs:
    """Tests for _convert_to_gemini_args helper."""

    def test_converts_arguments_placeholder(self):
        """Should convert $ARGUMENTS to {{args}}."""
        content = "Execute $ARGUMENTS now."
        result = _convert_to_gemini_args(content)
        assert "{{args}}" in result
        assert "$ARGUMENTS" not in result

    def test_adds_args_header_for_positional_args(self):
        """Should add Arguments header when $1, $2, etc. are present."""
        content = "First arg: $1, second: $2"
        result = _convert_to_gemini_args(content)
        assert "Arguments: {{args}}" in result

    def test_no_args_header_without_positional_args(self):
        """Should not add header when no positional args present."""
        content = "No positional arguments here."
        result = _convert_to_gemini_args(content)
        assert "Arguments:" not in result


# =============================================================================
# get_target Function Tests
# =============================================================================


class TestGetTarget:
    """Tests for get_target function."""

    def test_returns_correct_target_types(self):
        """Should return correct target instances."""
        assert isinstance(get_target("claude-code"), ClaudeCodeTarget)
        assert isinstance(get_target("cursor"), CursorTarget)
        assert isinstance(get_target("gemini-cli"), GeminiTarget)
        assert isinstance(get_target("openclaw"), OpenClawTarget)
        assert isinstance(get_target("opencode"), OpenCodeTarget)

    def test_raises_for_unknown_assistant(self):
        """Should raise UnknownAssistantError for unknown assistant."""
        with pytest.raises(UnknownAssistantError, match="Unknown assistant"):
            get_target("unknown-assistant")

    def test_error_message_lists_supported_assistants(self):
        """Error message should list supported assistants."""
        with pytest.raises(UnknownAssistantError) as exc_info:
            get_target("bad")
        assert "claude-code" in str(exc_info.value)
        assert "cursor" in str(exc_info.value)
        assert "gemini-cli" in str(exc_info.value)
        assert "openclaw" in str(exc_info.value)
        assert "opencode" in str(exc_info.value)


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestTargetIntegration:
    """Integration-style tests verifying complete workflows."""

    def test_full_skill_installation_workflow_claude(
        self,
        skill_source: Path,
        tmp_path: Path,
    ):
        """Test complete skill installation for Claude Code."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        target = ClaudeCodeTarget()
        skill_dest = target.get_skill_path(str(project_path))
        skill_dest.mkdir(parents=True)

        # Generate skill
        result = target.generate_skill(
            skill_source,
            skill_dest,
            "mymod-test-skill",
            str(project_path),
        )

        assert result is True
        skill_dir = skill_dest / "mymod-test-skill"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "scripts" / "helper.py").exists()

        # Remove skill
        result = target.remove_skill(skill_dest, "mymod-test-skill")
        assert result is True
        assert not skill_dir.exists()

    def test_full_skill_installation_workflow_cursor(
        self,
        skill_source: Path,
        tmp_path: Path,
    ):
        """Test complete skill installation for Cursor (2.4+)."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        target = CursorTarget()
        skill_dest = target.get_skill_path(str(project_path))
        skill_dest.mkdir(parents=True)

        # Generate skill
        result = target.generate_skill(
            skill_source,
            skill_dest,
            "mymod-test-skill",
            str(project_path),
        )

        assert result is True
        skill_dir = skill_dest / "mymod-test-skill"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "scripts" / "helper.py").exists()

        # Remove skill
        result = target.remove_skill(skill_dest, "mymod-test-skill")
        assert result is True
        assert not skill_dir.exists()

    def test_full_skill_installation_workflow_gemini(
        self,
        skill_source: Path,
        tmp_path: Path,
    ):
        """Test complete skill installation for Gemini CLI."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        target = GeminiTarget()
        skill_dest = target.get_skill_path(str(project_path))

        # Generate skills batch
        skills = [
            ("skill1", "First skill", skill_source),
            ("skill2", "Second skill", skill_source),
        ]
        result = target.generate_skills_batch(
            skill_dest,
            "mymod",
            skills,
            str(project_path),
        )

        assert result is True
        assert skill_dest.exists()
        content = skill_dest.read_text()
        assert "#### skill1" in content
        assert "#### skill2" in content

        # Remove module
        result = target.remove_skill(skill_dest, "mymod")
        assert result is True
        content = skill_dest.read_text()
        assert "### mymod" not in content

    def test_command_generation_all_targets(self, command_source: Path, tmp_path: Path):
        """Test command generation for all targets."""
        targets = [
            (ClaudeCodeTarget(), "cmd.md"),
            (CursorTarget(), "cmd.md"),
            (GeminiTarget(), "cmd.toml"),
            (OpenCodeTarget(), "cmd.md"),
        ]

        for target, expected_filename in targets:
            dest = tmp_path / f"dest_{target.name}"
            dest.mkdir()

            result = target.generate_command(command_source, dest, "cmd", "mymod")
            assert result is True, f"Failed for {target.name}"

            expected_file = dest / expected_filename
            assert expected_file.exists(), f"File not created for {target.name}"

    def test_agent_generation_supported_targets(
        self,
        agent_source: Path,
        tmp_path: Path,
    ):
        """Test agent generation for targets that support agents."""
        # Claude Code - should add model: inherit
        claude_dest = tmp_path / "claude"
        claude_dest.mkdir()
        claude_target = ClaudeCodeTarget()
        result = claude_target.generate_agent(
            agent_source,
            claude_dest,
            "agent",
            "mymod",
        )
        assert result is True
        content = (claude_dest / "agent.md").read_text()
        assert "model: inherit" in content

        # Cursor (2.4+) - should add model: inherit (supports subagents)
        cursor_dest = tmp_path / "cursor"
        cursor_dest.mkdir()
        cursor_target = CursorTarget()
        result = cursor_target.generate_agent(
            agent_source,
            cursor_dest,
            "agent",
            "mymod",
        )
        assert result is True
        content = (cursor_dest / "agent.md").read_text()
        assert "model: inherit" in content

        # OpenCode - should add mode: subagent
        opencode_dest = tmp_path / "opencode"
        opencode_dest.mkdir()
        opencode_target = OpenCodeTarget()
        result = opencode_target.generate_agent(
            agent_source,
            opencode_dest,
            "agent",
            "mymod",
        )
        assert result is True
        content = (opencode_dest / "agent.md").read_text()
        assert "mode: subagent" in content


class TestModuleTreeInstall:
    """Tests for module tree copy to target modules directory."""

    @pytest.fixture
    def module_with_packs(self, tmp_path: Path) -> Path:
        """Create a module source with skills, agents, commands, and packs."""
        mod_dir = tmp_path / "source" / "test-module" / "module"
        # Skills
        skill_dir = mod_dir / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\n# Skill")
        # Agents
        agents_dir = mod_dir / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test-agent.md").write_text(
            "---\ndescription: agent\n---\n# Agent",
        )
        # Commands
        cmd_dir = mod_dir / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "test-cmd.md").write_text("# Command")
        # Packs (the arbitrary extra directory)
        packs_dir = mod_dir / "packs"
        packs_dir.mkdir(parents=True)
        (packs_dir / "severity.md").write_text("# Severity levels")
        (packs_dir / "base.md").write_text("# Base conventions")
        return mod_dir.parent  # return test-module/ (the module root)

    def test_install_module_tree_copies_full_content(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """Module tree should copy all content including packs/."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        target = ClaudeCodeTarget()
        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()

        module_dir = _install_module_tree(
            target,
            module,
            module_with_packs,
            project_path,
            scope="project",
        )

        assert module_dir is not None
        assert module_dir.exists()
        assert module_dir == Path(project_path) / ".claude" / "modules" / "test-module"
        # Verify packs/ was copied
        assert (module_dir / "packs" / "severity.md").exists()
        assert (module_dir / "packs" / "base.md").exists()
        # Verify skills/ was also copied (full content tree)
        assert (module_dir / "skills" / "test-skill" / "SKILL.md").exists()
        # Verify agents/ was copied
        assert (module_dir / "agents" / "test-agent.md").exists()

    def test_install_module_tree_overwrites_existing(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """Reinstall should replace old module tree cleanly."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        target = ClaudeCodeTarget()
        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()

        # First install
        module_dir = _install_module_tree(
            target,
            module,
            module_with_packs,
            project_path,
        )
        assert module_dir is not None
        # Add a stale file
        (module_dir / "stale.md").write_text("stale")

        # Second install
        module_dir = _install_module_tree(
            target,
            module,
            module_with_packs,
            project_path,
        )
        assert module_dir is not None
        # Stale file should be gone
        assert not (module_dir / "stale.md").exists()
        # Fresh content should be present
        assert (module_dir / "packs" / "severity.md").exists()

    def test_uninstall_module_tree_removes_directory(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """Uninstall should remove the module tree directory."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        target = ClaudeCodeTarget()
        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()

        module_dir = _install_module_tree(
            target,
            module,
            module_with_packs,
            project_path,
        )
        assert module_dir is not None
        assert module_dir.exists()

        inst = Installation(
            module_name="test-module",
            assistant="claude-code",
            scope="project",
            project_path=project_path,
        )
        result = _uninstall_module_tree(target, inst)
        assert result is True
        assert not module_dir.exists()

    def test_uninstall_module_tree_idempotent(self, tmp_path: Path):
        """Uninstall when no tree exists should return False without error."""
        target = ClaudeCodeTarget()
        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()

        inst = Installation(
            module_name="nonexistent",
            assistant="claude-code",
            scope="project",
            project_path=project_path,
        )
        result = _uninstall_module_tree(target, inst)
        assert result is False

    def test_install_to_assistant_creates_module_tree(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """install_to_assistant should copy module tree and inject
        module_dir into agents."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()
        local_modules = tmp_path / ".lola" / "modules"
        local_modules.mkdir(parents=True)
        registry = InstallationRegistry(tmp_path / "installed.yml")

        install_to_assistant(
            module=module,
            assistant="claude-code",
            scope="project",
            project_path=project_path,
            local_modules=local_modules,
            registry=registry,
            force=True,
        )

        # Module tree should exist
        module_tree = Path(project_path) / ".claude" / "modules" / "test-module"
        assert module_tree.exists(), f"Module tree not found at {module_tree}"
        assert (module_tree / "packs" / "severity.md").exists()

        # Agent file should contain module-dir preamble
        agent_file = Path(project_path) / ".claude" / "agents" / "test-agent.md"
        assert agent_file.exists(), f"Agent file not found at {agent_file}"
        agent_content = agent_file.read_text()
        assert f"Module root: {module_tree}" in agent_content

    def test_uninstall_from_assistant_removes_module_tree(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """uninstall_from_assistant should remove the module tree directory."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()
        local_modules = tmp_path / ".lola" / "modules"
        local_modules.mkdir(parents=True)
        registry = InstallationRegistry(tmp_path / "installed.yml")

        install_to_assistant(
            module=module,
            assistant="claude-code",
            scope="project",
            project_path=project_path,
            local_modules=local_modules,
            registry=registry,
            force=True,
        )

        module_tree = Path(project_path) / ".claude" / "modules" / "test-module"
        assert module_tree.exists()

        installations = registry.find(module.name)
        assert len(installations) > 0
        inst = installations[0]

        uninstall_from_assistant(inst, registry)

        assert not module_tree.exists(), "Module tree should be removed after uninstall"

    def test_install_to_assistant_skill_has_preamble(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """install_to_assistant should inject module_dir preamble into SKILL.md."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()
        local_modules = tmp_path / ".lola" / "modules"
        local_modules.mkdir(parents=True)
        registry = InstallationRegistry(tmp_path / "installed.yml")

        install_to_assistant(
            module=module,
            assistant="claude-code",
            scope="project",
            project_path=project_path,
            local_modules=local_modules,
            registry=registry,
            force=True,
        )

        # Skill SKILL.md should contain module-dir preamble
        skill_file = (
            Path(project_path) / ".claude" / "skills" / "test-skill" / "SKILL.md"
        )
        assert skill_file.exists()
        content = skill_file.read_text()
        module_tree = Path(project_path) / ".claude" / "modules" / "test-module"
        assert f"Module root: {module_tree}" in content

    def test_install_to_assistant_command_has_preamble(
        self,
        module_with_packs: Path,
        tmp_path: Path,
    ):
        """install_to_assistant should inject module_dir preamble into command files."""
        module = Module.from_path(module_with_packs)
        assert module is not None

        project_path = str(tmp_path / "project")
        Path(project_path).mkdir()
        local_modules = tmp_path / ".lola" / "modules"
        local_modules.mkdir(parents=True)
        registry = InstallationRegistry(tmp_path / "installed.yml")

        install_to_assistant(
            module=module,
            assistant="claude-code",
            scope="project",
            project_path=project_path,
            local_modules=local_modules,
            registry=registry,
            force=True,
        )

        # Command file should contain module-dir preamble
        cmd_file = Path(project_path) / ".claude" / "commands" / "test-cmd.md"
        assert cmd_file.exists()
        content = cmd_file.read_text()
        module_tree = Path(project_path) / ".claude" / "modules" / "test-module"
        assert f"Module root: {module_tree}" in content
