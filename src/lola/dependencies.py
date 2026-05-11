"""Dependency resolution and component selection for lola modules."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lola.models import Module


class ComponentSelectionError(Exception):
    pass


@dataclass
class ComponentSelection:
    """Selected components for installation."""

    skills: set[str] = field(default_factory=set)
    commands: set[str] = field(default_factory=set)
    agents: set[str] = field(default_factory=set)

    @classmethod
    def all_from_module(cls, module: Module) -> ComponentSelection:
        """Create selection with all components from module."""
        return cls(
            skills=set(module.skills),
            commands=set(module.commands),
            agents=set(module.agents),
        )

    def is_empty(self) -> bool:
        """Check if no components selected."""
        return not (self.skills or self.commands or self.agents)

    def to_lists(self) -> tuple[list[str], list[str], list[str]]:
        """Return sorted lists of (skills, commands, agents)."""
        return (
            sorted(self.skills),
            sorted(self.commands),
            sorted(self.agents),
        )


def scan_component_for_references(
    module: Module, comp_type: str, comp_name: str
) -> list[tuple[str, str]]:
    """Scan a component file for references to other components in the module."""
    if comp_type == "skill":
        paths = module.get_skill_paths()
        comp_path = next((p for p in paths if p.name == comp_name), None)
        if not comp_path:
            return []
        file_path = comp_path / "SKILL.md"
    elif comp_type == "command":
        file_path = module.content_path / "commands" / f"{comp_name}.md"
    elif comp_type == "agent":
        file_path = module.content_path / "agents" / f"{comp_name}.md"
    else:
        return []

    if not file_path.exists():
        return []

    content = file_path.read_text()
    references = []

    # Pattern 1: Skill tool invocations
    # <invoke name="Skill">...<parameter name="skill">skill-name</parameter>
    skill_pattern = r'<parameter name="skill">([^<]+)</parameter>'
    for match in re.finditer(skill_pattern, content):
        skill_name = match.group(1).strip()
        if skill_name in module.skills:
            references.append(("skill", skill_name))

    # Pattern 2: Skill directory references in content
    # skills/skill-name/ or /skills/skill-name (with boundaries)
    for skill in module.skills:
        skill_dir_pattern = rf'skills/{re.escape(skill)}(?:/|\s|$|[)\]])'
        if re.search(skill_dir_pattern, content):
            references.append(("skill", skill))

    # Pattern 3: Command references
    # /<command-name> or slash command mentions
    for cmd in module.commands:
        # Avoid false positives: must be at word boundary
        cmd_pattern = rf'/{cmd}\b'
        if re.search(cmd_pattern, content):
            references.append(("command", cmd))

    # Pattern 4: Agent references
    # @agent-name or agent mentions
    for agent in module.agents:
        if f"@{agent}" in content or f"agent:{agent}" in content:
            references.append(("agent", agent))

    # Deduplicate
    return list(set(references))


def resolve_dependencies(
    module: Module, selected: ComponentSelection
) -> ComponentSelection:
    """Resolve transitive dependencies for selected components."""
    resolved = ComponentSelection(
        skills=set(selected.skills),
        commands=set(selected.commands),
        agents=set(selected.agents),
    )

    processed: set[tuple[str, str]] = set()
    queue: deque[tuple[str, str]] = deque()

    for skill in selected.skills:
        queue.append(("skill", skill))
    for cmd in selected.commands:
        queue.append(("command", cmd))
    for agent in selected.agents:
        queue.append(("agent", agent))

    while queue:
        comp_type, comp_name = queue.popleft()
        key = (comp_type, comp_name)

        if key in processed:
            continue
        processed.add(key)

        # Scan component for references
        refs = scan_component_for_references(module, comp_type, comp_name)

        # Add new references to resolved set and queue
        for ref_type, ref_name in refs:
            if ref_type == "skill" and ref_name not in resolved.skills:
                if ref_name in module.skills:
                    resolved.skills.add(ref_name)
                    queue.append(("skill", ref_name))
            elif ref_type == "command" and ref_name not in resolved.commands:
                if ref_name in module.commands:
                    resolved.commands.add(ref_name)
                    queue.append(("command", ref_name))
            elif ref_type == "agent" and ref_name not in resolved.agents:
                if ref_name in module.agents:
                    resolved.agents.add(ref_name)
                    queue.append(("agent", ref_name))

    return resolved


def parse_component_flags(
    skills: str | None, commands: str | None, agents: str | None
) -> ComponentSelection | None:
    """Parse --skills, --commands, --agents CLI flags into a ComponentSelection."""
    if skills is None and commands is None and agents is None:
        return None

    def parse_list(s: str | None) -> set[str]:
        if not s:
            return set()
        return {name.strip() for name in s.split(",") if name.strip()}

    selection = ComponentSelection(
        skills=parse_list(skills),
        commands=parse_list(commands),
        agents=parse_list(agents),
    )

    return selection


def validate_component_selection(module: Module, selection: ComponentSelection) -> None:
    """Raise ComponentSelectionError if any selected components don't exist in the module."""
    if selection.is_empty():
        raise ComponentSelectionError(
            "Must select at least one component (skill, command, or agent)"
        )

    checks = [
        ("skills", selection.skills, module.skills),
        ("commands", selection.commands, module.commands),
        ("agents", selection.agents, module.agents),
    ]
    errors = []
    for label, selected, available in checks:
        unknown = selected - set(available)
        if unknown:
            avail_str = ", ".join(available) if available else "(none)"
            errors.append(
                f"Unknown {label}: {', '.join(sorted(unknown))}\n"
                f"Available {label}: {avail_str}"
            )

    if errors:
        raise ComponentSelectionError("\n\n".join(errors))
