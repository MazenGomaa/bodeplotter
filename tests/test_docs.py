"""Guards on the documents. They are split over several files and kept by hand, so these
tests fail when a document drifts from the code or from the other documents:

- CLAUDE.md stays a small index and keeps the hard rules;
- the overview files stay short, and their index tables name every detail file;
- every spec or hardware-report section cited in the code exists, exactly once;
- docs/ARCHITECTURE.md lists every module with the imports it really has;
- the layering rules that file states hold in the code.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "bodeplot"
SPEC_FILES = ["docs/SPEC.md"] + sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "spec").glob("*.md"))
HW_FILES = ["HW_REPORT.md"] + sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "hw").glob("*.md"))


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- size and content
@pytest.mark.parametrize("rel, max_bytes, max_lines", [
    ("CLAUDE.md", 9000, 110),           # read in full at the start of every session
    ("docs/SPEC.md", 12000, 160),       # overview and index; the detail belongs in docs/spec/
    ("HW_REPORT.md", 30000, 160),       # facts sheet and index; dated runs belong in docs/hw/
])
def test_the_overview_files_stay_small(rel, max_bytes, max_lines):
    body = text(rel)
    size, lines = len(body.encode("utf-8")), body.count("\n")
    assert size <= max_bytes and lines <= max_lines, (
        "%s has grown to %d bytes, %d lines (limits %d, %d). Move detail into the file it belongs to "
        "(see the table at the top of CLAUDE.md) and do not raise the limit to make room."
        % (rel, size, lines, max_bytes, max_lines))


@pytest.mark.parametrize("rule", [
    "Never send `:RUN`",
    "Never send `:WAVeform:DATA?` unless a stopped record exists",
    "Never send `*OPC?` or any query missing from its manual",
    "Never send a negative number",
    "`read_termination = None`",
    "INITIATE_ABORT_BULK_IN",
    "no `*RST`",
    "switched OFF in a `finally` block",
    "Ask what is wired before EVERY bench run",
    "Commit before every bench run",
    "Select-Object -First N",
    "BODEPLOT_NO_HARDWARE",
])
def test_claude_md_keeps_the_hard_rules(rule):
    assert rule in text("CLAUDE.md"), "the hard rule %r is gone from CLAUDE.md" % rule


@pytest.mark.parametrize("index, folder", [("docs/SPEC.md", "docs/spec"), ("HW_REPORT.md", "docs/hw"),
                                           ("CLAUDE.md", "docs/spec")])
def test_every_detail_file_is_in_its_index(index, folder):
    body = text(index)
    names = sorted(p.name for p in (ROOT / folder).glob("*.md"))
    assert names, folder
    missing = [n for n in names if n not in body]
    assert not missing, "%s does not mention %s" % (index, ", ".join("%s/%s" % (folder, n) for n in missing))


ROOT_NAMES = {p.name for p in ROOT.iterdir()}
PKG_DIRS = {p.name for p in PKG.iterdir() if p.is_dir()}


def _paths_named_in(rel: str) -> list[str]:
    """Back-ticked tokens that are plainly a path into this repository."""
    out = []
    for token in re.findall(r"`([^`\s]+)`", text(rel)):
        if any(c in token for c in "*<>|\\:=") or token.startswith((".", "~", "-")):
            continue
        head = token.split("/")[0]
        if "/" in token and (head in ROOT_NAMES or head in PKG_DIRS):
            out.append(token)
        elif token in ROOT_NAMES:
            out.append(token)
    return out


@pytest.mark.parametrize("rel", ["CLAUDE.md", "docs/ARCHITECTURE.md", "docs/STATE.md"])
def test_paths_named_in_the_index_files_exist(rel):
    gone = []
    for token in _paths_named_in(rel):
        base = PKG if token.split("/")[0] in PKG_DIRS and token.split("/")[0] not in ROOT_NAMES else ROOT
        if not (base / token).exists():
            gone.append(token)
    assert not gone, "%s names paths that do not exist: %s" % (rel, ", ".join(sorted(set(gone))))


# ---------------------------------------------------------------------- section numbers
HEADING = re.compile(r"^#{2,3} (\d+(?:\.\d+)?)\.? ", re.M)


def _sections(files) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for rel in files:
        for number in HEADING.findall(text(rel)):
            found.setdefault(number, []).append(rel)
    return found


@pytest.mark.parametrize("files, top", [(SPEC_FILES, range(1, 18)), (HW_FILES, range(1, 14))])
def test_section_numbers_are_complete_and_unique(files, top):
    found = _sections(files)
    twice = {n: where for n, where in found.items() if len(where) > 1}
    assert not twice, "sections defined more than once: %s" % twice
    missing = [str(n) for n in top if str(n) not in found]
    assert not missing, "top-level sections missing from %s: %s" % (files[0], ", ".join(missing))


def _cited(name: str) -> dict[str, list[str]]:
    """Section numbers the code cites, e.g. 'SPEC.md section 8.6' or 'HW_REPORT 13.21'."""
    pattern = re.compile(name + r"(?:\.md)?`?,?\s+(?:sections?\s+|§\s*)?(\d+(?:\.\d+)?)")
    cited: dict[str, list[str]] = {}
    for folder in ("src", "tests", "hwcheck"):
        for path in (ROOT / folder).rglob("*.py"):
            if path.name == "test_docs.py":
                continue
            for number in pattern.findall(path.read_text(encoding="utf-8", errors="replace")):
                cited.setdefault(number, []).append(path.relative_to(ROOT).as_posix())
    return cited


@pytest.mark.parametrize("name, files", [("SPEC", SPEC_FILES), ("HW_REPORT", HW_FILES)])
def test_every_section_cited_in_the_code_exists(name, files):
    found = _sections(files)
    cited = _cited(name)
    assert cited, "no citation of %s found in the code: the pattern of this test no longer fits" % name
    dangling = {n: sorted(set(where)) for n, where in cited.items() if n not in found}
    assert not dangling, "the code cites %s sections that no document defines: %s" % (name, dangling)


# ---------------------------------------------------------------------- architecture map
def _modules() -> dict[str, Path]:
    out = {}
    for path in sorted(PKG.rglob("*.py")):
        if path.name == "__init__.py" and not path.read_text(encoding="utf-8").strip():
            continue
        out[path.relative_to(PKG).as_posix()] = path
    return out


def _imports(path: Path) -> tuple[set[str], set[str]]:
    """(modules of this package, top-level names of everything else) that a file imports."""
    package = ("bodeplot",) + path.relative_to(PKG).parts[:-1]
    inside, outside = set(), set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = package[:len(package) - node.level + 1]
            module = base + tuple(node.module.split(".")) if node.module else base
            for alias in node.names:
                as_module = PKG.joinpath(*(module + (alias.name,))[1:]).with_suffix(".py")
                target = (module + (alias.name,)) if as_module.exists() else module
                rel = "/".join(target[1:])
                inside.add(rel + ".py" if rel else "__init__.py")
        elif isinstance(node, ast.ImportFrom):
            (inside if node.module.split(".")[0] == "bodeplot" else outside).add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            outside.update(alias.name.split(".")[0] for alias in node.names)
    return inside, outside - set(sys.stdlib_module_names)


def _documented() -> dict[str, set[str]]:
    """The 'Modules' table of docs/ARCHITECTURE.md: module -> the imports its row lists."""
    section = text("docs/ARCHITECTURE.md").split("## Modules", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and re.fullmatch(r"`[\w/]+\.py`", cells[0]):
            rows[cells[0].strip("`")] = set(re.findall(r"`([\w/]+\.py)`", cells[2]))
    return rows


def test_architecture_map_lists_every_module_and_only_modules_that_exist():
    real, documented = set(_modules()), set(_documented())
    assert documented, "the Modules table of docs/ARCHITECTURE.md could not be read"
    assert not real - documented, "not in docs/ARCHITECTURE.md: %s" % sorted(real - documented)
    assert not documented - real, "in docs/ARCHITECTURE.md but not in src/bodeplot: %s" % sorted(documented - real)


def test_architecture_map_shows_the_real_imports():
    documented = _documented()
    wrong = []
    for name, path in _modules().items():
        real = _imports(path)[0]
        assert "bodeplot" not in real, "%s uses an absolute import of the package; the map only follows relative ones" % name
        listed = documented.get(name, set())
        if real != listed:
            wrong.append("%s: add %s, remove %s" % (name, sorted(real - listed) or "-", sorted(listed - real) or "-"))
    assert not wrong, ("docs/ARCHITECTURE.md is out of step with the code. Update the 'Imports' cell of these rows, "
                       "and the text around the table if a concern moved:\n  " + "\n  ".join(wrong))


def test_layering_rules_of_the_architecture_map():
    qt_allowed = lambda name: name.startswith("gui/") or name in ("app.py", "sweep/engine.py")
    broken = []
    for name, path in _modules().items():
        outside = _imports(path)[1]
        if outside & {"PySide6", "pyqtgraph"} and not qt_allowed(name):
            broken.append("%s imports Qt" % name)
        if "pyvisa" in outside and name != "drivers/visa_util.py":
            broken.append("%s imports pyvisa" % name)
        if outside & {"usb", "libusb_package"} and name != "drivers/transport.py":
            broken.append("%s imports pyusb" % name)
        if outside & {"hwcheck", "iolayer", "common"}:
            broken.append("%s imports the bench scripts" % name)
    assert not broken, broken
