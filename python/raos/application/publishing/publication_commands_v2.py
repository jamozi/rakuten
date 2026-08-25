"""ENV-DEV/CI-only application service for ST-0905 commands."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.publication_commands_v2 import (
    PublicationCommandFailure,
    PublicationCommandFailureCode,
    PublicationCommandResultV2,
    PublishCommandV2,
    RollbackCommandV2,
    UnpublishCommandV2,
    fail_publication_command,
)
from raos.ports.publishing.publication_commands_v2 import PublicationCommandStoreV2


def _supports(value: object) -> bool:
    try:
        return isinstance(value, PublicationCommandStoreV2)
    except Exception:
        return False


@final
class PublicationCommandServiceV2:
    """Dispatch typed commands only to a closed local transaction store."""

    __slots__ = ("_store",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        store: PublicationCommandStoreV2,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _supports(cast(object, store))
        ):
            fail_publication_command(
                PublicationCommandFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._store = store

    def publish(self, command: PublishCommandV2) -> PublicationCommandResultV2:
        if type(command) is not PublishCommandV2:
            fail_publication_command()
        try:
            return self._store.publish(command)
        except Exception as error:
            if type(error) is PublicationCommandFailure:
                raise
            fail_publication_command(PublicationCommandFailureCode.TRANSACTION_FAILED)

    def rollback(self, command: RollbackCommandV2) -> PublicationCommandResultV2:
        if type(command) is not RollbackCommandV2:
            fail_publication_command()
        try:
            return self._store.rollback(command)
        except Exception as error:
            if type(error) is PublicationCommandFailure:
                raise
            fail_publication_command(PublicationCommandFailureCode.TRANSACTION_FAILED)

    def unpublish(self, command: UnpublishCommandV2) -> None:
        del command
        fail_publication_command(
            PublicationCommandFailureCode.UNPUBLISH_ROLE_ACTION_UNDEFINED
        )


__all__ = ("PublicationCommandServiceV2",)
