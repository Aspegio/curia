"""The fence: the mechanism repo must not name any estate, its products or its
principal. The denylist comes from the estates registered on this machine, so
the mechanism never has to contain the words it is forbidden to contain."""
import pathlib
import re
import tomllib

import pytest

MECH = pathlib.Path(__file__).resolve().parent.parent
ESTATES = pathlib.Path.home() / ".config" / "curia" / "estates.toml"
SCAN_SUFFIXES = {".py", ".md", ".toml", ".plist", ".json", ".jsonl", ".html", ""}


# The copyright line in LICENSE names who wrote the software, not whom an
# estate serves; it is the same whichever estate runs. So LICENSE may name a
# principal, and nothing else: an estate's name, denylist or repos in it still fail.
PRINCIPAL_MAY_APPEAR = {"LICENSE"}


def denylist() -> tuple[set[str], set[str]]:
    """(every forbidden word, those that are only a principal's name: a word of
    one, or a phrase an estate's denylist spells from nothing else)."""
    words: set[str] = set()
    principals: set[str] = set()
    if not ESTATES.exists():
        return words, principals
    with open(ESTATES, "rb") as f:
        estates = tomllib.load(f).get("estates", {})
    for e in estates.values():
        p = pathlib.Path(e["path"]).expanduser()
        if (p / "estate.toml").exists():
            with open(p / "estate.toml", "rb") as f:
                m = tomllib.load(f)
            words.update(m.get("denylist", []))
            words.add(m.get("name", ""))
            principals.update(m.get("principal", "").split())
        if (p / "repos.toml").exists():
            with open(p / "repos.toml", "rb") as f:
                words.update(tomllib.load(f).get("repos", {}).keys())
    words = {w for w in words | principals if len(w) > 2}
    names = {w.lower() for w in principals}
    return words, {w for w in words if set(w.lower().split()) <= names}


def forbidden_in(rel: pathlib.Path, words: set[str], principals: set[str]) -> set[str]:
    return words - principals if rel.as_posix() in PRINCIPAL_MAY_APPEAR else words


def test_license_may_name_a_principal_and_nothing_else():
    words, principals = {"acme", "ada", "lovelace", "Ada Lovelace"}, {"ada", "lovelace", "Ada Lovelace"}
    assert forbidden_in(pathlib.Path("LICENSE"), words, principals) == {"acme"}
    assert forbidden_in(pathlib.Path("bin/curia"), words, principals) == words
    assert forbidden_in(pathlib.Path("docs/LICENSE"), words, principals) == words


def test_mechanism_names_no_estate():
    words, principals = denylist()
    if not words:
        pytest.skip("no estates registered; nothing to fence against")
    hits = []
    for f in MECH.rglob("*"):
        if not f.is_file() or ".git" in f.parts or "__pycache__" in f.parts:
            continue
        if f.suffix not in SCAN_SUFFIXES:
            continue
        rel = f.relative_to(MECH)
        text = f.read_text(errors="ignore")
        for w in sorted(forbidden_in(rel, words, principals)):
            if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE):
                hits.append(f"{rel}: {w}")
    assert not hits, "mechanism names an estate:\n" + "\n".join(hits)
