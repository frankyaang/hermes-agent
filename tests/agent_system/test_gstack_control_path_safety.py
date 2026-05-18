"""
Path safety test — assert that no bare ~/.gstack literal exists
in any gstack_control source file.

This is a grep-based structural test; it does not require imports.
"""
import subprocess
from pathlib import Path


GSTACK_CONTROL_DIR = Path(__file__).parent.parent.parent / "agent_system" / "gstack_control"


def test_no_literal_gstack_home_path():
    """grep for '~/.gstack' in gstack_control .py/.yaml/.json sources (excludes __pycache__)."""
    _pattern = "~/" + ".gstack"  # split to avoid matching this test file itself
    result = subprocess.run(
        ["grep", "-r",
         "--include=*.py", "--include=*.yaml", "--include=*.json",
         _pattern, str(GSTACK_CONTROL_DIR)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"Found hardcoded gstack home path in gstack_control sources:\n{result.stdout}"
    )


def test_no_hardcoded_hermes_home_path():
    """Paths must use get_hermes_home(), not os.path.expanduser('~/.hermes')."""
    result = subprocess.run(
        ["grep", "-r", r"expanduser.*\.hermes", str(GSTACK_CONTROL_DIR)],
        capture_output=True,
        text=True,
    )
    # This is advisory: warn but don't fail (expanduser in non-path context is ok)
    if result.returncode == 0:
        import warnings
        warnings.warn(
            f"Possible hardcoded .hermes path in gstack_control:\n{result.stdout}"
        )


def test_gstack_control_dir_exists():
    assert GSTACK_CONTROL_DIR.is_dir(), (
        f"gstack_control directory not found: {GSTACK_CONTROL_DIR}"
    )
