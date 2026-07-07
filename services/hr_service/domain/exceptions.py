"""
Domain exceptions for HR Service.
"""

class HRServiceError(Exception):
    """Base exception for HR Service."""

class EmployeeNotFoundError(HRServiceError):
    """Raised when an employee cannot be found."""
    def __init__(self, employee_id: str) -> None:
        super().__init__(f"Employee with ID {employee_id} not found.")

class DepartmentNotFoundError(HRServiceError):
    """Raised when a department cannot be found."""
    def __init__(self, department_id: str) -> None:
        super().__init__(f"Department with ID {department_id} not found.")

class InvalidEmployeeStateError(HRServiceError):
    """Raised when performing an action invalid for the current employee state."""
    def __init__(self, state: str, action: str) -> None:
        super().__init__(f"Cannot perform {action} when employee is in state {state}.")
