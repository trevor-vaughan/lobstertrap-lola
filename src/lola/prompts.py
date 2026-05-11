"""Interactive prompts for lola CLI.

Provides keyboard-navigable selection prompts for:
- Checking whether stdin is a real terminal (is_interactive)
- Selecting one or more AI assistants (multi-select checkbox)
- Selecting a single module from a list (single-select)
- Selecting a marketplace by name from a list (single-select)
- Selecting a marketplace when a module name conflicts across several (single-select)
- Handling command/agent file conflicts during installation

All functions return None / [] when the user cancels, so callers can raise
SystemExit(130) to signal a user-initiated cancellation.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from InquirerPy.validator import EmptyInputValidator

if TYPE_CHECKING:
    from lola.models import Module
    from lola.dependencies import ComponentSelection


def is_interactive() -> bool:
    """Return True when stdin is connected to a real TTY (not piped or CI)."""
    return sys.stdin.isatty()


def select_assistants(available: list[str]) -> list[str]:
    """
    Show a multi-select checkbox for AI assistants.

    If only one assistant is available it is returned immediately without
    prompting.  Returns a (possibly empty) list of selected assistant names;
    an empty list means the user cancelled or deselected everything.
    """
    if len(available) == 1:
        return list(available)

    result = inquirer.checkbox(
        message="Select assistants to install to (Space to toggle, Enter to confirm):",
        choices=available,
    ).execute()
    return result if result is not None else []


def select_module(modules: list[str]) -> str | None:
    """
    Show a single-select list for choosing a module.

    If only one module is available it is returned immediately without
    prompting.  Returns the selected module name, or None if cancelled.
    """
    if len(modules) == 1:
        return modules[0]

    result = inquirer.select(
        message="Select module:",
        choices=modules,
    ).execute()
    return str(result) if result is not None else None


def select_marketplace_name(names: list[str]) -> str | None:
    """
    Show a single-select list for choosing a marketplace by name.

    Always prompts, even when only one marketplace is registered, so the user
    must explicitly confirm before a destructive action proceeds.
    Returns the selected marketplace name, or None if cancelled.
    """
    result = inquirer.select(
        message="Select marketplace:",
        choices=names,
    ).execute()
    return str(result) if result is not None else None


def select_installations(
    installations: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """
    Show a multi-select checkbox for (project_path, assistant, label) tuples.

    Returns the selected installations; an empty list means the user cancelled
    or deselected everything.
    """
    choices = [
        Choice(value=(project, assistant, label), name=label)
        for project, assistant, label in installations
    ]
    result = inquirer.checkbox(
        message="Select installations to uninstall (Space to toggle, Enter to confirm):",
        choices=choices,
    ).execute()
    return result if result is not None else []


def select_marketplace(matches: list[tuple[dict, str]]) -> str | None:
    """
    Show a single-select list for marketplace conflict resolution.

    matches: list of (module_dict, marketplace_name) tuples.
    Returns the chosen marketplace name, or None if cancelled.
    """
    choices = [
        Choice(
            value=marketplace_name,
            name=(
                f"@{marketplace_name}/{module.get('name', '?')} "
                f"v{module.get('version', '?')} — {module.get('description', '')}"
            ),
        )
        for module, marketplace_name in matches
    ]
    result = inquirer.select(
        message="Module found in multiple marketplaces. Select one:",
        choices=choices,
    ).execute()
    return str(result) if result is not None else None


def prompt_conflict(
    kind: str, name: str, module_name: str, sep: str = "-"
) -> tuple[str, str]:
    """Prompt when a component file already exists. Returns (action, new_name)."""
    action = inquirer.select(
        message=f"'{name}' ({kind}) already exists. What would you like to do?",
        choices=[
            Choice("overwrite_all", name="Overwrite All"),
            Choice("overwrite", name="Overwrite"),
            Choice("rename", name=f"Rename {kind}"),
            Choice("skip", name="Skip"),
        ],
    ).execute()
    if action == "rename":
        new_name = inquirer.text(
            message=f"New {kind} name:",
            default=f"{module_name}{sep}{name}",
            validate=EmptyInputValidator(),
        ).execute()
        return "rename", str(new_name)
    return str(action) if action is not None else "skip", ""


def prompt_command_conflict(name: str, module_name: str) -> tuple[str, str]:
    return prompt_conflict("command", name, module_name)


def prompt_agent_conflict(name: str, module_name: str) -> tuple[str, str]:
    return prompt_conflict("agent", name, module_name)


def prompt_skill_conflict(name: str, module_name: str) -> tuple[str, str]:
    return prompt_conflict("skill", name, module_name, sep="_")


def select_components(
    module: Module, current: ComponentSelection | None = None
) -> ComponentSelection | None:
    """Show interactive picker for selecting module components."""
    from lola.dependencies import ComponentSelection

    is_update = current is not None
    prefixes = {"skill": "", "command": "/", "agent": "@"}
    current_sets: dict[str, set[str]] = {
        "skill": current.skills if current else set(),
        "command": current.commands if current else set(),
        "agent": current.agents if current else set(),
    }

    groups: list[tuple[str, str, list[str]]] = [
        ("Skills", "skill", sorted(module.skills)),
        ("Commands", "command", sorted(module.commands)),
        ("Agents", "agent", sorted(module.agents)),
    ]

    choices: list[Separator | Choice] = []
    for header, comp_type, names in groups:
        if not names:
            continue
        choices.append(Separator(header))
        for name in names:
            is_current = name in current_sets[comp_type]
            enabled = is_current if is_update else True
            suffix = ""
            if is_update:
                suffix = " (installed)" if is_current else " (new)"
            choices.append(
                Choice(
                    value={"name": name, "type": comp_type},
                    name=f"  {prefixes[comp_type]}{name}{suffix}",
                    enabled=enabled,
                )
            )
        choices.append(Separator(""))

    if module.mcps or module.has_instructions:
        choices.append(Separator("Always Included"))
        if module.has_instructions:
            choices.append(Choice(value=None, name="  instructions (AGENTS.md)", enabled=False))
        for mcp in sorted(module.mcps):
            choices.append(Choice(value=None, name=f"  mcp:{mcp}", enabled=False))

    message = "Update component selection:" if is_update else "Select components to install:"
    result = inquirer.checkbox(
        message=message,
        choices=choices,
        instruction="(Space: toggle | Ctrl-A: select all | Ctrl-R: invert | Enter: confirm)",
    ).execute()

    if result is None:
        return None

    selection = ComponentSelection()
    for item in result:
        if item is None:
            continue
        comp_type = item["type"]
        comp_name = item["name"]
        if comp_type == "skill":
            selection.skills.add(comp_name)
        elif comp_type == "command":
            selection.commands.add(comp_name)
        elif comp_type == "agent":
            selection.agents.add(comp_name)

    return selection
