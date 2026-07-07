"""
Domain exceptions for Voice Service.
"""

class VoiceServiceError(Exception):
    """Base exception for Voice Service."""


class CallNotFoundError(VoiceServiceError):
    """Raised when a call aggregate cannot be found."""
    def __init__(self, call_id: str) -> None:
        super().__init__(f"Call with ID {call_id} not found.")


class InvalidCallStateTransitionError(VoiceServiceError):
    """Raised on illegal state machine transitions."""
    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(f"Cannot transition call from {from_state} to {to_state}.")


class StreamInitializationError(VoiceServiceError):
    """Raised when media stream cannot be initialized."""
