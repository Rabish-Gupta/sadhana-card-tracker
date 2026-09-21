from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutResponse,
    RegistrationRequest,
    RegistrationResponse,
)
from app.schemas.user import UserPublic
from app.services.auth import (
    AccountNotActiveError,
    ConfigurationError,
    DuplicateEmailError,
    InvalidCredentialsError,
    authenticate_user,
    get_user_with_profile,
    register_devotee,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegistrationRequest, session: SessionDep) -> RegistrationResponse:
    try:
        user = await register_devotee(session, payload)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return RegistrationResponse(
        user_id=user.id,
        email=user.email,
        account_status=user.account_status,
        message="Registration submitted. Your account is pending Admin approval.",
    )


@router.post("/login", response_model=AccessTokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> AccessTokenResponse:
    try:
        _, token, expires_in = await authenticate_user(session, payload)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc
    except AccountNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {exc.status.value.lower()}",
        ) from exc

    return AccessTokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout", response_model=LogoutResponse)
async def logout(current_user: CurrentUserDep) -> LogoutResponse:
    # MVP uses stateless short-lived access tokens. Logout is client-side: the frontend
    # discards its token. Server-side token revocation can be added when auth is expanded.
    return LogoutResponse(message="Logged out. Discard the access token on the client.")


@router.get("/me", response_model=UserPublic)
async def me(current_user: CurrentUserDep, session: SessionDep) -> UserPublic:
    user = await get_user_with_profile(session, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublic.model_validate(user)
