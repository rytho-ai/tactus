"""Plugin manifests and references must remain usable outside the source checkout."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "tactus"


def test_marketplaces_resolve_the_same_versioned_plugin():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    [codex_entry] = codex["plugins"]
    [claude_entry] = claude["plugins"]
    assert (ROOT / codex_entry["source"]["path"]).resolve() == PLUGIN
    assert (ROOT / claude_entry["source"]).resolve() == PLUGIN
    assert claude_entry["version"] == version
    for host in (".codex-plugin", ".claude-plugin"):
        manifest = json.loads((PLUGIN / host / "plugin.json").read_text())
        assert manifest["name"] == "tactus"
        assert manifest["version"] == version
    assert {p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md")} == {
        "compose",
        "dsp",
        "measure",
    }


def _anchors(text: str) -> set[str]:
    headings = re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE)
    return {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}


def test_copied_plugin_references_are_self_contained(tmp_path):
    """Cache/install copies must not depend on sibling repo files or private paths."""
    copied = tmp_path / "installed-plugin"
    shutil.copytree(PLUGIN, copied)
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
