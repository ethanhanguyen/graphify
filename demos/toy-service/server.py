from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from auth import create_token, validate_token
from handlers import authenticate, create_user, get_user

app = FastAPI(title="Toy Auth Service")


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


def _require_auth(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth_header[7:]
    payload = validate_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@app.post("/login")
def login(req: LoginRequest):
    result = authenticate(req.email, req.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@app.post("/register")
def register(req: RegisterRequest):
    return create_user(req.name, req.email, req.password)


@app.get("/me")
def me(request: Request):
    payload = _require_auth(request)
    return get_user(payload["sub"], token=_extract_token(request))


def _extract_token(request: Request) -> str:
    return request.headers.get("Authorization", "")[7:]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
