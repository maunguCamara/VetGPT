"""
vetgpt/backend/google_auth.py

Google OAuth 2.0 sign-in.

Flow:
  1. Mobile gets Google ID token via expo-auth-session
  2. Mobile sends ID token to POST /api/auth/google
  3. Backend verifies token with Google's public keys
  4. Backend finds or creates user account (no password needed)
  5. Backend returns VetGPT JWT — same format as email/password login

Security:
  - ID token verified with Google's public keys (not just decoded)
  - audience claim checked against your Google Client ID
  - Token expiry checked
  - No Google password ever touches your server

Setup:
  1. Go to console.cloud.google.com
  2. APIs & Services → Credentials → Create OAuth 2.0 Client ID
  3. Application type: iOS (for iOS app)
  4. Application type: Android (for Android app)
  5. Copy Client IDs to .env

  GOOGLE_CLIENT_ID_IOS=your-ios-client-id.apps.googleusercontent.com
  GOOGLE_CLIENT_ID_ANDROID=your-android-client-id.apps.googleusercontent.com
  GOOGLE_CLIENT_ID_WEB=your-web-client-id.apps.googleusercontent.com (optional)
"""

import os
import uuid
import httpx
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import create_access_token, UserOut, Token
from .database import User, SubscriptionTier, get_db

google_auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# Google's token verification endpoint
GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

# Accepted Google client IDs — tokens must be issued for one of these
GOOGLE_CLIENT_IDS = list(filter(None, [
    os.getenv("GOOGLE_CLIENT_ID_IOS",     ""),
    os.getenv("GOOGLE_CLIENT_ID_ANDROID", ""),
    os.getenv("GOOGLE_CLIENT_ID_WEB",     ""),
]))


class GoogleSignInRequest(BaseModel):
    id_token: str    # the ID token from Google Sign-In on the mobile app


@google_auth_router.post("/google", response_model=Token)
async def google_sign_in(
    body: GoogleSignInRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a Google ID token and return a VetGPT JWT.

    The mobile app obtains the Google ID token via expo-auth-session,
    then sends it here. We verify it with Google, extract the user's
    email and profile, and issue a VetGPT session token.
    """
    # ── Step 1: Verify ID token with Google ──────────────────────────────────
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_TOKEN_INFO_URL,
            params={"id_token": body.id_token},
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google ID token. Please sign in again.",
        )

    claims = resp.json()

    # ── Step 2: Validate claims ───────────────────────────────────────────────

    # Check token hasn't expired
    exp = int(claims.get("exp", 0))
    if exp < int(datetime.utcnow().timestamp()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token has expired. Please sign in again.",
        )

    # Check audience matches our app's client IDs
    aud = claims.get("aud", "")
    if GOOGLE_CLIENT_IDS and aud not in GOOGLE_CLIENT_IDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token audience mismatch. Use the official VetGPT app.",
        )

    # Email must be verified by Google
    if claims.get("email_verified") not in (True, "true"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified.",
        )

    email      = claims.get("email", "").lower().strip()
    full_name  = claims.get("name",  "").strip()
    google_sub = claims.get("sub",   "")     # unique Google user ID

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address in Google token.",
        )

    # ── Step 3: Find or create user ───────────────────────────────────────────

    result = await db.execute(select(User).where(User.email == email))
    user   = result.scalar_one_or_none()

    if user is None:
        # New user — create account (no password, Google-authenticated)
        user = User(
            id              = str(uuid.uuid4()),
            email           = email,
            hashed_password = f"google:{google_sub}",  # sentinel — can't be used for password login
            full_name       = full_name or email.split("@")[0],
            is_active       = True,
            is_verified     = True,    # Google already verified the email
            tier            = SubscriptionTier.FREE,
            created_at      = datetime.utcnow(),
        )
        db.add(user)
        await db.flush()
    else:
        # Existing user — update name if it changed, mark as verified
        if full_name and not user.full_name:
            user.full_name  = full_name
        user.is_verified    = True
        user.last_login     = datetime.utcnow()

    # ── Step 4: Issue VetGPT JWT ──────────────────────────────────────────────

    token = create_access_token(user)

    return Token(
        access_token = token,
        user         = UserOut.model_validate(user),
    )
