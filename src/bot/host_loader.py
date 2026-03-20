"""Loads TRPG host configurations from the hosts/ directory."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bot.config import HOSTS_DIR


@dataclass
class AgentInfo:
    name: str
    description: str
    content: str


@dataclass
class HostConfig:
    name: str
    instructions: str
    agents: list[AgentInfo] = field(default_factory=list)
    host_dir: Path = field(default_factory=lambda: Path("."))


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_agent_file(path: Path) -> AgentInfo:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    content = raw

    m = _FRONTMATTER_RE.match(raw)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        content = raw[m.end():]

    return AgentInfo(
        name=meta.get("name", path.stem),
        description=meta.get("description", ""),
        content=content.strip(),
    )


def list_hosts() -> list[str]:
    """Return available host type names by scanning hosts/ subdirectories."""
    if not HOSTS_DIR.is_dir():
        return []
    return sorted(
        d.name for d in HOSTS_DIR.iterdir()
        if d.is_dir() and (d / ".github").is_dir()
    )


def load_host(host_type: str) -> HostConfig:
    """Load a host configuration from hosts/{host_type}/.github/."""
    base = HOSTS_DIR / host_type / ".github"
    if not base.is_dir():
        raise FileNotFoundError(f"Host config not found: {base}")

    instructions = ""
    instructions_file = base / "copilot-instructions.md"
    if instructions_file.is_file():
        instructions = instructions_file.read_text(encoding="utf-8")

    agents: list[AgentInfo] = []
    agents_dir = base / "agents"
    if agents_dir.is_dir():
        for f in sorted(agents_dir.glob("*.agent.md")):
            agents.append(_parse_agent_file(f))

    host_dir = HOSTS_DIR / host_type

    return HostConfig(name=host_type, instructions=instructions, agents=agents, host_dir=host_dir)


def list_models() -> list[str]:
    """Return available game module filenames from models/."""
    from bot.config import MODELS_DIR
    if not MODELS_DIR.is_dir():
        return []
    return sorted(
        f.name for f in MODELS_DIR.iterdir()
        if f.is_file() and f.suffix in (".txt", ".md", ".json")
    )


def load_model_content(model_name: str) -> str:
    """Read the content of a game module file."""
    from bot.config import MODELS_DIR
    path = MODELS_DIR / model_name
    if not path.is_file():
        raise FileNotFoundError(f"Game module not found: {path}")
    return path.read_text(encoding="utf-8")
