"""
Domain exceptions for Onboarding Service.
"""

class OnboardingServiceError(Exception):
    """Base exception for Onboarding Service."""

class OnboardingNotFoundError(OnboardingServiceError):
    """Raised when an onboarding record cannot be found."""
    def __init__(self, onboarding_id: str) -> None:
        super().__init__(f"Onboarding record with ID {onboarding_id} not found.")

class TaskNotFoundError(OnboardingServiceError):
    """Raised when a specific task is not found within an onboarding plan."""
    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task with ID {task_id} not found.")

class InvalidOnboardingStateError(OnboardingServiceError):
    """Raised when performing an action invalid for the current onboarding state."""
    def __init__(self, state: str, action: str) -> None:
        super().__init__(f"Cannot perform {action} when onboarding is in state {state}.")
