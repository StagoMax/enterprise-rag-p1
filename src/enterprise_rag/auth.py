import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from enterprise_rag.config import Settings
from enterprise_rag.models import ROLE_PATTERN, Principal, TokenRequest

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(request: TokenRequest, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.jwt_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": request.subject,
        "roles": sorted(request.roles),
        "tenant_id": request.tenant_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, int(ttl.total_seconds())


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    settings: Settings = request.app.state.settings
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        ) from exc

    roles = payload.get("roles")
    subject = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    claims_are_valid = (
        isinstance(subject, str)
        and bool(subject)
        and isinstance(roles, list)
        and bool(roles)
        and all(
            isinstance(role, str) and re.fullmatch(ROLE_PATTERN, role) is not None
            for role in roles
        )
        and isinstance(tenant_id, str)
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", tenant_id) is not None
    )
    if not claims_are_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token claims")

    return Principal(
        subject=subject,
        roles=frozenset(roles),
        tenant_id=tenant_id,
    )


PrincipalDependency = Annotated[Principal, Depends(get_principal)]
