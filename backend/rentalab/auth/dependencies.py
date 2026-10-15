from typing import Annotated

from fastapi import Depends, HTTPException, Request

from rentalab.auth.service import SessionIdentity

SESSION_ERROR = "La sesión no es válida o ha caducado"
ROLE_ERROR = "No tienes permisos para realizar esta operación"


def has_admin_role(identity: SessionIdentity) -> bool:
    return identity.active and identity.role == "admin"


def get_current_user(request: Request) -> SessionIdentity:
    identity: SessionIdentity | None = getattr(request.state, "auth_identity", None)
    if identity is None:
        raise HTTPException(status_code=401, detail=SESSION_ERROR)
    return identity


CurrentUser = Annotated[SessionIdentity, Depends(get_current_user)]


def require_admin(identity: CurrentUser) -> SessionIdentity:
    if not has_admin_role(identity):
        raise HTTPException(status_code=403, detail=ROLE_ERROR)
    return identity


AdminUser = Annotated[SessionIdentity, Depends(require_admin)]


def require_customer(identity: CurrentUser) -> SessionIdentity:
    if not identity.active or identity.role != "customer" or identity.user_id is None:
        raise HTTPException(status_code=403, detail=ROLE_ERROR)
    return identity


CustomerUser = Annotated[SessionIdentity, Depends(require_customer)]
