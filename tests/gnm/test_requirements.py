"""Tests for repository dependency hygiene and quickstart tooling."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO / rel).read_text()


def test_requirements_demo_exists():
    assert (REPO / "requirements-demo.txt").exists(), "requirements-demo.txt is missing"


def test_requirements_demo_contains_numpy():
    content = _read("requirements-demo.txt")
    assert "numpy" in content


def test_requirements_demo_contains_pytest():
    content = _read("requirements-demo.txt")
    assert "pytest" in content


def test_requirements_txt_does_not_pin_torch():
    content = _read("requirements.txt")
    assert "torch==2.2.2" not in content, (
        "requirements.txt must not pin torch==2.2.2; "
        "use requirements-ml.txt for ML dependencies"
    )


def test_requirements_ml_exists():
    assert (REPO / "requirements-ml.txt").exists(), "requirements-ml.txt is missing"


def test_requirements_ml_documents_torch_install():
    content = _read("requirements-ml.txt")
    assert "pytorch.org" in content, (
        "requirements-ml.txt should reference pytorch.org for installation instructions"
    )


def test_bootstrap_script_exists():
    assert (REPO / "scripts/gnm/bootstrap_demo_env.sh").exists(), (
        "scripts/gnm/bootstrap_demo_env.sh is missing"
    )


def test_link_script_exists():
    assert (REPO / "scripts/gnm/link_vlntube_data.sh").exists(), (
        "scripts/gnm/link_vlntube_data.sh is missing"
    )


def test_check_demo_ready_exists():
    assert (REPO / "scripts/gnm/check_demo_ready.py").exists(), (
        "scripts/gnm/check_demo_ready.py is missing"
    )


def test_readme_uses_bootstrap_script():
    content = _read("README.md")
    assert "bootstrap_demo_env.sh" in content, (
        "README.md should reference bootstrap_demo_env.sh"
    )


def test_readme_uses_check_demo_ready():
    content = _read("README.md")
    assert "check_demo_ready.py" in content, (
        "README.md should reference check_demo_ready.py"
    )


def test_readme_no_placeholder_path():
    content = _read("README.md")
    # The literal copy-paste command must not appear; a note may use it as text
    assert "ln -sfn /path/to/vlntube/train" not in content, (
        "README.md must not contain the placeholder `ln -sfn /path/to/vlntube/train` "
        "as a copy-paste command; use link_vlntube_data.sh instead"
    )


def test_quickstart_uses_bootstrap_script():
    content = _read("QUICKSTART.md")
    assert "bootstrap_demo_env.sh" in content, (
        "QUICKSTART.md should reference bootstrap_demo_env.sh"
    )


def test_quickstart_uses_check_demo_ready():
    content = _read("QUICKSTART.md")
    assert "check_demo_ready.py" in content, (
        "QUICKSTART.md should reference check_demo_ready.py"
    )


def test_quickstart_uses_link_script():
    content = _read("QUICKSTART.md")
    assert "link_vlntube_data.sh" in content, (
        "QUICKSTART.md should reference link_vlntube_data.sh"
    )


def test_quickstart_no_placeholder_path():
    content = _read("QUICKSTART.md")
    assert "ln -sfn /path/to/vlntube/train" not in content, (
        "QUICKSTART.md must not contain `ln -sfn /path/to/vlntube/train` as a command"
    )


# ── Torch-free package initialiser regression tests ──────────────────────────

def test_data_package_importable_without_torch():
    """gnm_vlnverse.data must be importable without torch installed."""
    import importlib, sys

    # Remove any cached imports so we get a clean import
    for key in list(sys.modules.keys()):
        if key.startswith("gnm_vlnverse"):
            del sys.modules[key]

    # Temporarily hide torch if it happens to be present
    torch_backup = sys.modules.pop("torch", None)
    try:
        mod = importlib.import_module("gnm_vlnverse.data")
        assert hasattr(mod, "VLNTubeConverter"), "VLNTubeConverter should be exported"
    finally:
        if torch_backup is not None:
            sys.modules["torch"] = torch_backup
        for key in list(sys.modules.keys()):
            if key.startswith("gnm_vlnverse"):
                del sys.modules[key]


def test_evaluation_package_importable_without_torch():
    """gnm_vlnverse.evaluation must be importable without torch installed."""
    import importlib, sys

    for key in list(sys.modules.keys()):
        if key.startswith("gnm_vlnverse"):
            del sys.modules[key]

    torch_backup = sys.modules.pop("torch", None)
    try:
        mod = importlib.import_module("gnm_vlnverse.evaluation")
        assert hasattr(mod, "NavigationMetrics"), "NavigationMetrics should be exported"
    finally:
        if torch_backup is not None:
            sys.modules["torch"] = torch_backup
        for key in list(sys.modules.keys()):
            if key.startswith("gnm_vlnverse"):
                del sys.modules[key]


def test_data_init_does_not_eagerly_import_torch():
    """gnm_vlnverse.data.__init__ must not import torch at package import time."""
    import ast
    path = REPO / "gnm_vlnverse" / "data" / "__init__.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in getattr(node, "names", [])]
            module = getattr(node, "module", "") or ""
            assert "torch" not in module and all("torch" not in n for n in names), (
                f"gnm_vlnverse/data/__init__.py must not import torch at package level; "
                f"found: {ast.dump(node)}"
            )


def test_evaluation_init_does_not_eagerly_import_torch():
    """gnm_vlnverse.evaluation.__init__ must not import torch at package import time."""
    import ast
    path = REPO / "gnm_vlnverse" / "evaluation" / "__init__.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in getattr(node, "names", [])]
            module = getattr(node, "module", "") or ""
            assert "torch" not in module and all("torch" not in n for n in names), (
                f"gnm_vlnverse/evaluation/__init__.py must not import torch at package level; "
                f"found: {ast.dump(node)}"
            )


def test_readme_states_torch_is_optional():
    content = _read("README.md")
    assert "optional" in content.lower() and "pytorch" in content.lower(), (
        "README.md should state that PyTorch is optional for the proof pipeline"
    )


def test_quickstart_states_torch_is_optional():
    content = _read("QUICKSTART.md")
    assert "optional" in content.lower() and "pytorch" in content.lower(), (
        "QUICKSTART.md should state that PyTorch is optional for the proof pipeline"
    )
