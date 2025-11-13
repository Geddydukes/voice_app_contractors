"""Infrastructure automation helpers for the CVA platform."""

from pathlib import Path

INFRA_ROOT = Path(__file__).resolve().parent

__all__ = ["INFRA_ROOT"]
