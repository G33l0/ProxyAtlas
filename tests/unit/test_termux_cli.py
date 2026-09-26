"""Ensure the CLI works headlessly without PyQt6 (Termux/servers)."""

import subprocess
import sys
import textwrap


def test_cli_runs_without_pyqt6(tmp_path):
    """The CLI import + commands must not require PyQt6.

    Run in a subprocess whose import system refuses PyQt6, proving the headless
    path never imports Qt.
    """
    script = textwrap.dedent(
        f"""
        import sys, os, importlib.util
        os.environ["PROXYATLAS_DATA_DIR"] = {str(tmp_path)!r}

        # Simulate Termux where PyQt6 is genuinely absent: find_spec -> None.
        _orig = importlib.util.find_spec
        def _fake(name, *a, **k):
            if name == "PyQt6" or name.startswith("PyQt6."):
                return None
            return _orig(name, *a, **k)
        importlib.util.find_spec = _fake

        from app.cli import main
        assert main(["--version"]) == 0
        assert main(["--stats"]) == 0
        # GUI request degrades gracefully (exit 2), never imports PyQt6.
        assert main(["--gui"]) == 2
        assert not any(m == "PyQt6" or m.startswith("PyQt6.") for m in sys.modules), "PyQt6 was imported"
        print("HEADLESS_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=".",
    )
    assert "HEADLESS_OK" in result.stdout, result.stdout + result.stderr
