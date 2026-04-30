#!/usr/bin/env python3
"""
vetgpt/bots/create_bot_user.py

Creates a dedicated bot user account and prints the JWT token
to add as BOT_API_KEY in .env

Run once after the API is running:
    python bots/create_bot_user.py --url https://api.vetgpt.app
"""

import sys
import json
import argparse
import urllib.request
import urllib.error

def post(url: str, data: dict, token: str = "") -> dict:
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def put(url: str, data: dict, token: str) -> dict:
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Create VetGPT bot user")
    parser.add_argument("--url",      default="http://localhost:8000", help="API base URL")
    parser.add_argument("--email",    default="bot@vetgpt.app",        help="Bot email")
    parser.add_argument("--password", default=None,                    help="Bot password (auto-generated if omitted)")
    parser.add_argument("--admin-token", default=None,                 help="Admin JWT to upgrade bot to clinic tier")
    args = parser.parse_args()

    import secrets
    password = args.password or secrets.token_urlsafe(24)

    print(f"\n🤖 Creating bot user: {args.email}")
    print(f"   API: {args.url}")

    # Register
    try:
        data = post(f"{args.url}/api/auth/register", {
            "email":     args.email,
            "password":  password,
            "full_name": "VetGPT Bot",
        })
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        if "already registered" in str(body.get("detail", "")):
            print("   ℹ️  User already exists — logging in...")
            # Login instead
            import urllib.parse
            form = urllib.parse.urlencode({"username": args.email, "password": password}).encode()
            req  = urllib.request.Request(
                f"{args.url}/api/auth/login", data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
        else:
            print(f"   ❌ Registration failed: {body}")
            sys.exit(1)

    token   = data["access_token"]
    user_id = data["user"]["id"]
    tier    = data["user"]["tier"]

    print(f"   ✅ Bot user created — tier: {tier}")

    # Upgrade to clinic tier if admin token provided
    if args.admin_token and tier != "clinic":
        print("   ⬆️  Upgrading to clinic tier...")
        try:
            result = put(
                f"{args.url}/api/admin/users/{user_id}/tier",
                {"tier": "clinic"},
                args.admin_token,
            )
            print(f"   ✅ Upgraded: {result['old_tier']} → {result['new_tier']}")
        except Exception as e:
            print(f"   ⚠️  Could not upgrade tier: {e}")
            print("       Add your admin token with --admin-token YOUR_JWT")

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add this to your .env file:

BOT_API_KEY={token}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bot credentials:
  Email:    {args.email}
  Password: {password}
  User ID:  {user_id}

⚠️  Save the password — you cannot recover it.
""")


if __name__ == "__main__":
    main()
