# Authentication Setup

VoiceVault supports three authentication modes, selected with the `AUTH_MODE`
environment variable. This guide documents the **token** mode; for single sign-on
via OpenID Connect (ADFS, Keycloak, Entra ID, …) see **[docs/oidc-setup.md](./oidc-setup.md)**.

## Overview

| Mode    | `AUTH_MODE` | Behavior                                                                 | When to use |
|---------|-------------|--------------------------------------------------------------------------|-------------|
| None    | `none`      | No login. Everything belongs to one shared local user.                   | Local development |
| Token   | `token`     | A single shared `ACCESS_TOKEN` bearer token gates the whole app.         | Small PoC / demo |
| OIDC    | `oidc`      | SSO via an OpenID Connect provider; each user gets their own identity.    | Production / teams — see [docs/oidc-setup.md](./oidc-setup.md) |

If `AUTH_MODE` is left **unset**, it is derived for backward compatibility:
`token` when `ACCESS_TOKEN` is set, otherwise `none`. Existing deployments keep
working with zero configuration changes.


## Personal access tokens

Signed-in users can create personal access tokens from **API tokens** in the
left sidebar. A token is always minted for the signed-in user; administrators
cannot create tokens on someone else's behalf. Active tokens can be renamed and
their expiry changed or removed, but their permissions are fixed for life. The
page lists active tokens by default; the status filter widens it to expired or
revoked ones. Administrators additionally get a **My tokens / All tokens**
switch and a user filter so they can review and revoke any token, paginated.
The secret is shown once, together with a ready-to-run `curl` example;
VoiceVault stores only its SHA-256 hash. Send it using the standard bearer
format:

```http
Authorization: Bearer vvpat_<secret>
```

PATs identify their owning user, so entry ownership and project membership
rules still apply. Each token also needs the permission required by the route:

| Permission | Allows |
|------------|--------|
| `entries:read` | List/read entries, stream audio, and chat |
| `entries:write` | Create, upload, update, archive, delete, move, and summarize entries |
| `projects:read` | List and view projects and access requests |
| `projects:write` | Create/update projects, membership, and access requests |
| `templates:read` | List prompt templates |
| `templates:write` | Create, update, and delete prompt templates |
| `admin:read` | `GET /api/admin/stats` and `GET /api/admin/users`, and only when the owning user is also an admin |

A missing, malformed, unknown, expired, or revoked PAT returns `401`. A valid
PAT without the required permission returns `403`, except on `/api/admin`,
where a non-admin's token receives `404` regardless of its scopes so the admin
area stays undiscoverable. PATs may only call the routes listed above plus
`GET /api/auth/me`; everything else (including every admin mutation and PAT
management itself) requires an interactive browser login. Deactivating a user
invalidates their sessions and revokes all of their PATs in one step, and a
deactivated user's next SSO attempt is refused before it can be recorded as a
login.

`last_used_at` is updated at most every five minutes, and only once the token
itself has been authorized, so a leaked token being probed against routes it
cannot reach does not appear "in use". A request that clears the token gate and
is then refused on the resource - someone else's entry, say - does count: the
caller held a credential that works. The five-minute interval is enforced in the
`UPDATE` itself, so concurrent requests cannot each slip a write past it.

In OIDC mode a bearer header that does not start with `vvpat_` is ignored and
the session cookie is used instead. This lets a browser that still holds a
token-mode credential sign in with SSO; automation sending a wrong credential
without a cookie still gets `401`.

`AUTH_MODE=none` intentionally permits anonymous access, so PAT permissions do
not provide a security boundary in that development mode. Use OIDC or token mode
when the API must be protected.
## Token mode (`AUTH_MODE=token`)

The token mode uses a **global access token** approach:
- Single token controls access to the entire application
- Token is stored in localStorage
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

## MCP access

An optional PAT-authenticated MCP endpoint is available at `/mcp`.
See [MCP setup, tools, and client examples](mcp.md).
