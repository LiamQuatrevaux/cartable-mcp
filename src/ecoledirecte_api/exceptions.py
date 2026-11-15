# SPDX-FileCopyrightText: 2025 Giga77
# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

import re
from typing import Any

_SECRET_RE = re.compile(
    r"""(['"]?(?:motdepasse|password|access[_-]?token|token|socketToken|2FA-Token|x-token)['"]?\s*[:=]\s*)(['"]?)([^'\",}\s]+)(\2)""",
    re.IGNORECASE,
)


def _redact(value: object) -> str:
    """Remove credential values from anything that may be surfaced."""
    return _SECRET_RE.sub(r"\1\2***\4", str(value))


class BaseEcoleDirecteException(Exception):
    """Base exception for Ecole Directe errors."""

    def __init__(
        self,
        path: str | None = None,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
        status: int | str | None = None,
        message: object | None = None,
    ) -> None:
        """
        Constructor

        :param path: the path of the API endpoint
        :param params: the parameters of the API endpoint
        :param payload: the payload of the API endpoint
        :param status: the HTTP status code
        :param message: the message of the exception
        """
        if path is None:
            self.message = _redact(message) if message is not None else "Ecole Directe error."
        else:
            self.message = (
                f"Error occurred while calling [{path}] with params "
                f"[{_redact(params)}] and payload [{_redact(payload)}]"
            )
            if status is not None:
                self.message += f" - status [{status}]"
            if message is not None:
                self.message += f": {_redact(message)}"

        super().__init__(self.message)


class EcoleDirecteException(BaseEcoleDirecteException):
    """Raised when an undefined error occurs while communicating with the Ecole Directe API."""


class SessionLimitException(EcoleDirecteException):
    """Raised when Ecole Directe refuses to open another session."""


class ServiceUnavailableException(BaseEcoleDirecteException):
    """Raised when the service is unavailable."""


class LoginException(BaseEcoleDirecteException):
    """Raised when MFA is required."""


class NotAuthenticatedException(LoginException):
    """Raised when user is not authenticated."""


class MFARequiredException(LoginException):
    """Raised when MFA is required."""


class GTKException(LoginException):
    """Raised when cookies is not good."""


class QCMException(LoginException):
    """Raised when QCM stuff is not good."""


class ReadOnlyViolation(EcoleDirecteException):
    """Raised when a write request is attempted on a read-only client."""


class QCMChallengeRequired(QCMException):
    """Raised when Ecole Directe asks a verification question.

    The MCP layer catches it, asks the user for the answer, then retries the
    login with the answer stored in the client's ``qcm_json``.
    """

    def __init__(self, question: str, propositions: list[str]) -> None:
        self.question = question
        self.propositions = propositions
        super().__init__(
            path="/connexion/doubleauth.awp",
            message="QCM de connexion requis.",
        )
