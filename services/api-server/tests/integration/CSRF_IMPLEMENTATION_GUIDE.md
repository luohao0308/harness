# CSRF Protection Implementation Guide

**Quick Reference for Developers**

---

## Overview

This guide provides step-by-step instructions for implementing CSRF protection on SAML endpoints based on the test requirements in `test_saml_csrf_protection.py`.

---

## 1. RelayState HMAC Signing

### Problem
Current implementation uses plain provider_id in RelayState, allowing tampering and replay attacks.

### Solution
Sign RelayState with HMAC-SHA256 and include timestamp for expiration.

### Implementation

#### Step 1: Add CSRF Configuration

**File:** `app/core/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... existing settings ...
    
    # CSRF Protection
    csrf_secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for HMAC signing of RelayState tokens"
    )
    relay_state_max_age: int = Field(
        default=300,
        description="RelayState token expiration in seconds (default: 5 minutes)"
    )
```

#### Step 2: Create CSRF Utility Module

**File:** `app/security/csrf.py`

```python
"""
CSRF Protection Utilities for SAML Endpoints

Story 6.6 - CSRF Protection
"""
import hashlib
import hmac
import time
from typing import Tuple

from app.core.config import get_settings


def generate_relay_state_token(provider_id: str, timestamp: int | None = None) -> str:
    """
    Generate a secure RelayState token with HMAC signature.
    
    Format: provider_id:timestamp:signature
    
    Args:
        provider_id: SAML provider UUID
        timestamp: Unix timestamp (defaults to current time)
    
    Returns:
        Signed RelayState token
    
    Example:
        >>> token = generate_relay_state_token("provider-123")
        >>> print(token)
        provider-123:1717545600:abc123def456...
    """
    settings = get_settings()
    
    if timestamp is None:
        timestamp = int(time.time())
    
    message = f"{provider_id}:{timestamp}"
    signature = hmac.new(
        settings.csrf_secret_key.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    
    return f"{message}:{signature}"


def verify_relay_state_token(relay_state: str) -> Tuple[bool, str | None, str | None]:
    """
    Verify RelayState token integrity and freshness.
    
    Args:
        relay_state: RelayState token to verify
    
    Returns:
        Tuple of (is_valid, provider_id, error_message)
    
    Example:
        >>> is_valid, provider_id, error = verify_relay_state_token(token)
        >>> if is_valid:
        ...     print(f"Valid token for provider: {provider_id}")
        ... else:
        ...     print(f"Invalid token: {error}")
    """
    settings = get_settings()
    
    try:
        parts = relay_state.split(":")
        if len(parts) != 3:
            return False, None, "Invalid RelayState format"
        
        provider_id, timestamp_str, signature = parts
        timestamp = int(timestamp_str)
        
        # Verify signature using constant-time comparison
        expected_signature = hmac.new(
            settings.csrf_secret_key.encode(),
            f"{provider_id}:{timestamp}".encode(),
            hashlib.sha256,
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return False, None, "Invalid RelayState signature"
        
        # Verify freshness (not expired)
        current_time = int(time.time())
        if current_time - timestamp > settings.relay_state_max_age:
            return False, None, f"RelayState expired (max age: {settings.relay_state_max_age}s)"
        
        return True, provider_id, None
    
    except (ValueError, IndexError) as e:
        return False, None, f"RelayState parsing error: {str(e)}"
```

#### Step 3: Update SAML Service

**File:** `app/services/saml_service.py`

```python
from app.security.csrf import generate_relay_state_token

class SAMLService:
    def generate_authn_request(self, provider: SAMLProvider) -> dict[str, str]:
        """Generate SAML AuthnRequest for SP-Initiated SSO flow."""
        # ... existing code ...
        
        # Generate signed RelayState
        relay_state = generate_relay_state_token(provider.id)
        
        # ... rest of implementation ...
        
        return {
            "redirect_url": authn_url,
            "relay_state": relay_state,  # Return to caller
        }
```

#### Step 4: Update ACS Endpoint

**File:** `app/api/saml.py`

```python
from app.security.csrf import verify_relay_state_token

@router.post("/acs")
async def saml_acs(
    saml_response: Annotated[str, Form(alias="SAMLResponse")],
    db: DbSession,
    relay_state: Annotated[str | None, Form(alias="RelayState")] = None,
) -> SAMLACSResponse:
    """Process SAML Response from Identity Provider."""
    
    # ... existing IdP-initiated flow logic ...
    
    if relay_state:
        # SP-Initiated: Verify signed RelayState
        is_valid, provider_id, error = verify_relay_state_token(relay_state)
        
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid RelayState: {error}",
            )
        
        provider = provider_service.get_provider_by_id(provider_id)
        # ... rest of processing ...
```

---

## 2. Origin/Referer Header Validation

### Problem
No validation of request origin allows cross-origin CSRF attacks.

### Solution
Validate Origin/Referer headers against allowlist of trusted origins.

### Implementation

#### Step 1: Add Middleware

**File:** `app/middleware/csrf.py`

```python
"""
CSRF Protection Middleware

Story 6.6 - CSRF Protection
"""
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urlparse

from app.core.config import get_settings


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate Origin/Referer headers on SAML endpoints.
    
    Protects against cross-origin CSRF attacks on state-changing operations.
    """
    
    PROTECTED_PATHS = [
        "/api/auth/saml/acs",
        "/api/auth/saml/sls",
    ]
    
    async def dispatch(self, request: Request, call_next):
        # Only check POST requests to protected paths
        if request.method == "POST" and any(
            request.url.path.startswith(path) for path in self.PROTECTED_PATHS
        ):
            if not self._validate_origin(request):
                raise HTTPException(
                    status_code=403,
                    detail="CSRF validation failed: Invalid origin",
                )
        
        response = await call_next(request)
        return response
    
    def _validate_origin(self, request: Request) -> bool:
        """Validate request Origin/Referer against allowlist."""
        settings = get_settings()
        
        # Get Origin or Referer header
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        
        # Extract origin from Referer if Origin not present
        if not origin and referer:
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        
        if not origin:
            # No Origin/Referer - reject for security
            # Exception: Allow if coming from IdP (POST from external domain)
            # In production, you may want to allow IdP domains specifically
            return False
        
        # Build allowed origins list
        allowed_origins = [
            str(settings.console_base_url).rstrip("/"),
            str(settings.app_base_url).rstrip("/"),
            str(settings.api_base_url).rstrip("/"),
        ]
        
        # Check if origin is in allowlist
        return any(origin.startswith(allowed) for allowed in allowed_origins)
```

#### Step 2: Register Middleware

**File:** `app/main.py`

```python
from app.middleware.csrf import CSRFProtectionMiddleware

app = FastAPI(...)

# Add CSRF protection middleware
app.add_middleware(CSRFProtectionMiddleware)

# ... rest of middleware ...
```

---

## 3. SameSite Cookie Attribute

### Problem
Session tokens returned only in response body (JWT), vulnerable to CSRF if cookies added later.

### Solution
Add SameSite=Lax attribute to session cookies.

### Implementation

#### Step 1: Update Session Service

**File:** `app/services/session_service.py`

```python
from fastapi import Response

class SessionService:
    def create_session_cookie(
        self,
        response: Response,
        session_token: str,
        expires_at: datetime,
    ) -> None:
        """
        Set session cookie with secure attributes.
        
        Security attributes:
        - HttpOnly: Prevent XSS access to cookie
        - Secure: Only send over HTTPS
        - SameSite=Lax: Prevent CSRF attacks
        """
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,  # Require HTTPS in production
            samesite="lax",  # or "strict" for stricter CSRF protection
            expires=expires_at,
            path="/",
        )
```

#### Step 2: Update ACS Endpoint

**File:** `app/api/saml.py`

```python
from fastapi import Response

@router.post("/acs")
async def saml_acs(
    saml_response: Annotated[str, Form(alias="SAMLResponse")],
    db: DbSession,
    response: Response,  # Add Response parameter
    relay_state: Annotated[str | None, Form(alias="RelayState")] = None,
) -> SAMLACSResponse:
    """Process SAML Response from Identity Provider."""
    
    # ... existing processing ...
    
    # Set secure session cookie
    session_service = SessionService(db)
    session_service.create_session_cookie(
        response=response,
        session_token=session_data["session_token"],
        expires_at=datetime.fromisoformat(session_data["expires_at"]),
    )
    
    # Still return token in response body for flexibility
    return SAMLACSResponse(**response_data)
```

---

## 4. Rate Limiting

### Problem
No rate limiting allows brute force and DoS attacks on SAML endpoints.

### Solution
Implement per-IP rate limiting using Redis or in-memory store.

### Implementation

#### Step 1: Add Rate Limiting Dependency

**File:** `app/middleware/rate_limit.py`

```python
"""
Rate Limiting for SAML Endpoints

Story 6.6 - CSRF Protection
"""
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
import threading


class RateLimiter:
    """
    Simple in-memory rate limiter.
    
    For production, use Redis-based rate limiting.
    """
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = threading.Lock()
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed under rate limit."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        with self.lock:
            # Remove old requests
            self.requests[key] = [
                ts for ts in self.requests[key] if ts > cutoff
            ]
            
            # Check limit
            if len(self.requests[key]) >= self.max_requests:
                return False
            
            # Record this request
            self.requests[key].append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit SAML endpoints to prevent abuse."""
    
    def __init__(self, app):
        super().__init__(app)
        # 10 requests per minute per IP
        self.limiter = RateLimiter(max_requests=10, window_seconds=60)
    
    RATE_LIMITED_PATHS = [
        "/api/auth/saml/acs",
        "/api/auth/saml/sls",
        "/api/auth/saml/login",
    ]
    
    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(path) for path in self.RATE_LIMITED_PATHS):
            # Use client IP as rate limit key
            client_ip = request.client.host if request.client else "unknown"
            
            if not self.limiter.is_allowed(client_ip):
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                )
        
        response = await call_next(request)
        return response
```

#### Step 2: Register Middleware

**File:** `app/main.py`

```python
from app.middleware.rate_limit import RateLimitMiddleware

app = FastAPI(...)

# Add rate limiting
app.add_middleware(RateLimitMiddleware)
```

---

## Testing Your Implementation

### Run CSRF Tests

```bash
cd services/api-server
.venv/bin/python -m pytest tests/integration/test_saml_csrf_protection.py -v
```

### Expected Results After Implementation

All tests should pass:
- ✅ Test 1-4: RelayState validation
- ✅ Test 5: Origin validation (should reject cross-origin)
- ✅ Test 6-7: SLS validation
- ✅ Test 8: SLS origin validation (should reject cross-origin)
- ✅ Test 9-10: Cookie and signature validation

---

## Configuration

### Environment Variables

Add to `.env` or environment configuration:

```bash
# CSRF Protection
CSRF_SECRET_KEY=your-secret-key-here-minimum-32-chars
RELAY_STATE_MAX_AGE=300

# Allowed Origins (comma-separated)
ALLOWED_ORIGINS=https://app.example.com,https://console.example.com
```

### Production Checklist

- [ ] Generate strong CSRF secret key (32+ characters)
- [ ] Configure allowed origins in production
- [ ] Enable HTTPS (required for Secure cookies)
- [ ] Set SameSite=Lax on all session cookies
- [ ] Implement Redis-based rate limiting
- [ ] Monitor rate limit metrics
- [ ] Set up alerts for CSRF attempts

---

## Security Best Practices

### 1. CSRF Secret Key Management
- Use cryptographically strong random key
- Rotate regularly (e.g., every 90 days)
- Store in secure secret management system
- Never commit to version control

### 2. Origin Allowlist
- Maintain strict allowlist
- Include only trusted domains
- Review quarterly
- Log blocked origins for monitoring

### 3. Rate Limiting
- Start conservative (10 req/min)
- Monitor legitimate traffic patterns
- Adjust based on metrics
- Implement exponential backoff

### 4. Cookie Security
- Always use HTTPS in production
- Set HttpOnly flag (prevent XSS)
- Set Secure flag (HTTPS only)
- Use SameSite=Lax (balance security/usability)

---

## Troubleshooting

### "Invalid RelayState signature" Error

**Cause:** CSRF secret key mismatch  
**Solution:** Ensure same secret key across all app instances

### "CSRF validation failed: Invalid origin" Error

**Cause:** Request from non-allowed origin  
**Solution:** Add origin to allowlist in configuration

### "Too many requests" Error

**Cause:** Rate limit exceeded  
**Solution:** Legitimate user - increase limit; Attack - investigate IP

### Tests Failing After Implementation

**Check:**
1. CSRF secret key is set in test environment
2. Test client sends correct Origin headers
3. Middleware is properly registered
4. Configuration is loaded correctly

---

## References

- Test Suite: `tests/integration/test_saml_csrf_protection.py`
- Summary: `tests/integration/CSRF_PROTECTION_TESTS_SUMMARY.md`
- Security Review: `tests/integration/INTEGRATION_TEST_REVIEW.md`
- OWASP CSRF Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

---

**Last Updated:** 2026-06-15  
**Version:** 1.0
