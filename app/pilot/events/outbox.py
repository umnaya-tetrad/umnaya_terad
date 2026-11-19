"""Transactional event facts use the shared audit/outbox writer."""

from .audit import audit

__all__ = ["audit"]
