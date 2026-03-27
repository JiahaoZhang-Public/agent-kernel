"""Project configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PathConfig:
    """Standard project paths."""

    root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def output_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def checkpoint_dir(self) -> Path:
        return self.root / "checkpoints"

    @property
    def config_dir(self) -> Path:
        return self.root / "configs"


@dataclass
class Config:
    """Base experiment configuration. Extend this for your experiments."""

    seed: int = 42
    paths: PathConfig = field(default_factory=PathConfig)
