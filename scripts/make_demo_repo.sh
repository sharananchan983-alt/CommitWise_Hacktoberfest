#!/usr/bin/env bash
# ==============================================================================
# CommitWise Demo Repository Builder
# Builds a realistic git repository with two authors, AST symbols,
# downstream callers, outdated documentation, and pending uncommitted changes.
# ==============================================================================

set -e

TARGET_DIR="${1:-demo_repo}"

echo "Creating CommitWise demo repository in '${TARGET_DIR}'..."

# Clean up existing demo_repo if present
if [ -d "$TARGET_DIR" ]; then
    echo "Removing existing directory '${TARGET_DIR}'..."
    rm -rf "$TARGET_DIR"
fi

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

# Initialize git repository
git init -q
git checkout -q -b main 2>/dev/null || git checkout -q -b master 2>/dev/null || true

# Configure local git user if not set
git config user.name "Alice Johnson"
git config user.email "alice@example.com"

# Create directories
mkdir -p auth api docs ui screenshots

# ------------------------------------------------------------------------------
# Commit 1 by Alice Johnson: Initial auth token module, API routes, and docs
# ------------------------------------------------------------------------------
cat << 'EOF' > auth/token.py
"""JWT and session token verification module."""

import time
from typing import Optional, Dict, Any

SECRET_KEY = "super-secret-key-change-in-production"

def create_token(user_id: str, role: str = "member") -> str:
    """Create a signed session token for a user."""
    timestamp = int(time.time())
    return f"{user_id}:{role}:{timestamp}"

def verify_token(token: str) -> bool:
    """Verify session token structure and validity."""
    if not token or not isinstance(token, str):
        return False
    parts = token.split(":")
    if len(parts) != 3:
        return False
    return True
EOF

cat << 'EOF' > api/routes.py
"""Protected API endpoints requiring token authentication."""

from auth.token import verify_token

def handle_login(username: str, password: str) -> dict:
    """Authenticate user credentials."""
    return {"status": "success", "username": username}

def get_user_profile(token: str) -> dict:
    """Fetch user profile after verifying token."""
    if not verify_token(token):
        raise PermissionError("Invalid authentication token")
    return {"user_id": "usr_991", "name": "Alice Johnson", "role": "admin"}
EOF

cat << 'EOF' > docs/auth.md
# Authentication Guide

CommitWise Authentication uses lightweight token verification.

## Token Verification
The `verify_token` function validates active session tokens:

```python
is_valid = verify_token(token)
```

Called by `api/routes.py` before serving protected resources.
EOF

cat << 'EOF' > ui/login.py
"""UI rendering component for login dialog."""

def render_login_form():
    return {
        "title": "Welcome Back",
        "button_label": "Sign In",
        "button_color": "#808080",
        "border_radius": "0px",
    }
EOF

git add .
git -c user.name="Alice Johnson" -c user.email="alice@example.com" commit -q -m "feat(auth): initial token verification and protected profile route"

# ------------------------------------------------------------------------------
# Commit 2 by Bob Smith: Additional protected route in api/routes.py
# ------------------------------------------------------------------------------
cat << 'EOF' >> api/routes.py

def get_dashboard_metrics(token: str) -> dict:
    """Retrieve system metrics for authenticated users."""
    if not verify_token(token):
        raise PermissionError("Access denied: invalid token")
    return {"active_users": 142, "uptime": "99.98%"}
EOF

git add api/routes.py
git -c user.name="Bob Smith" -c user.email="bob@example.com" commit -q -m "feat(api): add protected dashboard metrics endpoint"

# ------------------------------------------------------------------------------
# Create Pending Uncommitted Changes (working tree diff for CommitWise)
# ------------------------------------------------------------------------------
echo "Injecting pending code modifications for CommitWise to analyze..."

# 1. Modify auth/token.py:
#    - Changes verify_token signature: adds 'required_role: Optional[str] = None'
#    - Adds brand new function 'revoke_token(token: str) -> bool'
cat << 'EOF' > auth/token.py
"""JWT and session token verification module."""

import time
from typing import Optional, Dict, Any

SECRET_KEY = "super-secret-key-change-in-production"

def create_token(user_id: str, role: str = "member") -> str:
    """Create a signed session token for a user."""
    timestamp = int(time.time())
    return f"{user_id}:{role}:{timestamp}"

def verify_token(token: str, required_role: Optional[str] = None) -> bool:
    """Verify session token structure, validity, and optional role requirement."""
    if not token or not isinstance(token, str):
        return False
    parts = token.split(":")
    if len(parts) != 3:
        return False
    user_id, role, timestamp = parts[0], parts[1], parts[2]
    if required_role and role != required_role:
        return False
    return True

def revoke_token(token: str) -> bool:
    """Explicitly invalidate and revoke an active session token."""
    if not token:
        return False
    # Logic to record token in revocation blacklist
    return True
EOF

# 2. Modify ui/login.py:
#    - Modernizes button styling, color, and border radius
cat << 'EOF' > ui/login.py
"""UI rendering component for login dialog."""

def render_login_form():
    return {
        "title": "Welcome Back to CommitWise",
        "button_label": "Sign In with Single Sign-On",
        "button_color": "#1A73E8",
        "border_radius": "8px",
        "shadow": "0 4px 6px rgba(0, 0, 0, 0.1)",
    }
EOF

# ------------------------------------------------------------------------------
# Generate Sample Before & After Screenshots for Multimodal Testing
# ------------------------------------------------------------------------------
python - << 'PYEOF'
import os
try:
    from PIL import Image, ImageDraw, ImageFont

    def create_image(filename, bg_color, btn_color, btn_text, radius, title):
        img = Image.new("RGB", (600, 360), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Draw card container
        draw.rectangle([100, 50, 500, 310], fill="#FFFFFF", outline="#E2E8F0", width=2)

        # Title
        draw.text((140, 80), title, fill="#1E293B")
        draw.text((140, 115), "Enter your credentials to continue", fill="#64748B")

        # Input fields
        draw.rectangle([140, 150, 460, 185], fill="#F8FAFC", outline="#CBD5E1", width=1)
        draw.text((150, 160), "user@example.com", fill="#94A3B8")

        draw.rectangle([140, 200, 460, 235], fill="#F8FAFC", outline="#CBD5E1", width=1)
        draw.text((150, 210), "••••••••••••", fill="#94A3B8")

        # Submit button
        if radius > 0:
            draw.rounded_rectangle([140, 255, 460, 295], radius=radius, fill=btn_color)
        else:
            draw.rectangle([140, 255, 460, 295], fill=btn_color)
        draw.text((230, 268), btn_text, fill="#FFFFFF")

        img.save(filename)

    os.makedirs("screenshots", exist_ok=True)
    create_image("screenshots/before.png", "#F1F5F9", "#64748B", "Sign In", 0, "Welcome Back")
    create_image("screenshots/after.png", "#F8FAFC", "#1A73E8", "Sign In with SSO", 8, "Welcome Back to CommitWise")
    print("Generated demo screenshots: screenshots/before.png and screenshots/after.png")
except Exception as e:
    print(f"Skipping screenshot generation: {e}")
PYEOF

cd ..

echo "Demo repository successfully created at '${TARGET_DIR}'!"
echo "Pending changes are ready for CommitWise analysis."