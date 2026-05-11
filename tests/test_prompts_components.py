"""Tests for component selection prompts."""

from unittest.mock import MagicMock, patch
from lola.prompts import select_components
from lola.models import Module
from lola.dependencies import ComponentSelection


def test_select_components_all_types(sample_module_with_instructions):
    """select_components shows all component types."""
    module = Module.from_path(sample_module_with_instructions)

    # Mock InquirerPy to return selection
    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = [
            {"name": "skill1", "type": "skill"},
            {"name": "cmd1", "type": "command"},
        ]
        mock_checkbox.return_value = mock_prompt

        result = select_components(module)

        assert result is not None
        assert "skill1" in result.skills
        assert "cmd1" in result.commands
        assert "agent1" not in result.agents  # Not selected


def test_select_components_user_cancelled(sample_module):
    """select_components returns None when user cancels."""
    module = Module.from_path(sample_module)

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = None  # User cancelled
        mock_checkbox.return_value = mock_prompt

        result = select_components(module)

        assert result is None


def test_select_components_shows_instructions(sample_module_with_instructions):
    """select_components displays instructions as always included."""
    module = Module.from_path(sample_module_with_instructions)

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = []
        mock_checkbox.return_value = mock_prompt

        select_components(module)

        # Check that choices were created
        call_args = mock_checkbox.call_args
        assert call_args is not None


def test_select_components_prefixes(sample_module_with_instructions):
    """select_components uses / prefix for commands and @ for agents."""
    module = Module.from_path(sample_module_with_instructions)

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = []
        mock_checkbox.return_value = mock_prompt

        select_components(module)

        # Check that choices include prefixed names
        call_args = mock_checkbox.call_args
        choices = call_args[1]["choices"]

        # Find the names in choices
        choice_names = [c.name for c in choices if hasattr(c, "name")]

        # Should have /cmd1 and @agent1 in names
        assert any("/cmd1" in str(name) for name in choice_names), \
            f"Expected /cmd1 prefix in choices, got: {choice_names}"
        assert any("@agent1" in str(name) for name in choice_names), \
            f"Expected @agent1 prefix in choices, got: {choice_names}"


def test_select_components_all_pre_checked(sample_module_with_instructions):
    """select_components has all selectable components pre-checked."""
    module = Module.from_path(sample_module_with_instructions)

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = []
        mock_checkbox.return_value = mock_prompt

        select_components(module)

        # Check that all selectable choices are enabled
        call_args = mock_checkbox.call_args
        choices = call_args[1]["choices"]

        # Filter to only Choice objects (exclude Separators)
        from InquirerPy.base.control import Choice
        choice_objects = [c for c in choices if isinstance(c, Choice)]

        # All selectable items (skills, commands, agents) should be enabled
        selectable_choices = [c for c in choice_objects if c.value is not None]
        assert all(c.enabled for c in selectable_choices), \
            "Not all selectable components are enabled"


def test_select_components_always_included_disabled(sample_module_with_instructions):
    """select_components shows instructions and MCPs as always included (disabled)."""
    module = Module.from_path(sample_module_with_instructions)

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = []
        mock_checkbox.return_value = mock_prompt

        select_components(module)

        call_args = mock_checkbox.call_args
        choices = call_args[1]["choices"]

        # Find choices with instructions
        from InquirerPy.base.control import Choice
        choice_objects = [c for c in choices if isinstance(c, Choice)]

        # Always included items should be disabled
        always_included = [c for c in choice_objects if c.value is None]
        assert len(always_included) > 0, "Should have always-included items"
        assert all(not c.enabled for c in always_included), \
            "Always-included items should be disabled"


def test_select_components_empty_module(tmp_path):
    """select_components handles module with no components gracefully."""
    # Create minimal module with only instructions
    module_dir = tmp_path / "minimal-module"
    module_dir.mkdir()
    (module_dir / "AGENTS.md").write_text("# Module\n\nJust instructions.")

    module = Module.from_path(module_dir)
    assert module is not None

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = []
        mock_checkbox.return_value = mock_prompt

        result = select_components(module)

        # Should work without crashing
        assert result is not None
        assert result.is_empty()


def test_select_components_groups_by_type(integration_module):
    """select_components groups items with headers."""
    module = Module.from_path(integration_module)

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = []
        mock_checkbox.return_value = mock_prompt

        select_components(module)

        call_args = mock_checkbox.call_args
        choices = call_args[1]["choices"]

        # Check for separator objects
        from InquirerPy.separator import Separator
        separators = [c for c in choices if isinstance(c, Separator)]

        # Should have skill and command separators at minimum
        assert len(separators) > 0, f"Should have separators, got {len(separators)}"


def test_select_components_for_update_prechecks_current(sample_module):
    """select_components with current= pre-checks currently installed components."""
    module = Module.from_path(sample_module)
    current = ComponentSelection(skills={"skill1"})

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = [
            {"name": "skill1", "type": "skill"},
        ]
        mock_checkbox.return_value = mock_prompt

        _ = select_components(module, current=current)

        # Verify choices had skill1 enabled
        call_args = mock_checkbox.call_args
        assert call_args is not None
        choices = call_args.kwargs.get("choices")
        assert choices is not None

        # Find skill1 choice and verify it's enabled
        from InquirerPy.base.control import Choice
        skill1_choice = next(
            (c for c in choices if isinstance(c, Choice) and
             c.value and c.value.get("name") == "skill1"),
            None
        )
        assert skill1_choice is not None
        assert skill1_choice.enabled is True


def test_select_components_for_update_shows_new_unchecked(tmp_path):
    """select_components with current= shows new components unchecked."""
    # Create module with 2 skills
    module_dir = tmp_path / "update-test"
    module_dir.mkdir()
    skills_dir = module_dir / "skills"
    skills_dir.mkdir()

    for name in ["skill1", "skill2"]:
        skill = skills_dir / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"---\ndescription: {name}\n---\n\nSkill {name}")

    module = Module.from_path(module_dir)

    # Current has only skill1
    current = ComponentSelection(skills={"skill1"})

    with patch("lola.prompts.inquirer.checkbox") as mock_checkbox:
        mock_prompt = MagicMock()
        mock_prompt.execute.return_value = [
            {"name": "skill1", "type": "skill"},
            {"name": "skill2", "type": "skill"},
        ]
        mock_checkbox.return_value = mock_prompt

        _ = select_components(module, current=current)

        # Check that skill2 was shown but not enabled
        choices = mock_checkbox.call_args.kwargs.get("choices")
        from InquirerPy.base.control import Choice
        skill2_choice = next(
            (c for c in choices if isinstance(c, Choice) and
             c.value and c.value.get("name") == "skill2"),
            None
        )
        assert skill2_choice is not None
        assert skill2_choice.enabled is False  # New component, not pre-checked
