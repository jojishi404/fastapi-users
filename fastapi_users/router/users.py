from typing import Any, Callable, Dict, Optional, Type

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import UUID4

from fastapi_users import models
from fastapi_users.authentication import Authenticator
from fastapi_users.manager import (
    InvalidPasswordException,
    UserAlreadyExists,
    UserManager,
    UserManagerDependency,
    UserNotExists,
)
from fastapi_users.router.common import ErrorCode, run_handler


def get_users_router(
    get_user_manager: UserManagerDependency[models.UD],
    user_model: Type[models.BaseUser],
    user_update_model: Type[models.BaseUserUpdate],
    user_db_model: Type[models.BaseUserDB],
    authenticator: Authenticator,
    after_update: Optional[Callable[[models.UD, Dict[str, Any], Request], None]] = None,
    requires_verification: bool = False,
) -> APIRouter:
    """Generate a router with the authentication routes."""
    router = APIRouter()

    get_current_active_user = authenticator.current_user(
        active=True, verified=requires_verification
    )
    get_current_superuser = authenticator.current_user(
        active=True, verified=requires_verification, superuser=True
    )

    async def get_user_or_404(
        id: UUID4, user_manager: UserManager[models.UD] = Depends(get_user_manager)
    ) -> models.BaseUserDB:
        try:
            return await user_manager.get(id)
        except UserNotExists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @router.get("/me", response_model=user_model)
    async def me(
        user: user_db_model = Depends(get_current_active_user),  # type: ignore
    ):
        return user

    @router.patch(
        "/me",
        response_model=user_model,
        dependencies=[Depends(get_current_active_user)],
    )
    async def update_me(
        request: Request,
        user_update: user_update_model,  # type: ignore
        user: user_db_model = Depends(get_current_active_user),  # type: ignore
        user_manager: UserManager[models.UD] = Depends(get_user_manager),
    ):
        try:
            updated_user = await user_manager.update(user_update, user, safe=True)
            if after_update:
                await run_handler(
                    after_update,
                    updated_user,
                    user_update.create_update_dict(),  # type: ignore
                    request,
                )
            return updated_user
        except InvalidPasswordException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ErrorCode.UPDATE_USER_INVALID_PASSWORD,
                    "reason": e.reason,
                },
            )
        except UserAlreadyExists:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS,
            )

    @router.get(
        "/{id:uuid}",
        response_model=user_model,
        dependencies=[Depends(get_current_superuser)],
    )
    async def get_user(user=Depends(get_user_or_404)):
        return user

    @router.patch(
        "/{id:uuid}",
        response_model=user_model,
        dependencies=[Depends(get_current_superuser)],
    )
    async def update_user(
        user_update: user_update_model,  # type: ignore
        request: Request,
        user=Depends(get_user_or_404),
        user_manager: UserManager[models.UD] = Depends(get_user_manager),
    ):
        try:
            updated_user = await user_manager.update(user_update, user, safe=False)
            if after_update:
                await run_handler(
                    after_update,
                    updated_user,
                    user_update.create_update_dict_superuser(),  # type: ignore
                    request,
                )
            return updated_user
        except InvalidPasswordException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ErrorCode.UPDATE_USER_INVALID_PASSWORD,
                    "reason": e.reason,
                },
            )
        except UserAlreadyExists:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS,
            )

    @router.delete(
        "/{id:uuid}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
        dependencies=[Depends(get_current_superuser)],
    )
    async def delete_user(
        user=Depends(get_user_or_404),
        user_manager: UserManager[models.UD] = Depends(get_user_manager),
    ):
        await user_manager.delete(user)
        return None

    return router
