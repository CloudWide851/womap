from fastapi import APIRouter

from app.features.auth.schemas import AuthPolicyResponse, LoginRequest, LoginResponse
from app.features.auth.service import AuthService


router = APIRouter()
service = AuthService()


@router.get("/policy", response_model=AuthPolicyResponse)
async def get_auth_policy() -> AuthPolicyResponse:
    return service.get_policy()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    return service.login(payload)
