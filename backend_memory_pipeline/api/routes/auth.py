from uuid import uuid4
from datetime import datetime,timezone
from fastapi import APIRouter,HTTPException,status
from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    authenticate_user,
    create_access_token,
    register_user,
    revoke_token
)
from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    LoginRequestV1,
    LoginResponseV1,
    LogoutRequestV1,
    LogoutResponseV1,
    RegisterRequestV1,
    RegisterResponseV1
)
router=APIRouter(
    prefix="/v1/auth",
    tags=["authentication"]
)
TOKEN_EXPIRES_IN_SECONDS=3600
@router.post(
    "/register",
    response_model=RegisterResponseV1,
    responses={
        400:{
            "model":APIErrorResponseV1,
            "description":"Registration failed."
        }
    }
)
def register(request:RegisterRequestV1)->RegisterResponseV1:
    correlation_id=str(uuid4())
    try:
        user=register_user(
            username=request.username,
            password=request.password,
            metadata=request.metadata
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User registration failed."
        ) from exc
    access_token=create_access_token(
        subject_id=user.subject_id,
        username=user.username,
        expires_in_seconds=TOKEN_EXPIRES_IN_SECONDS
    )
    return RegisterResponseV1(
        access_token=access_token,
        token_type="bearer",
        expires_in=TOKEN_EXPIRES_IN_SECONDS,
        subject_id=user.subject_id,
        username=user.username,
        correlation_id=correlation_id
    )
@router.post(
    "/login",
    response_model=LoginResponseV1,
    responses={
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication failed."
        }
    }
)
def login(request:LoginRequestV1)->LoginResponseV1:
    correlation_id=str(uuid4())
    user=authenticate_user(
        username=request.username,
        password=request.password
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    access_token=create_access_token(
        subject_id=user.subject_id,
        username=user.username,
        expires_in_seconds=TOKEN_EXPIRES_IN_SECONDS
    )
    return LoginResponseV1(
        access_token=access_token,
        token_type="bearer",
        expires_in=TOKEN_EXPIRES_IN_SECONDS,
        subject_id=user.subject_id,
        username=user.username,
        correlation_id=correlation_id
    )

@router.post(
    "/logout",
    response_model=LogoutResponseV1,
    responses={
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication required."
        }
    }
)
def logout(request:LogoutRequestV1,current_subject:CurrentSubject)->LogoutResponseV1:
    correlation_id=str(uuid4())
    timestamp=datetime.now(timezone.utc)
    try:
        from backend_memory_pipeline.api.dependencies import revoke_token
        if not current_subject.token_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has no valid token ID.",
                headers={"WWW-Authenticate":"Bearer"}
            )
        revoke_token(current_subject.token_id)
    except HTTPException:
        raise   
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed."
        ) from exc
    return LogoutResponseV1(
        status="accepted",
        subject_id=current_subject.subject_id,
        username=current_subject.username,
        token_revoked=True,
        correlation_id=correlation_id,
        timestamp=timestamp,
        metadata=dict(request.metadata)
    )