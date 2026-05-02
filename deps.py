from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from config import get_settings

bearer = HTTPBearer()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=["HS256"]
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise ValueError()
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return user_id
