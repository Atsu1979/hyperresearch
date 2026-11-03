"""scripts/bench_vault.py is what the Japanese README's numbers come from;
keep it runnable so those numbers stay reproducible."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_vault.py"


def test_bench_script_runs_and_indexes_every_note(capsys):
    spec = importlib.util.spec_from_file_location("bench_vault", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.main(["--notes", "25", "--words", "40", "--queries", "10"]) == 0

    out = capsys.readouterr().out
    assert "notes indexed     25  (sync added=25)" in out
    assert "search queries    10" in out
