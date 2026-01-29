"""
Supabase authentication with email whitelist for MCP server.
"""
import os
import jwt
import httpx
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user."""
    email: str
    user_id: str
    token: str


class EmailWhitelistAuth:
    """
    Supabase JWT authentication with email whitelist.

    Validates JWTs issued by Supabase and checks if the user's email
    is in the allowed list.
    """

    def __init__(
        self,
        supabase_url: str,
        allowed_emails: List[str],
        supabase_jwt_secret: Optional[str] = None,
    ):
        """
        Initialize the authenticator.

        Args:
            supabase_url: Your Supabase project URL (e.g., https://xyz.supabase.co)
            allowed_emails: List of email addresses allowed to access the server
            supabase_jwt_secret: JWT secret for HS256 verification (optional, uses JWKS if not provided)
        """
        self.supabase_url = supabase_url.rstrip("/")
        self.allowed_emails = [email.lower().strip() for email in allowed_emails]
        self.jwt_secret = supabase_jwt_secret
        self._jwks_client = None

    def _get_jwks_client(self):
        """Get or create JWKS client for RS256 verification."""
        if self._jwks_client is None:
            jwks_url = f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
            self._jwks_client = jwt.PyJWKClient(jwks_url)
        return self._jwks_client

    def verify_token(self, token: str) -> Optional[AuthenticatedUser]:
        """
        Verify a Supabase JWT and check email whitelist.

        Args:
            token: The JWT bearer token

        Returns:
            AuthenticatedUser if valid and email is whitelisted, None otherwise
        """
        try:
            # Try to decode the token
            if self.jwt_secret:
                # Use HS256 with secret
                payload = jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated",
                )
            else:
                # Use RS256 with JWKS
                jwks_client = self._get_jwks_client()
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience="authenticated",
                )

            # Extract email from token
            email = payload.get("email", "").lower()
            user_id = payload.get("sub", "")

            if not email:
                print(f"AUTH: No email in token")
                return None

            # Check email whitelist
            if email not in self.allowed_emails:
                print(f"AUTH: Email {email} not in whitelist")
                return None

            print(f"AUTH: User {email} authenticated successfully")
            return AuthenticatedUser(email=email, user_id=user_id, token=token)

        except jwt.ExpiredSignatureError:
            print("AUTH: Token expired")
            return None
        except jwt.InvalidTokenError as e:
            print(f"AUTH: Invalid token - {e}")
            return None
        except Exception as e:
            print(f"AUTH: Error verifying token - {e}")
            return None


def get_auth_from_env() -> Optional[EmailWhitelistAuth]:
    """
    Create an EmailWhitelistAuth instance from environment variables.

    Required env vars:
        SUPABASE_URL: Your Supabase project URL
        ALLOWED_EMAILS: Comma-separated list of allowed email addresses

    Optional env vars:
        SUPABASE_JWT_SECRET: JWT secret for HS256 (uses JWKS/RS256 if not set)

    Returns:
        EmailWhitelistAuth instance if configured, None if auth is disabled
    """
    supabase_url = os.getenv("SUPABASE_URL")
    allowed_emails_str = os.getenv("ALLOWED_EMAILS", "")
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")

    if not supabase_url or not allowed_emails_str:
        print("AUTH: Supabase auth not configured (SUPABASE_URL or ALLOWED_EMAILS missing)")
        return None

    allowed_emails = [e.strip() for e in allowed_emails_str.split(",") if e.strip()]

    if not allowed_emails:
        print("AUTH: No allowed emails configured")
        return None

    print(f"AUTH: Configured with {len(allowed_emails)} allowed email(s)")
    return EmailWhitelistAuth(
        supabase_url=supabase_url,
        allowed_emails=allowed_emails,
        supabase_jwt_secret=jwt_secret,
    )
