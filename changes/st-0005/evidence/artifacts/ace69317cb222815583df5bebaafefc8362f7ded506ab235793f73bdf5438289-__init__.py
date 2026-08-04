"""Outward adapters for RAOS application ports."""

from raos.adapters.queue_fake import DeadLetter, QueueFake

__all__ = ["DeadLetter", "QueueFake"]
