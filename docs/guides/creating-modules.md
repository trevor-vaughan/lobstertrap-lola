# Creating Modules

Lola modules can be a single [Agent Skill](https://agentskills.io/specification) or a full [AI Context Module](../concepts/skills-and-modules.md). An Agent Skill is a standalone `SKILL.md` with optional supporting files. An AI Context Module is a superset - it wraps one or more skills alongside `AGENTS.md`, `commands/`, and `mcps.json` inside a `module/` directory.

## Initialize an AI Context Module

```bash
lola mod init my-module
```

This creates the AI Context Module structure:

```
my-module/
  module/
    AGENTS.md           # AI main spec
    skills/
      example-skill/
        SKILL.md        # Skill following agentskills.io
    commands/
      example-command.md
    agents/
      example-agent.md
    mcps.json           # MCP settings
```

You can add any additional directories alongside the standard ones (e.g., `packs/`, `templates/`, `reference/`). During installation, the entire module content tree is copied to the target assistant's `modules/<name>/` directory, preserving all internal relative paths.

!!! note
    `lola mod init` currently creates only the AI Context Module pattern. Standalone Agent Skill initialization (`lola skill init`) is planned for a future release.

## Edit the skill

Edit your skill's `SKILL.md` following the [AgentSkills.io](https://agentskills.io/specification) standard:

```markdown
---
name: my-skill
description: When to use this skill
---

# My Skill

Instructions for the AI assistant...
```

## Add supporting files

Each skill can have its own `scripts/`, `reference/`, and `assets/` directories:

```
my-skill/
  SKILL.md
  scripts/           # Executable scripts
  reference/         # Documentation
  assets/            # Other supporting files
```

Reference them with relative paths in your `SKILL.md`:

```markdown
Use the helper script: `./scripts/helper.sh`
```

## Add an AGENTS.md

The `AGENTS.md` provides module-level context that applies across all skills in the module. This is what elevates a collection of skills into an AI Context Module.

## Add slash commands

Slash commands are custom commands that can be invoked with `/command-name` in AI assistants. Claude Code, Cursor, and Gemini CLI all support them. Create markdown files in `commands/`:

```markdown
---
description: Review a pull request
argument-hint: <pr-number>
---

Review PR #$ARGUMENTS and provide feedback.
```

Use `$ARGUMENTS` for all args or `$1`, `$2` for positional. Lola automatically converts commands to each assistant's native format (markdown for Claude Code and Cursor, TOML for Gemini CLI).

## Add shared resources for agents

Modules often include shared resources that agents need at runtime -- convention packs, reference documents, templates, or protocol files. Place these in any directory at the module content root:

```text
my-module/
  module/
    agents/
      reviewer.md
    packs/                # Shared resources for agents
      conventions.md
      severity.md
    skills/
      my-skill/
        SKILL.md
```

During installation, the full content tree is copied to the target's modules directory (e.g., `.claude/modules/my-module/`). Generated skill, command, and agent files receive a plain-text module directory preamble between the frontmatter and body, pointing to the installed module tree (Gemini CLI commands use TOML format and do not receive the preamble). Agents can read this path to locate module-relative resources:

```markdown
---
name: reviewer
model: inherit
---
Module root: .claude/modules/my-module
This is the installed root of the module. Resolve all relative file references in this document against the path above.
Example: packs/foo.md -> .claude/modules/my-module/packs/foo.md

Read `conventions.md` from the packs directory.
```

The module tree is installed per-target at:

| Target      | Project Scope               | User Scope                              |
|-------------|-----------------------------|-----------------------------------------|
| Claude Code | `.claude/modules/<name>/`   | `~/.claude/modules/<name>/`             |
| Cursor      | `.cursor/modules/<name>/`   | `~/.cursor/modules/<name>/`             |
| Gemini CLI  | `.gemini/modules/<name>/`   | `~/.gemini/modules/<name>/`             |
| OpenClaw    | `modules/<name>/`           | `~/.openclaw/workspace/modules/<name>/` |
| OpenCode    | `.opencode/modules/<name>/` | `~/.config/opencode/modules/<name>/`    |

## Register and install

```bash
lola mod add ./my-module
lola install my-module
```

See [Skill Format](skill-format.md) for details on the SKILL.md specification.
