"""
Domain exceptions for Interview Service.
"""

class InterviewServiceError(Exception):
    """Base exception for Interview Service."""

class InterviewNotFoundError(InterviewServiceError):
    """Raised when an interview cannot be found."""
    def __init__(self, interview_id: str) -> None:
        super().__init__(f"Interview with ID {interview_id} not found.")

class SlotUnavailableError(InterviewServiceError):
    """Raised when trying to schedule an interview in an occupied slot."""
    def __init__(self, start_time: str, end_time: str) -> None:
        super().__init__(f"Time slot from {start_time} to {end_time} is unavailable.")

class InvalidInterviewStateError(InterviewServiceError):
    """Raised when performing an action invalid for the current interview state."""
    def __init__(self, state: str, action: str) -> None:
        super().__init__(f"Cannot perform {action} when interview is in state {state}.")
