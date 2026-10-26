"""The .env lookup order and the one-model rule."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from config import settings

ROOT = Path(__file__).resolve().parents[1]


def test_env_lookup_prefers_repo_then_parent(tmp_path):
    repo = tmp_path / "parent" / "repo"
    repo.mkdir(parents=True)
    assert settings.find_env_file(repo) is None
    (repo.parent / ".env").write_text("PORTKEY_API_KEY=parent\n")
    assert settings.find_env_file(repo) == repo.parent / ".env"
    (repo / ".env").write_text("PORTKEY_API_KEY=repo\n")
    assert settings.find_env_file(repo) == repo / ".env"
    assert settings.env_source_label(repo / ".env", repo) == "repo/.env"
    assert settings.env_source_label(repo.parent / ".env", repo).startswith("../.env")


def test_check_models_passes_on_repo():
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_models.py")], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout


def test_check_models_fails_on_another_model_name():
    bad = ROOT / "tests" / "_tmp_other_model.txt"
    bad.write_text("model = " + "gp" + "t-4o-mini\n")  # built at runtime so this file stays clean
    try:
        res = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_models.py")], capture_output=True, text=True)
        assert res.returncode == 1 and "_tmp_other_model.txt" in res.stdout
    finally:
        bad.unlink()


def test_model_is_defined_once():
    from backend import model
    assert model.MODEL_NAME == "gpt-6-luna"
    marker = "MODEL_NAME" + " = "
    hits = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and marker in p.read_text()]
    assert [p.name for p in hits] == ["model.py"]
