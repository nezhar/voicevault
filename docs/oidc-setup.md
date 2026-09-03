# OIDC / SSO Setup

VoiceVault supports single sign-on through any standard **OpenID Connect (OIDC)**
provider — Active Directory Federation Services (ADFS), Keycloak, Microsoft Entra
ID, Okta, Auth0, and others. The integration is generic and configured entirely
through environment variables; nothing in the codebase is specific to one vendor.

## Overview

VoiceVault has three authentication modes, selected with `AUTH_MODE`:

| Mode    | `AUTH_MODE` | Behavior                                                                 | When to use |
|---------|-------------|--------------------------------------------------------------------------|-------------|
| None    | `none`      | No login. Everything belongs to one shared local user.                   | Local development |
| Token   | `token`     | A single shared `ACCESS_TOKEN` bearer token gates the whole app.         | Small PoC / demo |
| OIDC    | `oidc`      | SSO via an OpenID Connect provider; each user gets their own identity.   | Production / teams |

If `AUTH_MODE` is left **unset**, it is derived for backward compatibility:
`token` when `ACCESS_TOKEN` is set, otherwise `none`. Existing deployments keep
working with zero configuration changes.

**Scope note:** entries and projects are per-user in OIDC mode, but **prompt
templates remain one global collection** — every authenticated user can list,
edit, and delete them. Treat them as org-wide configuration, not personal data.

### The login flow (Backend-for-Frontend)

VoiceVault uses the **Authorization Code flow with PKCE**, driven entirely by the
backend (a Backend-for-Frontend, or BFF, pattern). The browser never sees tokens;
it only ever holds an opaque, `HttpOnly` session cookie. This sidesteps the CORS
restrictions many IdPs (ADFS in particular) place on their token endpoint.

```
Browser                    VoiceVault API                 IdP (ADFS/Keycloak/…)
   │  GET /api/auth/oidc/login  │                                │
   │───────────────────────────▶│  redirect (state + PKCE)       │
   │◀───────────────────────────┤────────────────────────────────▶ /authorize
   │        user authenticates at the IdP …                       │
   │  GET /api/auth/oidc/callback?code=…                          │
   │───────────────────────────▶│  code + verifier → /token       │
   │                            │◀───────────────────────────────┤ id_token
   │                            │  provision user, create session │
   │◀───── Set-Cookie: voicevault_session (HttpOnly) ── redirect / │
```

On success the callback:
1. Exchanges the code for an ID token (PKCE-protected).
2. Maps the token claims to an identity (see the claim mapping below).
3. Finds-or-creates the user, keyed on `(issuer, subject)` — never on email.
4. Creates a server-side session row (stored as a SHA-256 hash of the opaque
   token, so a leaked database cannot be replayed as cookies) and sets the
   `voicevault_session` cookie (`HttpOnly`, `SameSite=Lax`, `Secure` when
   `SESSION_COOKIE_SECURE=true`).

### Environment variables

```bash
AUTH_MODE=oidc

OIDC_DISCOVERY_URL=            # https://<host>/.well-known/openid-configuration
OIDC_CLIENT_ID=voicevault
OIDC_CLIENT_SECRET=
OIDC_SCOPES=openid profile email
OIDC_CLAIM_SUBJECT=sub         # stable, unique subject claim; ADFS: employeeID
OIDC_CLAIM_EMAIL=email         # ADFS: upn
OIDC_CLAIM_NAME=name           # fallback when the given/family claims are absent
OIDC_CLAIM_GIVEN_NAME=given_name   # ADFS: firstname
OIDC_CLAIM_FAMILY_NAME=family_name # ADFS: lastname
PUBLIC_BASE_URL=               # e.g. https://voicevault.example.com
INITIAL_OWNER_EMAIL=           # optional: legacy-data takeover (see below)

SESSION_SECRET=                # openssl rand -hex 32
SESSION_LIFETIME_HOURS=12
SESSION_COOKIE_SECURE=true     # false only for local HTTP dev
CORS_ORIGINS=http://localhost:3000
```

The redirect URI you register at the IdP is always
`<PUBLIC_BASE_URL>/api/auth/oidc/callback`.

The display name is composed from the given/family name claims when either is
present; `OIDC_CLAIM_NAME` is only read when both parts are absent (a user with
no name claims at all falls back to their email address). The parts win on
purpose: ADFS often emits a domain login such as `ANEXIA\alice` as its combined
name claim, which is not a display name.

## ADFS walkthrough (Windows Server 2016+)

1. **Create an Application Group.** In *Server Manager → AD FS Management →
   Application Groups → Add Application Group*, choose the template
   **"Server application accessing a web API"**. Name it `VoiceVault`.
2. **Server application.** Note the generated **Client Identifier** — this is your
   `OIDC_CLIENT_ID`. Add the redirect URI
   `https://<PUBLIC_BASE_URL>/api/auth/oidc/callback`.
3. **Client secret.** Tick *Generate a shared secret* and copy it into
   `OIDC_CLIENT_SECRET`.
4. **Web API.** Set the identifier to the same client id. Under *Access control
   policy* pick a policy (e.g. *Permit everyone*, or restrict to a group).
5. **Permitted scopes.** Enable `openid`, `email`, and `profile`.
6. **Issuance transform rules.** Add rules that emit the claims VoiceVault reads:
   - LDAP attribute **Employee-ID → employeeID** (`employeeID`)
   - LDAP attribute **User-Principal-Name → UPN** (`upn`)
   - LDAP attribute **Given-Name → firstname** (`firstname`)
   - LDAP attribute **Surname → lastname** (`lastname`)

   If the UPN domain is not the email address users expect, emit LDAP attribute
   **E-Mail-Addresses → email** instead and set `OIDC_CLAIM_EMAIL=email`.

   Prefer `employeeID` over ADFS's built-in `sub` as the subject: ADFS derives
   `sub` per client from an anchor claim (typically the UPN), so it does not
   survive UPN or domain migrations — `employeeID` stays stable across email
   and name changes. Users are keyed by the subject, so a changed subject
   looks like a brand-new user and orphans the old account's data.
7. **VoiceVault configuration:**

   ```bash
   AUTH_MODE=oidc
   OIDC_DISCOVERY_URL=https://<fs-host>/adfs/.well-known/openid-configuration
   OIDC_CLIENT_ID=<client id from step 2>
   OIDC_CLIENT_SECRET=<secret from step 3>
   OIDC_CLAIM_SUBJECT=employeeID
   OIDC_CLAIM_EMAIL=upn
   OIDC_CLAIM_GIVEN_NAME=firstname
   OIDC_CLAIM_FAMILY_NAME=lastname
   PUBLIC_BASE_URL=https://voicevault.example.com
   SESSION_SECRET=<openssl rand -hex 32>
   SESSION_COOKIE_SECURE=true
   ```

ADFS exposes discovery under the `/adfs/` path, so the discovery URL includes it.
ADFS does not send CORS headers on its token endpoint — the BFF flow above means
that never matters, because the browser never calls the token endpoint directly.

## Keycloak walkthrough (local development)

A ready-to-run Keycloak is bundled for local testing. No hosts-file tricks are
needed: the bundled config pins Keycloak's browser-facing URLs (issuer,
authorization endpoint) to `http://localhost:8080` via `KC_HOSTNAME`, while
`KC_HOSTNAME_BACKCHANNEL_DYNAMIC` lets the API reach the token endpoint through
the compose-internal name `http://keycloak:8080`.

1. **Start it alongside VoiceVault:**

   ```bash
   docker compose -f compose.yml -f compose.oidc.yml up --build
   ```

   `--build` is needed once so the API image picks up the `authlib` dependency.
   The `voicevault` realm is imported automatically from
   `dev/keycloak-realm.json`, including a confidential client `voicevault`
   (secret `dev-secret`) and a test user **alice@example.com** / password **alice**.

2. **Configure VoiceVault (`.env`):** if your `.env` started as a copy of
   `.env.local.example`, all of this is already pre-filled — just set
   `AUTH_MODE=oidc`.

   ```bash
   AUTH_MODE=oidc
   OIDC_DISCOVERY_URL=http://keycloak:8080/realms/voicevault/.well-known/openid-configuration
   OIDC_CLIENT_ID=voicevault
   OIDC_CLIENT_SECRET=dev-secret
   OIDC_CLAIM_SUBJECT=sub
   OIDC_CLAIM_EMAIL=email
   OIDC_CLAIM_NAME=name
   PUBLIC_BASE_URL=http://localhost:3000
   SESSION_SECRET=<openssl rand -hex 32>
   SESSION_COOKIE_SECURE=false
   CORS_ORIGINS=http://localhost:3000
   ```

   `SESSION_COOKIE_SECURE=false` is required because local dev runs over plain
   HTTP. `SameSite=Lax` ignores the port, so the cookie set for `localhost:3000`
   is sent to the API on `localhost:8000`.

3. Open http://localhost:3000, click **Sign in with SSO**, log in as
   `alice@example.com` / `alice`.

4. **More test users** (for trying out Projects sharing): open the Keycloak
   admin console at http://localhost:8080 (admin / admin), switch to the
   `voicevault` realm, and add users under *Users → Add user* (set an email,
   mark it verified, and set a password under *Credentials*). Users added this
   way vanish on `docker compose down` (see below) — for test users that
   should stick around, edit `dev/keycloak-realm.json` instead: copy alice's
   entry in the `users` array and give it a unique fixed `id`, so the user
   (and its OIDC subject) survives realm re-imports.

### Smoke test: sharing between two users

A quick manual walkthrough that covers login, Projects, and role gating:

1. Log in as `alice@example.com` / `alice` — the header shows the display name
   and a Logout button.
2. Create a project via the sidebar's *New Project*, then add an entry with the
   project selected in the add dialog (or create it private and move it later
   via the card's *Move to project* button — the folder icon in the action
   rail). The entry card shows a project badge.
3. Create a second user in the Keycloak admin console (step 4 above), then log
   in as that user once **in a private browser window** — members can only be
   added after their first login, because that is when the user is provisioned.
4. As Alice, open the project's settings (gear icon in the sidebar) and add the
   second user by email as **viewer**: in their window they see the shared
   entry but get no edit/archive/delete buttons. Change their role to
   **editor** and the edit/archive buttons appear — delete stays reserved for
   the entry owner.
5. Worth poking at: cancel the login at the Keycloak screen (you land back on
   the login page with a friendly message and only `auth_error=<code>` in the
   URL); try removing yourself as the last owner in the project settings
   (blocked with an error); log out and back in.

Two things to know when testing against an existing local database:

- **Entries created before the switch to OIDC are invisible in `oidc` mode** —
  they are unowned rows, and OIDC users only see their own or shared content.
  They reappear when you set `AUTH_MODE=` back (startup assigns them to the
  shared local user), or you can set `INITIAL_OWNER_EMAIL` **before the first
  login** to permanently hand them to that user (see below).
- Keycloak runs without a persistent volume: `docker compose down` removes
  users you added by hand (the realm re-imports fresh on the next start), while
  `stop`/`start` keeps them. Re-creating a removed user gives it a **new
  subject**, so its next login fails with `provisioning_failed` until you
  reconcile the old user row (see Troubleshooting). The bundled
  **alice@example.com** is immune: her id is pinned in `dev/keycloak-realm.json`,
  so her subject survives re-imports — the same trick works for any test user
  you add to that file (step 4 above).

## Legacy data takeover (`INITIAL_OWNER_EMAIL`)

When you switch an existing deployment to `oidc`, all previously created entries
have no OIDC owner (they belonged to the shared system user or predate ownership
entirely). Set `INITIAL_OWNER_EMAIL` to the email of the administrator who should
inherit them:

- On that user's **first login**, all ownerless entries and all entries owned by
  the system user are reassigned to them.
- The operation is **idempotent** — after the first takeover there is nothing left
  to match, so subsequent logins do nothing.
- If `INITIAL_OWNER_EMAIL` is left empty, pre-existing entries stay invisible until
  you set it (the API logs a warning on startup).

## Project permalinks and access requests

Every project has a permanent URL at `/projects/{project_id}`; the copy-link
button on the sidebar row — and in **Project Settings** — puts it on the
clipboard.

Anyone signed in who opens that URL sees the project name and its owners, even
without membership. A project UUID is unguessable, and that disclosure is the
point of a shareable link; description, member count, and entries stay hidden.
A non-member can send an access request with an optional note.

Owners review requests in **Project Settings → Access requests**, with a count
badge on the project in the sidebar, and approve each one with a role (Viewer by
default) or deny it. Approving is the only path from a request to membership,
and the role is always the owner's choice.

A denied user may request again. The request reuses the same row, so an owner's
list never fills up with repeats from one person.

Requests are an OIDC-mode feature. In `none` and `token` mode every request
endpoint returns 404, because those modes share a single local user for whom
requesting access would be meaningless. Permalinks themselves work in all modes.

Someone who opens a permalink while signed out is sent through the IdP and
returns to the project page afterwards, not to the dashboard.

## Troubleshooting

If the callback fails, VoiceVault redirects to `/?auth_error=<code>` rather than
leaking claim values or stack traces into the URL. The login screen renders a
friendly message for each code:

| `auth_error`            | Cause                                                             | Fix |
|-------------------------|-------------------------------------------------------------------|-----|
| `idp_error`             | The IdP returned an error (e.g. `access_denied`, misconfig).      | Check the app registration, scopes, and access-control policy. |
| `invalid_state`         | The handshake state expired or did not match (CSRF protection).   | Retry the login; ensure `SESSION_SECRET` is set and stable. |
| `token_exchange_failed` | The token endpoint was unreachable or rejected the code.          | Check network reachability, `OIDC_CLIENT_SECRET`, and clock skew. `OIDC_DISCOVERY_URL` must be reachable **from inside the API container** — `localhost` there is the container itself; use the compose service name (e.g. `http://keycloak:8080/...`). |
| `missing_claim`         | A required claim (`iss`, subject, or email) was absent.           | Fix the `OIDC_CLAIM_*` mapping / issuance transform rules. |
| `provisioning_failed`   | Creating the user collided with an existing one — usually the IdP account was re-created (new subject, same email). | Reconcile in the database: update the old user row's `issuer`/`subject` to the new values, or free up the email. |

**Cookie is never set / you are bounced back to login:**
- `SESSION_COOKIE_SECURE=true` on a plain-HTTP host — the browser drops the
  cookie. Set it to `false` for local HTTP.
- `CORS_ORIGINS` does not include the UI origin — cross-origin requests with
  credentials are blocked. Add the exact scheme+host+port.
- `PUBLIC_BASE_URL` does not match the redirect URI registered at the IdP — the
  IdP rejects the callback. They must be identical.
