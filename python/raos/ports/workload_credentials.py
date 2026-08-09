"""Inward material-free workload credential and rotation ports."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from raos.domain.iam.workload_credentials import (
    CredentialLease,
    CredentialRequest,
    CredentialRotationNotice,
)


@runtime_checkable
class WorkloadCredentialPort(Protocol):
    """Acquire one opaque lease without exposing credential material."""

    def acquire(self, *, request: CredentialRequest, now: datetime) -> CredentialLease:
        """Return one fresh lease for the exact request and observation time."""

        ...


@runtime_checkable
class CredentialRotationHook(Protocol):
    """Synchronously observe one validated metadata-only rotation."""

    def notify(self, notice: CredentialRotationNotice) -> None:
        """Handle the notice once without receiving credential material."""

        ...


__all__ = ["CredentialRotationHook", "WorkloadCredentialPort"]
