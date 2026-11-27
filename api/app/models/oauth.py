import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.timeutils import utcnow
from app.db.database import Base


class OAuthClient(Base):
    """An MCP client that registered itself (RFC 7591).

    client_info is the full registration as the MCP SDK returns it. It holds
    the client secret as issued, because the SDK compares it verbatim; PKCE and
    the redirect allow-list are what protect the flow, and a client secret on
    its own grants nothing.
    """

    __tablename__ = "oauth_clients"

    client_id = Column(String(64), primary_key=True)
    client_name = Column(String(255), nullable=True)
    client_info = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class OAuthAuthorizationRequest(Base):
    """One sign-in: pending until a user decides, then (when approved) the
    single-use authorization code the client trades for a token."""

    __tablename__ = "oauth_authorization_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(
        String(64),
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )
    redirect_uri = Column(Text, nullable=False)
    redirect_uri_provided_explicitly = Column(Boolean, nullable=False, default=True)
    code_challenge = Column(String(128), nullable=False)
    state = Column(Text, nullable=True)
    scopes = Column(JSON, nullable=True)  # requested by the client
    resource = Column(Text, nullable=True)
    status = Column(
        String(16),
        nullable=False,
        default="pending",
    )  # pending|approved|denied
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    # Set on approval.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    capabilities = Column(JSON, nullable=True)
    project_ids = Column(JSON, nullable=True)
    code_hash = Column(String(64), nullable=True, unique=True)
    code_expires_at = Column(DateTime, nullable=True)
    code_used_at = Column(DateTime, nullable=True)
