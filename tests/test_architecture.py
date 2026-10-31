"""Enforces the layer rules and the 200-line limit (ported from Paper Trail)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ["config", "deals", "engine", "agents", "paypal", "render", "web", "tests"]
MAX_LINES = 200

COMMON = ["config"]
FORBIDDEN = {
    "deals/domain": ["django", "httpx", "paypal", "engine", "agents", "web", "render",
                     "deals.models", "deals.services", "config"],
    "engine": ["django", "httpx", "paypal", "agents", "web", "render",
               "deals.models", "deals.services", "config"],
    "agents": ["django", "paypal", "engine", "web", "render",
               "deals.models", "deals.services", "config"],
    "paypal": ["django", "engine", "agents", "web", "render",
               "deals.models", "deals.services", "config"],
    "render": ["django", "httpx", "paypal", "engine", "agents", "web", "deals", "config"],
    "deals/models": ["paypal", "engine", "agents", "web", "render", "deals.services", "config"],
    "deals/services": ["paypal", "web", "config"],
    "web": ["paypal", "engine", "agents", "deals.models"],
}
ENV_READERS = {"config/env.py", "config/asgi.py", "manage.py"}


def py_files(*dirs):
    for d in dirs:
        for p in sorted((ROOT / d).rglob("*.py")):
            if "migrations" not in p.parts and "__pycache__" not in p.parts:
                yield p


def imports(path):
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_files_stay_under_line_limit():
    too_long = [f"{p.relative_to(ROOT)} ({len(p.read_text().splitlines())} lines)"
                for p in py_files(*SOURCE_DIRS) if len(p.read_text().splitlines()) > MAX_LINES]
    assert not too_long, f"files over {MAX_LINES} lines: {too_long}"


def test_layers_do_not_import_what_they_must_not():
    violations = []
    for layer, banned in FORBIDDEN.items():
        if not (ROOT / layer).exists():
            continue
        for p in py_files(layer):
            for mod in imports(p):
                for b in banned:
                    if mod == b or mod.startswith(b + "."):
                        rel = p.relative_to(ROOT)
                        violations.append(f"{rel} imports {mod} (banned in {layer})")
    assert not violations, "\n".join(violations)


def test_every_python_folder_has_init():
    missing = []
    for d in sorted({p.parent for p in py_files(*SOURCE_DIRS)}):
        if not (d / "__init__.py").exists():
            missing.append(str(d.relative_to(ROOT)))
    assert not missing, f"folders without __init__.py: {missing}"


def test_no_float_in_money_paths():
    pattern = re.compile(r"\bfloat\b")
    bad = []
    for p in py_files("deals/domain", "paypal", "engine"):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            code = line.split("#")[0]
            if pattern.search(code) and "isinstance" not in code and '"' not in code:
                bad.append(f"{p.relative_to(ROOT)}:{n}")
    assert not bad, f"float used in money paths: {bad}"


def test_environment_is_read_only_in_env_module():
    bad = []
    for p in list(py_files(*SOURCE_DIRS)) + [ROOT / "manage.py"]:
        rel = str(p.relative_to(ROOT))
        if rel in ENV_READERS or rel.startswith("tests/"):
            continue
        text = p.read_text()
        if "os.environ" in text or "os.getenv" in text:
            bad.append(rel)
    assert not bad, f"environment read outside config/env.py: {bad}"
