"""Tests for config module."""

from __future__ import annotations

from pathlib import Path

from agent_os_kernel.config import Config, PathConfig


class TestPathConfig:
    def test_default_paths(self):
        pc = PathConfig()
        assert isinstance(pc.root, Path)
        assert pc.data_dir == pc.root / "data"
        assert pc.output_dir == pc.root / "outputs"
        assert pc.checkpoint_dir == pc.root / "checkpoints"
        assert pc.config_dir == pc.root / "configs"

    def test_custom_root(self, tmp_path):
        pc = PathConfig(root=tmp_path)
        assert pc.data_dir == tmp_path / "data"
        assert pc.output_dir == tmp_path / "outputs"
        assert pc.checkpoint_dir == tmp_path / "checkpoints"
        assert pc.config_dir == tmp_path / "configs"


class TestConfig:
    def test_defaults(self):
        cfg = Config()
        assert cfg.seed == 42
        assert isinstance(cfg.paths, PathConfig)

    def test_custom_seed(self):
        cfg = Config(seed=123)
        assert cfg.seed == 123

    def test_custom_paths(self, tmp_path):
        pc = PathConfig(root=tmp_path)
        cfg = Config(paths=pc)
        assert cfg.paths.root == tmp_path
