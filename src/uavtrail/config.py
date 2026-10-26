"""Settings live in config/ and are read here; code carries no thresholds of its own."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def root() -> Path:
    env = os.environ.get("UAV_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("UAV_DATA", root() / "data"))


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache
def targets() -> dict[str, Any]:
    return dict(_load(root() / "config" / "targets.yaml"))


@lru_cache
def codes() -> dict[str, dict[str, Any]]:
    return dict(_load(root() / "config" / "codes.yaml"))


@lru_cache
def line() -> dict[str, Any]:
    return dict(_load(root() / "config" / "line.yaml"))


@lru_cache
def analysis() -> dict[str, Any]:
    return dict(_load(root() / "config" / "analysis.yaml"))


def recipe(name: str) -> dict[str, Any]:
    return dict(_load(root() / "config" / "recipes" / f"{name}.yaml"))


def database_url() -> str:
    return os.environ.get("UAV_DATABASE_URL", "postgresql+psycopg://uav:uav@localhost:5432/uav")
