"""
Onboarding Service REST API Router.

Exposes endpoints for managing onboarding plans.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.onboarding_service.application.use_cases import CreateOnboardingPlanUseCase
from shared.auth import get_current_user, TokenClaims, require_roles
from shared.idempotency import get_idempotency_key, IdempotencyStore, require_idempotency_key
from shared.unit_of_work import get_uow, UnitOfWork

router = APIRouter(prefix="/v1/onboarding", tags=["Onboarding"])

class CreatePlanRequest(BaseModel):
    employee_id: str
    department_id: str

class PlanResponse(BaseModel):
    plan_id: str
    status: str = "created"


@router.post("/plans", response_model=PlanResponse)
async def create_plan(
    req: CreatePlanRequest,
    user: TokenClaims = Depends(require_roles("hr_admin", "system")),
    idem_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_uow),
) -> Any:
    """
    Create a new onboarding plan for an employee.
    Protected by Auth, Roles, and Idempotency.
    """
    idem_store = IdempotencyStore(user.tenant_id)
    
    cached_resp = await idem_store.get_stored_response(idem_key, "/v1/onboarding/plans")
    if cached_resp:
        return cached_resp["body"]

    acquired = await idem_store.mark_in_flight(idem_key, "/v1/onboarding/plans")
    if not acquired:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Request already in progress")

    try:
        use_case = CreateOnboardingPlanUseCase(uow)
        plan_id = await use_case.execute(
            tenant_id=user.tenant_id,
            employee_id=req.employee_id,
            department_id=req.department_id,
        )
        
        response_body = PlanResponse(plan_id=plan_id).model_dump()
        
        await idem_store.store_response(
            idempotency_key=idem_key,
            path="/v1/onboarding/plans",
            status_code=200,
            headers={},
            body=response_body,
        )
        return response_body

    finally:
        await idem_store.clear_in_flight(idem_key, "/v1/onboarding/plans")
