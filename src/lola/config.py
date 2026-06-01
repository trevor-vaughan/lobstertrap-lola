"""
config:
    Configuration and paths for the lola package manager
"""

from pathlib import Path
import os

# Base lola directory
LOLA_HOME = Path(os.environ.get("LOLA_HOME", Path.home() / ".lola"))

# Where modules are stored after being added
MODULES_DIR = LOLA_HOME / "modules"

# Installation tracking file
INSTALLED_FILE = LOLA_HOME / "installed.yml"

# Marketplace directories
MARKET_DIR = LOLA_HOME / "market"
CACHE_DIR = MARKET_DIR / "cache"

# Skill definition filename
SKILL_FILE = "SKILL.md"

# MCP servers definition filename
MCPS_FILE = "mcps.json"


def get_user_config_dir() -> Path:
    """Get the user-scope config directory for OpenCode.

    OpenCode resolves its global config from ``$XDG_CONFIG_HOME/opencode``
    when ``XDG_CONFIG_HOME`` is set, otherwise ``~/.config/opencode`` — on
    every platform (Linux, macOS, Windows). It does not use platform-specific
    locations such as ``~/Library/Application Support`` on macOS, so neither
    do we.
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "opencode"
