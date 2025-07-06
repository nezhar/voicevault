# Authentication Setup

VoiceVault includes a simple token-based authentication system for PoC protection. This guide explains how to configure and use the authentication system.

## Overview

The authentication system uses a **global access token** approach:
- Single token controls access to the entire application
- Token is stored securely in localStorage
- All API requests include the token via Bearer authentication
- Simple but effective for PoC and small team deployments

## Configuration

### Development Mode (No Authentication)

For development or testing without authentication:

```bash
# In .env file - leave ACCESS_TOKEN empty
ACCESS_TOKEN=
```

When `ACCESS_TOKEN` is empty, the application allows all requests without authentication.

### Production Mode (With Authentication)

For production deployment with access control:

```bash
# In .env file - set ACCESS_TOKEN to any secure string
ACCESS_TOKEN=your-secure-token-here-make-it-long-and-random
```

**Example secure tokens:**
```bash
ACCESS_TOKEN=VoiceVault2025-prod-token-x8k9m2n4p7q1
ACCESS_TOKEN=hackathon-demo-access-2025-secure-key
ACCESS_TOKEN=enterprise-voice-vault-access-token-2025
```

## Usage

### For Users

1. **Access the application** - Navigate to your VoiceVault URL
2. **Login screen appears** - Enter the access token provided by administrator
3. **Access granted** - Use the application normally
4. **Logout** - Click logout button in header to clear token

### For Administrators

1. **Generate a secure token** - Create a long, random string
2. **Set environment variable** - Add `ACCESS_TOKEN=your-token` to .env
3. **Restart application** - Restart containers to apply changes
4. **Share token** - Provide token to authorized users

## API Endpoints

### Authentication Endpoints

- **POST /api/auth/login** - Login with access token
- **POST /api/auth/verify** - Verify token validity

### Protected Endpoints

All API endpoints under `/api/entries/` require authentication:
- File uploads
- Entry management
- Chat functionality
- Summary generation

## Security Features

### Token Protection
- Tokens are stored in localStorage (client-side)
- All API requests include Bearer token
- Automatic redirect to login on 401 errors
- Token cleared on logout

### API Security
- CORS configured for production
- Bearer token validation on all protected endpoints
- Proper HTTP status codes (401 for unauthorized)
- No token exposure in logs or URLs

## Best Practices

### Token Generation
```bash
# Generate secure random token (Linux/macOS)
openssl rand -hex 32

# Or use a custom format
echo "voicevault-$(date +%Y)-$(openssl rand -hex 16)"
```

### Production Deployment
1. **Use HTTPS** - Always use SSL/TLS in production
2. **Secure token storage** - Keep access tokens in secure environment variables
3. **Regular rotation** - Change tokens periodically
4. **Access control** - Limit token sharing to authorized personnel

### Environment Security
```bash
# ✅ Good - environment variable
ACCESS_TOKEN=secure-token-here

# ❌ Bad - never commit tokens to code
# ACCESS_TOKEN=hardcoded-token
```

## Upgrading to Full Authentication

For production systems beyond PoC, consider upgrading to:

### JWT-based Authentication
- User-specific tokens with expiration
- Role-based access control
- Refresh token mechanism

### Database Authentication
- User accounts with passwords
- Session management
- User roles and permissions

### SSO Integration
- SAML/OAuth integration
- Enterprise directory integration
- Multi-factor authentication

## Implementation Details

### Backend (FastAPI)
```python
# Token verification
from app.core.auth import get_current_user

@router.post("/protected-endpoint")
async def protected_route(
    current_user: bool = Depends(get_current_user)
):
    # Endpoint is now protected
    pass
```

### Frontend (React)
```typescript
// API calls include token automatically
const entries = await entryApi.getEntries();

// Check authentication status
if (!auth.isAuthenticated()) {
    // Redirect to login
}
```

## Troubleshooting

### Common Issues

#### "Authentication required" error
- **Cause**: No token provided or invalid token
- **Solution**: Check if ACCESS_TOKEN is set correctly and restart containers

#### Token not working
- **Cause**: Token mismatch between client and server
- **Solution**: Clear browser localStorage and re-enter correct token

#### Automatic logouts
- **Cause**: Token becomes invalid or server restart with new token
- **Solution**: Re-enter token or check if ACCESS_TOKEN was changed

### Debug Commands

```bash
# Check if authentication is enabled
docker logs voicevault-api | grep "access_token"

# Clear browser storage
# In browser console:
localStorage.removeItem('auth_token')

# Test API with curl
curl -H "Authorization: Bearer your-token" \
  http://localhost:8000/api/entries/
```

## Development vs Production

### Development
- Authentication disabled by default
- Easy testing without token requirements
- Focus on functionality development

### Production
- Authentication enabled with secure token
- Access control for enterprise deployment
- Ready for hackathon demonstration

This simple authentication system provides adequate security for PoC and hackathon scenarios while being easy to set up and manage.