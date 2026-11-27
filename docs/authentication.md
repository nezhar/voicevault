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


## Capabilities, groups and content access

Two questions decide every request:

1. **Reach** - can the user get at this content at all? Their own entries, and
   entries in projects they are a member of: directly, or through a group the
   project is shared with. Viewers read, editors also edit and add entries,
   owners also manage the project. Anything else answers `404`.
2. **Capability** - may the user use this feature here? A capability is granted
   globally or, for project-scoped ones, in single projects. Missing it answers
   `403` with a message naming the capability, e.g.
   `Missing capability entries.chat (Chat) in project "Sales"`.

A capability never makes content visible: granting `entries.view` in a project
does not let anyone see it who is not a member.

| Capability | Area | Per project | Unlocks |
|---|---|---|---|
| `entries.view` | Entries | yes | List and open entries: transcript, summary, audio; upload status |
| `entries.upload` | Entries | yes | File upload, also through upload links |
| `entries.import_url` | Entries | yes | `POST /api/entries/url` |
| `entries.import_transcript` | Entries | yes | `POST /api/entries/transcript` |
| `entries.edit` | Entries | yes | Metadata, status, archive; moving needs it in the source and the target |
| `entries.delete` | Entries | yes | Permanently delete own entries |
| `entries.export` | Entries | yes | SRT download |
| `entries.chat` | AI | yes | Chat with a transcript |
| `entries.summarize` | AI | yes | Generate and save summaries |
| `projects.create` | Projects | no | Create projects |
| `projects.manage` | Projects | yes | Settings, members, group shares, access requests (the owner role is still required) |
| `templates.use` | Templates | no | List prompt templates and use them in chat |
| `templates.manage` | Templates | no | Create, edit, delete prompt templates |
| `tokens.create` | Integrations | no | Create personal access tokens |
| `mcp.connect` | Integrations | no | Use `/mcp` and approve OAuth sign-ins of MCP clients |
| `admin.view` | Admin | no | Admin statistics, users, groups and permissions (read) |
| `admin.manage` | Admin | no | Activate users, manage groups, grants and every user's tokens |

`GET /api/capabilities` returns this catalog with the routes and MCP tools each
capability unlocks; `GET /api/auth/me` reports the caller's `capabilities` and,
per project, the `project_capabilities` that hold there in addition.

**Grants only add.** A user holds the union of their own grants, the grants of
every group they belong to, and those of the built-in **Everyone** group, which
contains every user. There are no deny rules: to restrict something, narrow
Everyone and grant more to the users or groups that need it. On first start
Everyone receives every capability except `admin.*` and `templates.manage`, so
nothing changes for existing installations until an admin narrows it.

**Admins** - `ADMIN_EMAILS` in OIDC mode, the shared local user in `none` and
`token` mode - hold every capability whatever the grants say, so a
misconfiguration cannot lock them out. Anyone else can be given `admin.view`
and/or `admin.manage`.

**Groups** are managed under **Admin -> Groups**. A group can be linked to an
IdP group (`OIDC_CLAIM_GROUPS`, see [oidc-setup.md](./oidc-setup.md)); its
IdP members are then reconciled with the claim at every sign-in. An admin can
also add members by hand; the two kinds never touch each other. **Admin ->
Permissions** shows the capability matrix of a user or group, with a column per
project, and for users which grants they inherit and from where.

**Sharing a project with a group**: in project settings an owner (with
`projects.manage`) adds a group as viewer or editor. Owners are always added in
person, so an IdP group change can never leave a project without an owner. A
user's role is the highest of their direct and group memberships; someone whose
access comes only from a group cannot leave the project themselves, and an
access request is refused while a group already gives access. Sharing with
Everyone makes a project visible to every user.

## Personal access tokens

Signed-in users with `tokens.create` can create personal access tokens from
**API tokens** in the left sidebar. A token is always minted for the signed-in
user; administrators cannot create tokens on someone else's behalf. Active
tokens can be renamed and their expiry changed or removed, but their
capabilities and projects are fixed for life. The page lists active tokens by
default; the status filter widens it to expired or revoked ones. Users with
`admin.view` additionally get a **My tokens / All tokens** switch and a user
filter so they can review tokens; revoking another user's token needs
`admin.manage`. The secret is shown once, together with a ready-to-run `curl`
example; VoiceVault stores only its SHA-256 hash. Send it using the standard
bearer format:

```http
Authorization: Bearer vvpat_<secret>
```

A token carries capabilities from the table above - only ones its owner holds -
and can be limited to some projects (`project_ids`; a limited token cannot
reach the owner's private entries). On every request it is cut down to what
its owner holds **now**: taking a capability from a user, or from their group,
takes it from their tokens on the next request. Entry ownership and project
membership rules apply as for the owner.

`POST /api/auth/pats` still accepts the scope names from before capabilities
existed, and tokens created with them were converted on upgrade:

| Old scope | Capabilities |
|---|---|
| `entries:read` | `entries.view`, `entries.chat`, `entries.export` |
| `entries:write` | `entries.upload`, `entries.import_url`, `entries.import_transcript`, `entries.edit`, `entries.delete`, `entries.summarize` |
| `projects:read` | none needed: listing and reading own projects is open to every token |
| `projects:write` | `projects.create`, `projects.manage` |
| `templates:read` | `templates.use` |
| `templates:write` | `templates.manage` |
| `admin:read` | `admin.view` |

A converted token also gains `mcp.connect`, since every token could use `/mcp`
before.

Tokens issued to MCP clients through OAuth sign-in (see [mcp.md](mcp.md)) are
ordinary tokens with `source: "oauth"`; they are listed, limited and revoked
the same way.

A missing, malformed, unknown, expired, or revoked PAT returns `401`. A valid
PAT without the required capability returns `403`, except on `/api/admin`,
where a token whose owner may not see the admin area receives `404` so the area
stays undiscoverable. Every route is listed in `ROUTE_POLICY`
(`api/app/core/capabilities.py`); routes marked interactive - PAT management,
every admin mutation, group and grant management, OAuth approvals - and any
route missing from it require an interactive browser login. Deactivating a user
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

`AUTH_MODE=none` intentionally permits anonymous access as the shared local
user, who is the admin, so capabilities do not provide a security boundary in
that development mode. Use OIDC or token mode
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

An optional token-authenticated MCP endpoint is available at `/mcp`; clients
can sign in with OAuth or use a pasted token. See
[MCP setup, tools, and client examples](mcp.md).
