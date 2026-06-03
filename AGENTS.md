# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## What is Lola

Lola is an AI Skills Package Manager that lets you write AI context/skills once and install them to multiple AI assistants (Claude Code, Cursor, Gemini CLI, OpenCode, etc.). Skills are portable modules with a SKILL.md file that get converted to each assistant's native format.

## Development Commands

Remember to source the virtual environment before running commands:
```bash
source .venv/bin/activate
```

```bash
# Install in development mode with dev dependencies
uv sync --group dev

# Run tests
pytest                        # All tests
pytest tests/test_cli_mod.py  # Single test file
pytest -k test_add            # Tests matching pattern
pytest --cov=src/lola         # With coverage

# Run linting and type checking
ruff check src tests
basedpyright src

# Run the CLI
lola --help
lola mod ls
lola install <module> -a claude-code
```

## Architecture

### Core Data Flow

1. **Module Registration**: `lola mod add <source>` fetches modules (from git, zip, tar, or folder) to `~/.lola/modules/`
2. **Installation**: `lola install <module>` copies modules to project's `.lola/modules/` and generates assistant-specific files
3. **Updates**: `lola update` regenerates assistant files from source modules
4. **Marketplace Registration**: `lola market add <name> <url>` fetches marketplace catalogs to `~/.lola/market/` (reference) and `~/.lola/market/cache/` (full catalog)
5. **Module Discovery**: `lola mod search <query>` searches across enabled marketplace caches; `lola install <module>` auto-adds from marketplace if not in registry

### Installation Scopes

Lola supports two installation scopes:

- **Project scope** (default): Installs to project directories (`.claude/`, `.cursor/`, etc.)
- **User scope**: Installs to user home directories (`~/.claude/`, `~/.cursor/`, etc.)

#### Examples

Install to current project (default):
```bash
lola install my-module
```

Install globally for your user:
```bash
lola install my-module --scope user
```

Install to specific project:
```bash
lola install my-module /path/to/project
```

List all installations:
```bash
lola list
```

Uninstall from user scope only:
```bash
lola uninstall my-module --scope user
```

### Key Source Files

- `src/lola/main.py` - CLI entry point, registers all commands
- `src/lola/cli/mod.py` - Module management: add, rm, ls, info, init, update, search
- `src/lola/cli/install.py` - Install/uninstall/update commands (with marketplace integration)
- `src/lola/cli/market.py` - Marketplace management: add, ls, update, set (enable/disable), rm
- `src/lola/models.py` - Data models: Module, Skill, Command, Agent, Installation, InstallationRegistry, Marketplace
- `src/lola/market/manager.py` - MarketplaceRegistry class for marketplace operations
- `src/lola/market/search.py` - Search functionality across marketplace caches
- `src/lola/config.py` - Global paths (LOLA_HOME, MODULES_DIR, INSTALLED_FILE, MARKET_DIR, CACHE_DIR)
- `src/lola/targets/` - Assistant target package:
  - `__init__.py` - TARGETS registry, `get_target()` lookup
  - `base.py` - `AssistantTarget` ABC, `BaseAssistantTarget` defaults, shared helpers (`_generate_agent_with_frontmatter`, `_generate_passthrough_command`, `_get_content_path`)
  - `install.py` - Install/uninstall orchestration (`install_to_assistant`, `_install_module_tree`, `_uninstall_module_tree`, `_install_skills/commands/agents/mcps/instructions`)
  - `claude_code.py`, `cursor.py`, `gemini.py`, `openclaw.py`, `opencode.py` - Per-target implementations
- `src/lola/parsers.py` - Source fetching (SourceHandler classes) and skill/command parsing
- `src/lola/frontmatter.py` - YAML frontmatter parsing

### Module Structure

Modules use auto-discovery. Skills, commands, and agents are discovered from directory structure:

```
my-module/
  skills/              # Skills directory (required for skills)
    skill-name/
      SKILL.md         # Required: skill definition with frontmatter
      scripts/         # Optional: supporting files
  commands/            # Slash commands (*.md files)
    review.md          # A command
    review/            # Optional: co-named sidecar dir of supporting files
      phase.md         #   for a multi-file command (copied with review.md)
  agents/              # Subagents (*.md files)
```

A command can be a single `*.md` file or a *multi-file command*: an entry file
`commands/<cmd>.md` plus a co-named sidecar directory `commands/<cmd>/` holding
supporting files the entry reads at runtime (e.g. via a path relative to its own
location). The sidecar directory is copied verbatim alongside the entry file for
file-based targets (Claude Code, Cursor, OpenCode) and removed on uninstall. The
sidecar's files are not registered as separate commands.

### Marketplace Structure

Marketplaces are YAML files with module catalogs:

```yaml
name: Marketplace Name
description: Description of the marketplace
version: 1.0.0
modules:
  - name: module-name
    description: Module description
    version: 1.0.0
    repository: https://github.com/user/repo.git
    tags: [tag1, tag2]
```

**Storage locations:**
- **Reference files**: `~/.lola/market/<name>.yml` - Contains source URL and enabled status
- **Cache files**: `~/.lola/market/cache/<name>.yml` - Full marketplace catalog

**Key operations:**
- `MarketplaceRegistry.add(name, url)` - Downloads and validates marketplace, saves reference and cache
- `MarketplaceRegistry.search_module_all(name)` - Finds module across all enabled marketplaces
- `MarketplaceRegistry.select_marketplace(name, matches)` - Prompts user when module exists in multiple marketplaces
- `MarketplaceRegistry.update(name)` - Re-fetches marketplace from source URL
- Cache recovery: Automatically re-downloads from source URL if cache is missing

### Target Assistants

Defined in `targets.py` TARGETS dict. Each assistant has different output formats:

| Assistant | Skills | Commands | Agents | Modules |
|-----------|--------|----------|--------|---------|
| claude-code | `.claude/skills/<skill>/SKILL.md` | `.claude/commands/<cmd>.md` | `.claude/agents/<agent>.md` | `.claude/modules/<name>/` |
| cursor | `.cursor/skills/<skill>/SKILL.md` | `.cursor/commands/<cmd>.md` | `.cursor/agents/<agent>.md` | `.cursor/modules/<name>/` |
| gemini-cli | `GEMINI.md` (managed section) | `.gemini/commands/<cmd>.toml` | N/A | `.gemini/modules/<name>/` |
| openclaw | `~/.openclaw/workspace/skills/<skill>/SKILL.md` | N/A | N/A | `modules/<name>/` |
| opencode | `AGENTS.md` (managed section) | `.opencode/commands/<cmd>.md` | `.opencode/agents/<agent>.md` | `.opencode/modules/<name>/` |

Agent frontmatter is modified during generation:
- Claude Code: `name` (agent name) and `model: inherit` are added
- Cursor: `name` (agent name) and `model: inherit` are added
- OpenCode: `mode: subagent` is added

**Module tree:** During installation, the entire module content tree is copied to
the target's `modules/<name>/` directory. This preserves internal relative paths
between module files (e.g. a `packs/` directory that agents reference at
runtime). Skills, commands, and agents all receive a module-dir preamble block
between frontmatter and body, pointing to the installed module tree. Assets can
use this path to locate module-relative resources like convention packs,
reference files, or other shared content that falls outside the standard
skills/commands/agents directories.

The preamble is plain text inlined between frontmatter and body:

```markdown
Module root: .claude/modules/review-council
This is the installed root of the module. Resolve all relative file references in this document against the path above.
Example: packs/foo.md -> .claude/modules/review-council/packs/foo.md
```

**Exceptions:** Gemini CLI commands use TOML format and do not receive the
preamble. The Gemini `ManagedSectionTarget` emits
`**Module root:** \`<path>\`` with an example resolution line in the skills
batch section instead.

Example generated agent file with preamble:
```markdown
---
name: divisor-guard-code
model: inherit
---
Module root: .claude/modules/review-council
This is the installed root of the module. Resolve all relative file references in this document against the path above.
Example: packs/foo.md -> .claude/modules/review-council/packs/foo.md

# Guard - Code Review
...
```

User-scope module tree paths:

| Target | User Scope Module Dir |
|--------|----------------------|
| claude-code | `~/.claude/modules/<name>/` |
| cursor | `~/.cursor/modules/<name>/` |
| gemini-cli | `~/.gemini/modules/<name>/` |
| openclaw | `~/.openclaw/workspace/modules/<name>/` |
| opencode | `~/.config/opencode/modules/<name>/` |

**Backwards compatibility:** Uninstall also checks for old prefixed filenames
(`<module>.<cmd>.md`, `<module>.<agent>.md`) so installs made before prefix
removal are cleaned up correctly.

### Source Handlers

`parsers.py` uses strategy pattern for fetching modules:
- `GitSourceHandler` - git clone with depth 1
- `ZipSourceHandler` / `ZipUrlSourceHandler` - local/remote zip files
- `TarSourceHandler` / `TarUrlSourceHandler` - local/remote tar archives
- `FolderSourceHandler` - local directory copy

### Testing Patterns

Tests use Click's `CliRunner` for CLI testing. Key fixtures in `tests/conftest.py`:
- `mock_lola_home` - patches LOLA_HOME, MODULES_DIR, INSTALLED_FILE to temp directory
- `sample_module` - creates test module with skill, command, and agent
- `registered_module` - sample_module copied into mock_lola_home
- `mock_assistant_paths` - creates mock assistant output directories
- `marketplace_with_modules` - creates marketplace with test modules
- `marketplace_disabled` - creates disabled marketplace for testing

**Unused parameters in ABC overrides (ruff ARG002 vs ty):**
When test stubs or `BaseAssistantTarget` override an ABC method without using
every parameter, ruff raises `ARG002` (unused method argument). Do **not**
prefix the parameter with `_` — `ty` enforces the Liskov Substitution Principle
and rejects parameter name changes in overrides. Instead, annotate each unused
parameter with an inline `# noqa: ARG002` comment. This matches the existing
pattern in `src/lola/targets/base.py` (e.g. `BaseAssistantTarget` stubs).

**Marketplace testing patterns:**
- HTTP requests are mocked using `unittest.mock.patch` with `urllib.request.urlopen`
- Marketplace YAML validation uses actual `Marketplace` model validation
- Tests verify both reference and cache files are created correctly
- Cache recovery is tested with missing cache files
- Multi-marketplace conflicts tested with multiple marketplace fixtures

## Lola Skills

These skills are installed by Lola and provide specialized capabilities.
When a task matches a skill's description, read the skill's SKILL.md file
to learn the detailed instructions and workflows.

**How to use skills:**
1. Check if your task matches any skill description below
2. Use `read_file` to read the skill's SKILL.md for detailed instructions
3. Follow the instructions in the SKILL.md file

<!-- lola:skills:start -->
<!-- lola:skills:end -->
