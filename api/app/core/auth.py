from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verify the bearer token against the global access token
    
    For PoC: Simple token-based authentication using a global token
    In production: Replace with proper JWT or session-based auth
    """
    from loguru import logger
    
    # Debug logging
    logger.info(f"Auth check - ACCESS_TOKEN configured: {bool(settings.access_token)}")
    if settings.access_token:
        logger.info(f"Expected token: {settings.access_token[:10]}..." if len(settings.access_token) > 10 else f"Expected token: {settings.access_token}")
    
    # If no access token is configured, allow all requests (development mode)
    if not settings.access_token:
        logger.info("Development mode: Authentication disabled")
        return True
    
    # If no credentials provided, deny access
    if not credentials:
        logger.warning("No credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Received token: {credentials.credentials[:10]}..." if len(credentials.credentials) > 10 else f"Received token: {credentials.credentials}")
    
    # Verify the token
    if credentials.credentials != settings.access_token:
        logger.warning(f"Token mismatch - received: {credentials.credentials[:10]}..., expected: {settings.access_token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info("Authentication successful")
    return True

# Optional dependency for protected endpoints
def get_current_user(authorized: bool = Security(verify_token)):
    """
    Dependency that ensures user is authenticated
    Returns True if authenticated (for PoC simplicity)
    """
    return authorized