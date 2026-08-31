"""config 模块测试。"""

from __future__ import annotations

from coding.config import Settings, get_settings


def test_get_settings_creates_dirs(tmp_path, monkeypatch):
    s = get_settings()
    assert s.data_dir.exists()
    assert s.memory_file.exists()
    assert s.checkpoints_db.parent.exists()
    # 技能目录包含仓库 skills/（若存在）与 curator 产出目录
    assert any("skills" in d for d in s.skills_dirs)


def test_ensure_dirs_idempotent(tmp_path):
    s = Settings(
        data_dir=tmp_path / "d",
        sessions_db=tmp_path / "d" / "sessions.db",
        checkpoints_db=tmp_path / "d" / "cp.db",
        static_dir=tmp_path / "static",
        outputs_dir=tmp_path / "outputs",
        skills_dirs=(),
        memory_file=tmp_path / "d" / "memory" / "AGENTS.md",
    )
    s.ensure_dirs()
    s.ensure_dirs()
    assert s.memory_file.exists()
