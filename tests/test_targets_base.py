"""Tests for AssistantTarget ABC scope parameter support."""

from pathlib import Path
from typing import Any

from lola.targets.base import (
    AssistantTarget,
    _build_module_dir_preamble,
    _inject_preamble,
)


class MockTarget(AssistantTarget):
    """Mock target for testing ABC."""

    name = "mock"
    supports_agents = True
    uses_managed_section = False

    def get_skill_path(self, project_path: str, scope: str = "project") -> Path:
        if scope == "user":
            return Path.home() / ".mock" / "skills"
        return Path(project_path) / ".mock" / "skills"

    def get_command_path(self, project_path: str, scope: str = "project") -> Path:
        if scope == "user":
            return Path.home() / ".mock" / "commands"
        return Path(project_path) / ".mock" / "commands"

    def get_agent_path(self, project_path: str, scope: str = "project") -> Path:
        if scope == "user":
            return Path.home() / ".mock" / "agents"
        return Path(project_path) / ".mock" / "agents"

    def get_instructions_path(self, project_path: str, scope: str = "project") -> Path:
        if scope == "user":
            return Path.home() / "MOCK.md"
        return Path(project_path) / "MOCK.md"

    def get_mcp_path(self, project_path: str, scope: str = "project") -> Path:
        if scope == "user":
            return Path.home() / ".mock.json"
        return Path(project_path) / ".mock.json"

    # Minimal stubs — params match ABC names; noqa suppresses ARG002
    def generate_skill(
        self,
        source_path: Path,  # noqa: ARG002
        dest_path: Path,  # noqa: ARG002
        skill_name: str,  # noqa: ARG002
        project_path: str | None = None,  # noqa: ARG002
        *,
        module_dir: Path | None = None,  # noqa: ARG002
    ) -> bool:
        return True

    def generate_command(
        self,
        source_path: Path,  # noqa: ARG002
        dest_dir: Path,  # noqa: ARG002
        cmd_name: str,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
        *,
        module_dir: Path | None = None,  # noqa: ARG002
    ) -> bool:
        return True

    def generate_agent(
        self,
        source_path: Path,  # noqa: ARG002
        dest_dir: Path,  # noqa: ARG002
        agent_name: str,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
        *,
        module_dir: Path | None = None,  # noqa: ARG002
    ) -> bool:
        return True

    def generate_instructions(
        self,
        source: Path | str,  # noqa: ARG002
        dest_path: Path,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
    ) -> bool:
        return True

    def remove_skill(self, dest_path: Path, skill_name: str) -> bool:  # noqa: ARG002
        return True

    def remove_instructions(self, dest_path: Path, module_name: str) -> bool:  # noqa: ARG002
        return True

    def generate_skills_batch(
        self,
        dest_file: Path,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
        skills: list[tuple[str, str, Path]],  # noqa: ARG002
        project_path: str | None,  # noqa: ARG002
        *,
        module_dir: Path | None = None,  # noqa: ARG002
    ) -> bool:
        return True

    def get_command_filename(self, module_name: str, cmd_name: str) -> str:
        return f"{module_name}.{cmd_name}.md"

    def get_agent_filename(self, module_name: str, agent_name: str) -> str:
        return f"{module_name}.{agent_name}.md"

    def generate_mcps(
        self,
        mcps: dict[str, dict[str, Any]],  # noqa: ARG002
        dest_path: Path,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
    ) -> bool:
        return True

    def remove_mcps(
        self,
        dest_path: Path,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
        mcp_names: list[str] | None = None,  # noqa: ARG002
    ) -> bool:
        return True

    def remove_command(
        self,
        dest_dir: Path,  # noqa: ARG002
        cmd_name: str,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
    ) -> bool:
        return True

    def get_module_path(self, project_path: str, scope: str = "project") -> Path:
        if scope == "user":
            return Path.home() / ".mock" / "modules"
        return Path(project_path) / ".mock" / "modules"

    def remove_agent(
        self,
        dest_dir: Path,  # noqa: ARG002
        agent_name: str,  # noqa: ARG002
        module_name: str,  # noqa: ARG002
    ) -> bool:
        return True


def test_get_skill_path_project_scope():
    target = MockTarget()
    path = target.get_skill_path("/home/user/project", "project")
    assert path == Path("/home/user/project/.mock/skills")


def test_get_skill_path_user_scope():
    target = MockTarget()
    path = target.get_skill_path("/home/user/project", "user")
    assert path == Path.home() / ".mock" / "skills"


def test_get_command_path_project_scope():
    target = MockTarget()
    path = target.get_command_path("/home/user/project", "project")
    assert path == Path("/home/user/project/.mock/commands")


def test_get_command_path_user_scope():
    target = MockTarget()
    path = target.get_command_path("/home/user/project", "user")
    assert path == Path.home() / ".mock" / "commands"


class TestModuleDirPreamble:
    """Tests for module-dir preamble helper functions."""

    def test_build_preamble_produces_plain_text_block(self):
        """Preamble should use plain text without HTML comment delimiters."""
        result = _build_module_dir_preamble(Path("/project/.claude/modules/mymod"))
        assert "<!-- lola:module-dir:start -->" not in result
        assert "<!-- lola:module-dir:end -->" not in result
        assert "Module root: /project/.claude/modules/mymod" in result
        expected = (
            "This is the installed root of the module."
            " Resolve all relative file references in"
            " this document against the path above."
        )
        assert expected in result
        assert (
            "Example: packs/foo.md -> /project/.claude/modules/mymod/packs/foo.md"
            in result
        )

    def test_build_preamble_trailing_newline(self):
        """Preamble block should end with a trailing newline."""
        result = _build_module_dir_preamble(Path("/some/path"))
        assert result.endswith("\n")

    def test_build_preamble_starts_with_newline(self):
        """Preamble should start with newline for separation
        from frontmatter closing ---."""
        result = _build_module_dir_preamble(Path("/some/path"))
        assert result.startswith("\n")

    def test_inject_preamble_with_frontmatter(self):
        """Preamble should be injected between frontmatter and body."""
        content = "---\ndescription: test\n---\n\n# Body"
        result = _inject_preamble(content, Path("/mod/dir"))
        assert result.startswith("---\n")
        assert "Module root: /mod/dir" in result
        assert "# Body" in result
        preamble_pos = result.index("Module root: /mod/dir")
        body_pos = result.index("# Body")
        assert preamble_pos < body_pos

    def test_inject_preamble_without_frontmatter(self):
        """Content without frontmatter should get preamble prepended."""
        content = "# Just a heading\n\nSome content."
        result = _inject_preamble(content, Path("/mod/dir"))
        assert result.startswith("Module root: /mod/dir")
        assert "# Just a heading" in result
        preamble_end = result.index("Example: packs/foo.md")
        body_pos = result.index("# Just a heading")
        assert preamble_end < body_pos

    def test_inject_preamble_none_returns_unchanged(self):
        """When module_dir is None, content should be returned unchanged."""
        content = "---\ndescription: test\n---\n\n# Body"
        result = _inject_preamble(content, None)
        assert result == content

    def test_inject_preamble_malformed_frontmatter_no_closing(self):
        """Malformed frontmatter (no closing ---) should fall back to prepend."""
        content = "---\ndescription: test\nname: broken\n\n# Body"
        result = _inject_preamble(content, Path("/mod/dir"))
        assert result.startswith("Module root: /mod/dir")
        assert "Module root: /mod/dir" in result
        assert content in result

    def test_inject_preamble_preserves_frontmatter_fields(self):
        """Frontmatter fields should be preserved after preamble injection."""
        content = "---\ndescription: my skill\nname: cool-skill\n---\n\n# Body"
        result = _inject_preamble(content, Path("/mod/dir"))
        assert "description:" in result
        assert "# Body" in result
