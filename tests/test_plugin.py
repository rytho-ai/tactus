"""Plugin manifests and references must remain usable outside the source checkout."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT
SKILLS = PLUGIN / "skills"


def test_marketplaces_resolve_the_same_versioned_plugin():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    description = project["description"]
    name = project["name"]
    codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    [codex_entry] = codex["plugins"]
    [claude_entry] = claude["plugins"]
    assert (ROOT / codex_entry["source"]["path"]).resolve() == PLUGIN
    assert (ROOT / claude_entry["source"]).resolve() == PLUGIN
    assert codex["name"] == claude["name"] == "tactus"
    assert codex_entry["name"] == claude_entry["name"] == name
    assert codex_entry["source"]["source"] == "local"
    assert claude_entry["version"] == version
    assert claude_entry["description"] == claude["metadata"]["description"] == description
    for host in (".codex-plugin", ".claude-plugin"):
        manifest = json.loads((PLUGIN / host / "plugin.json").read_text())
        assert manifest["name"] == name
        assert manifest["description"] == description
        assert manifest["version"] == version
        if host == ".codex-plugin":
            assert (PLUGIN / manifest["skills"]).resolve() == SKILLS
            assert manifest["interface"]["shortDescription"] == description
    assert {p.parent.name for p in SKILLS.glob("*/SKILL.md")} == {
        "compose",
        "dsp",
        "measure",
        "version",
    }


def _anchors(text: str) -> set[str]:
    headings = re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE)
    return {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}


def test_copied_plugin_references_are_self_contained(tmp_path):
    """Cache/install copies must not depend on sibling repo files or private paths."""
    copied = tmp_path / "installed-plugin"
    shutil.copytree(SKILLS, copied / "skills")
    shutil.copytree(PLUGIN / "design", copied / "design")
    for host in (".codex-plugin", ".claude-plugin"):
        (copied / host).mkdir()
        shutil.copy2(PLUGIN / host / "plugin.json", copied / host / "plugin.json")
    manifest = json.loads((copied / ".codex-plugin/plugin.json").read_text())
    for key in ("composerIcon", "logo"):
        target = (copied / manifest["interface"][key]).resolve()
        assert target.is_relative_to(copied)
        assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    for document in copied.rglob("*.md"):
        text = document.read_text()
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (document.parent / unquote(url.path)).resolve() if url.path else document
            assert target.is_relative_to(copied), (document, link)
            assert target.exists(), (document, link)
            if url.fragment and target.suffix == ".md":
                assert unquote(url.fragment) in _anchors(target.read_text()), (document, link)
