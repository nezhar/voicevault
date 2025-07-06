from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()

class LoginRequest(BaseModel):
    token: str

class LoginResponse(BaseModel):
    message: str
    token: str

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Simple token-based login for PoC
    
    In production: Replace with proper JWT authentication
    """
    
    # If no access token is configured, accept any token (development mode)
    if not settings.access_token:
        return LoginResponse(
            message="Authentication disabled (development mode)",
            token=request.token
        )
    
    # Verify the token
    if request.token != settings.access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token"
        )
    
    return LoginResponse(
        message="Login successful",
        token=request.token
    )

@router.post("/verify")
async def verify_token(request: LoginRequest):
    """Verify if a token is valid"""
    
    # If no access token is configured, accept any token
    if not settings.access_token:
        return {"valid": True, "message": "Authentication disabled"}
    
    # Verify the token
    if request.token != settings.access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token"
        )
    
    return {"valid": True, "message": "Token is valid"}