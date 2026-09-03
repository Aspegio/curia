"""The fence: the mechanism repo must not name any estate, its products or its
principal. The denylist comes from the estates registered on this machine, so
the mechanism never has to contain the words it is forbidden to contain."""
import pathlib
import re
import tomllib

import pytest

MECH = pathlib.Path(__file__).resolve().parent.parent
ESTATES = pathlib.Path.home() / ".config" / "curia" / "estates.toml"
SCAN_SUFFIXES = {".py", ".md", ".toml", ".plist", ".json", ""}


def denylist() -> set[str]:
    words: set[str] = set()
    if not ESTATES.exists():
        return words
    with open(ESTATES, "rb") as f:
        estates = tomllib.load(f).get("estates", {})
    for e in estates.values():
        p = pathlib.Path(e["path"]).expanduser()
        if (p / "estate.toml").exists():
            with open(p / "estate.toml", "rb") as f:
                m = tomllib.load(f)
            words.update(m.get("denylist", []))
            words.add(m.get("name", ""))
            words.update(m.get("principal", "").split())
        if (p / "repos.toml").exists():
            with open(p / "repos.toml", "rb") as f:
                words.update(tomllib.load(f).get("repos", {}).keys())
    return {w for w in words if len(w) > 2}


def test_mechanism_names_no_estate():
    words = denylist()
    if not words:
        pytest.skip("no estates registered; nothing to fence against")
    hits = []
    for f in MECH.rglob("*"):
        if not f.is_file() or ".git" in f.parts or "__pycache__" in f.parts:
            continue
        if f.suffix not in SCAN_SUFFIXES:
            continue
        text = f.read_text(errors="ignore")
        for w in sorted(words):
            if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE):
                hits.append(f"{f.relative_to(MECH)}: {w}")
    assert not hits, "mechanism names an estate:\n" + "\n".join(hits)
