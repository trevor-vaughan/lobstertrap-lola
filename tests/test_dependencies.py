"""Tests for component dependency scanning."""

import pytest
from lola.models import Module
from lola.dependencies import (
    scan_component_for_references,
    resolve_dependencies,
    ComponentSelection,
    parse_component_flags,
    validate_component_selection,
    ComponentSelectionError,
)


def test_scan_skill_for_skill_references(module_with_dependencies):
    """scan_component_for_references finds Skill tool invocations."""
    module = Module.from_path(module_with_dependencies)

    refs = scan_component_for_references(module, "skill", "skill1")

    assert ("skill", "skill2") in refs


def test_scan_command_for_skill_references(module_with_dependencies):
    """scan_component_for_references finds skill refs in commands."""
    module = Module.from_path(module_with_dependencies)

    refs = scan_component_for_references(module, "command", "cmd1")

    assert ("skill", "skill1") in refs


def test_scan_nonexistent_component(tmp_path):
    """scan_component_for_references returns empty list for missing component."""
    # Create minimal module with one skill so it's valid
    tmp = tmp_path / "test-module"
    tmp.mkdir()
    skills_dir = tmp / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "skill1"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
description: A test skill
---

# Skill 1

This is a test skill.
""")
    module = Module.from_path(tmp)

    refs = scan_component_for_references(module, "skill", "nonexistent")

    assert refs == []


def test_scan_skill_no_references(module_with_dependencies):
    """Skill with no references returns empty list."""
    module = Module.from_path(module_with_dependencies)

    refs = scan_component_for_references(module, "skill", "skill2")

    assert refs == []


def test_resolve_dependencies_no_deps(sample_module):
    """resolve_dependencies returns input when no dependencies."""
    module = Module.from_path(sample_module)
    selected = ComponentSelection(skills={"skill1"})

    resolved = resolve_dependencies(module, selected)

    assert resolved.skills == {"skill1"}
    assert resolved.commands == set()
    assert resolved.agents == set()


def test_resolve_dependencies_single_level(module_with_dependencies):
    """resolve_dependencies includes direct dependencies."""
    module = Module.from_path(module_with_dependencies)
    selected = ComponentSelection(skills={"skill1"})

    resolved = resolve_dependencies(module, selected)

    # skill1 references skill2
    assert "skill1" in resolved.skills
    assert "skill2" in resolved.skills


def test_resolve_dependencies_transitive(tmp_path):
    """resolve_dependencies handles transitive deps (A→B→C)."""
    # Create module: skill1 → skill2 → skill3
    module_dir = tmp_path / "transitive"
    module_dir.mkdir()
    skills_dir = module_dir / "skills"
    skills_dir.mkdir()

    skill1 = skills_dir / "skill1"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text("""---
description: Skill 1
---

Uses skill2:
<parameter name="skill">skill2</parameter>
""")

    skill2 = skills_dir / "skill2"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text("""---
description: Skill 2
---

Uses skill3:
<parameter name="skill">skill3</parameter>
""")

    skill3 = skills_dir / "skill3"
    skill3.mkdir()
    (skill3 / "SKILL.md").write_text("""---
description: Skill 3
---

Base skill, no deps.
""")

    module = Module.from_path(module_dir)
    selected = ComponentSelection(skills={"skill1"})

    resolved = resolve_dependencies(module, selected)

    # Should include all three
    assert resolved.skills == {"skill1", "skill2", "skill3"}


def test_resolve_dependencies_circular(tmp_path):
    """resolve_dependencies handles circular refs (A→B, B→A)."""
    # Create module with circular dependency
    module_dir = tmp_path / "circular"
    module_dir.mkdir()
    skills_dir = module_dir / "skills"
    skills_dir.mkdir()

    skill1 = skills_dir / "skill1"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text("""---
description: Skill 1
---

Uses skill2:
<parameter name="skill">skill2</parameter>
""")

    skill2 = skills_dir / "skill2"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text("""---
description: Skill 2
---

Uses skill1:
<parameter name="skill">skill1</parameter>
""")

    module = Module.from_path(module_dir)
    selected = ComponentSelection(skills={"skill1"})

    resolved = resolve_dependencies(module, selected)

    # Should include both, not infinite loop
    assert resolved.skills == {"skill1", "skill2"}


def test_resolve_dependencies_cross_type(module_with_dependencies):
    """resolve_dependencies handles command→skill references."""
    module = Module.from_path(module_with_dependencies)
    selected = ComponentSelection(commands={"cmd1"})

    resolved = resolve_dependencies(module, selected)

    # cmd1 references skill1, skill1 references skill2
    assert "cmd1" in resolved.commands
    assert "skill1" in resolved.skills
    assert "skill2" in resolved.skills


def test_parse_component_flags_all_none():
    """parse_component_flags returns None when all flags are None."""
    result = parse_component_flags(None, None, None)
    assert result is None


def test_parse_component_flags_skills_only():
    """parse_component_flags parses comma-separated skills."""
    result = parse_component_flags("skill1,skill2", None, None)

    assert result is not None
    assert result.skills == {"skill1", "skill2"}
    assert result.commands == set()
    assert result.agents == set()


def test_parse_component_flags_all_types():
    """parse_component_flags handles multiple component types."""
    result = parse_component_flags("skill1", "cmd1,cmd2", "agent1")

    assert result is not None
    assert result.skills == {"skill1"}
    assert result.commands == {"cmd1", "cmd2"}
    assert result.agents == {"agent1"}


def test_parse_component_flags_whitespace():
    """parse_component_flags strips whitespace from names."""
    result = parse_component_flags(" skill1 , skill2 ", None, None)

    assert result.skills == {"skill1", "skill2"}


def test_parse_component_flags_empty_string():
    """parse_component_flags treats empty string as no selection."""
    result = parse_component_flags("", "", "")

    assert result is not None
    assert result.is_empty()


def test_validate_component_selection_valid(sample_module):
    """validate_component_selection accepts valid components."""
    module = Module.from_path(sample_module)
    selection = ComponentSelection(skills={"skill1"}, commands={"cmd1"})

    # Should not raise
    validate_component_selection(module, selection)


def test_validate_component_selection_unknown_skill(sample_module):
    """validate_component_selection raises for unknown skills."""
    module = Module.from_path(sample_module)
    selection = ComponentSelection(skills={"nonexistent"})

    with pytest.raises(ComponentSelectionError) as exc:
        validate_component_selection(module, selection)

    assert "Unknown skills: nonexistent" in str(exc.value)
    assert "skill1" in str(exc.value)  # Shows available


def test_validate_component_selection_unknown_multiple(sample_module):
    """validate_component_selection lists all unknown components."""
    module = Module.from_path(sample_module)
    selection = ComponentSelection(
        skills={"bad1", "bad2"},
        commands={"badcmd"},
    )

    with pytest.raises(ComponentSelectionError) as exc:
        validate_component_selection(module, selection)

    msg = str(exc.value)
    assert "bad1" in msg
    assert "bad2" in msg
    assert "badcmd" in msg


def test_validate_component_selection_empty(sample_module):
    """validate_component_selection raises for empty selection."""
    module = Module.from_path(sample_module)
    selection = ComponentSelection()

    with pytest.raises(ComponentSelectionError) as exc:
        validate_component_selection(module, selection)

    assert "at least one component" in str(exc.value)
