from fastapi import HTTPException, Request, status


def require_operator(request: Request) -> None:
    """Allow operational changes only to operator-level accounts."""
    if request.state.user.role == "VIEWER":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator permission required")
