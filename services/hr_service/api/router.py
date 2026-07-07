"""
HR Service REST API Router.

Exposes endpoints for managing employees and departments.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from services.hr_service.application.use_cases import CreateEmployeeUseCase, UpdateEmployeeContactUseCase
from shared.auth import get_current_user, TokenClaims, require_roles
from shared.idempotency import get_idempotency_key, IdempotencyStore, require_idempotency_key
from shared.unit_of_work import get_uow, UnitOfWork

router = APIRouter(prefix="/v1/hr", tags=["HR"])

class CreateEmployeeRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    department_id: str
    position: str

class EmployeeResponse(BaseModel):
    employee_id: str
    status: str = "created"


@router.post("/employees", response_model=EmployeeResponse)
async def create_employee(
    req: CreateEmployeeRequest,
    user: TokenClaims = Depends(require_roles("hr_admin", "system")),
    idem_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_uow),
) -> Any:
    """
    Create a new employee profile.
    Protected by Auth, Roles, and Idempotency.
    """
    idem_store = IdempotencyStore(user.tenant_id)
    
    cached_resp = await idem_store.get_stored_response(idem_key, "/v1/hr/employees")
    if cached_resp:
        return cached_resp["body"]

    acquired = await idem_store.mark_in_flight(idem_key, "/v1/hr/employees")
    if not acquired:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Request already in progress")

    try:
        use_case = CreateEmployeeUseCase(uow)
        employee_id = await use_case.execute(
            tenant_id=user.tenant_id,
            first_name=req.first_name,
            last_name=req.last_name,
            email=req.email,
            phone_number=req.phone_number,
            department_id=req.department_id,
            position=req.position,
        )
        
        response_body = EmployeeResponse(employee_id=employee_id).model_dump()
        
        await idem_store.store_response(
            idempotency_key=idem_key,
            path="/v1/hr/employees",
            status_code=200,
            headers={},
            body=response_body,
        )
        return response_body

    finally:
        await idem_store.clear_in_flight(idem_key, "/v1/hr/employees")
