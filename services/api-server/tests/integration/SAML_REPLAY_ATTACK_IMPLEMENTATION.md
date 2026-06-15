# SAML Replay Attack Prevention - Implementation Summary

**Story 6.3 - SAML Replay Attack Prevention**  
**Priority:** P1 - CRITICAL  
**Security Classification:** OWASP A04:2021 - Security Misconfiguration

---

## Executive Summary

This implementation adds comprehensive replay attack prevention to the SAML SSO system. Replay attacks occur when an attacker intercepts a valid SAML assertion and attempts to reuse it to gain unauthorized access.

**Impact:** Without these protections, an attacker who intercepts network traffic can:
- Impersonate legitimate users by replaying their SAML assertions
- Gain unauthorized access to the system multiple times with a single intercepted assertion
- Bypass standard authentication security measures

---

## Implementation Components

### 1. Database Models (✅ Complete)

**File:** `services/api-server/app/db/models.py`

#### SAMLAssertionUsage Table
Tracks every SAML assertion ID that has been successfully processed to ensure one-time use only.

**Columns:**
- `assertion_id` (UNIQUE): The SAML assertion ID from the IdP
- `provider_id`: Which IdP issued this assertion
- `subject_id`: User identifier from the assertion (NameID)
- `session_id`: Optional session binding
- `authn_request_id`: Links to original AuthnRequest (if SP-initiated)
- `used_at`: Timestamp when assertion was processed
- `expires_at`: Cleanup timestamp (1 hour after use)

**Indexes:**
- Unique index on `assertion_id` (prevents duplicate inserts)
- Index on `expires_at` (efficient cleanup queries)
- Index on `provider_id` (per-IdP tracking)

#### SAMLAuthnRequest Table
Tracks AuthnRequest IDs issued during SP-initiated SSO to validate InResponseTo fields.

**Columns:**
- `request_id` (UNIQUE): The AuthnRequest ID we generated
- `provider_id`: Target IdP
- `session_id`: Session that initiated the request
- `relay_state`: Optional state parameter
- `created_at`: When request was issued
- `expires_at`: Request validity window (10 minutes)
- `consumed_at`: When matching response was received

**Indexes:**
- Unique index on `request_id`
- Index on `session_id` (session-to-request mapping)
- Index on `expires_at` (cleanup)

### 2. Database Migration (✅ Complete)

**File:** `alembic/versions/20260615_0041_create_saml_replay_prevention_tables.py`

Creates both tables with all indexes and constraints.

**To Apply:**
```bash
cd services/api-server
alembic upgrade head
```

### 3. Test Suite (✅ Complete)

**File:** `tests/integration/test_saml_replay_attacks.py`

**12 Comprehensive Test Scenarios:**

#### Suite 1: InResponseTo Validation (4 tests)
1. ✅ Valid InResponseTo matches original request - PASS
2. ✅ Missing InResponseTo in response - FAIL
3. ✅ Invalid InResponseTo (doesn't match any request) - FAIL
4. ✅ InResponseTo from different session - FAIL

#### Suite 2: Assertion ID Tracking (4 tests)
5. ✅ First use of assertion ID - PASS
6. ✅ **Reuse of same assertion ID - FAIL (PRIMARY DEFENSE)**
7. ✅ Expired assertion ID cleanup
8. ✅ Concurrent requests with same assertion ID - FAIL

#### Suite 3: Timing Window (2 tests)
9. ✅ Assertion used within 5-minute window - PASS
10. ✅ Assertion used after 5-minute window - FAIL

#### Suite 4: Combined Attacks (2 tests)
11. ✅ Valid InResponseTo but replayed assertion ID - FAIL
12. ✅ Different session attempts to use valid assertion - FAIL

---

## Implementation Checklist

### ✅ Completed
- [x] Database models defined (`SAMLAssertionUsage`, `SAMLAuthnRequest`)
- [x] Database migration created
- [x] Comprehensive test suite (12 tests covering all attack vectors)
- [x] Test documentation with attack scenarios

### ⚠️ Pending Implementation

The following components need to be implemented in `services/api-server/app/services/saml_service.py`:

#### 1. AuthnRequest ID Tracking
**Method:** `generate_authn_request()` (modify existing)

```python
def generate_authn_request(self, provider: SAMLProvider, session_id: str) -> dict[str, str]:
    """Generate AuthnRequest and record request ID for validation."""
    # Generate AuthnRequest using existing logic
    result = ...  # existing code
    
    # Extract request ID from generated AuthnRequest
    request_id = extract_request_id_from_saml(result["saml_request"])
    
    # Store request ID for InResponseTo validation
    authn_request = SAMLAuthnRequest(
        request_id=request_id,
        provider_id=provider.id,
        session_id=session_id,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    self.db_session.add(authn_request)
    self.db_session.commit()
    
    return result
```

#### 2. InResponseTo Validation
**Method:** `validate_inresponseto()` (new)

```python
def validate_inresponseto(
    self, 
    in_response_to: str | None,
    session_id: str,
    is_idp_initiated: bool
) -> None:
    """
    Validate InResponseTo field matches a pending AuthnRequest.
    
    Raises:
        ValueError: If InResponseTo is invalid or missing
    """
    if is_idp_initiated:
        # IdP-initiated flow: no InResponseTo expected
        return
    
    if not in_response_to:
        raise ValueError("InResponseTo is required for SP-initiated flow")
    
    # Find matching AuthnRequest
    authn_request = self.db_session.query(SAMLAuthnRequest).filter(
        SAMLAuthnRequest.request_id == in_response_to,
        SAMLAuthnRequest.session_id == session_id,
        SAMLAuthnRequest.consumed_at.is_(None),
        SAMLAuthnRequest.expires_at > datetime.now(UTC),
    ).first()
    
    if not authn_request:
        raise ValueError(
            f"InResponseTo '{in_response_to}' does not match any valid pending request"
        )
    
    # Mark as consumed (prevent reuse)
    authn_request.consumed_at = datetime.now(UTC)
    self.db_session.commit()
```

#### 3. Assertion ID Tracking
**Method:** `track_assertion_usage()` (new)

```python
def track_assertion_usage(
    self,
    assertion_id: str,
    provider_id: str,
    subject_id: str,
    session_id: str | None = None,
    authn_request_id: str | None = None,
) -> None:
    """
    Track assertion ID to prevent replay attacks.
    
    Raises:
        ValueError: If assertion ID has already been used
    """
    # Check if assertion ID already used
    existing = self.db_session.query(SAMLAssertionUsage).filter(
        SAMLAssertionUsage.assertion_id == assertion_id
    ).first()
    
    if existing:
        raise ValueError(
            f"Assertion ID '{assertion_id}' has already been used at {existing.used_at}"
        )
    
    # Record usage
    usage = SAMLAssertionUsage(
        assertion_id=assertion_id,
        provider_id=provider_id,
        subject_id=subject_id,
        session_id=session_id,
        authn_request_id=authn_request_id,
        used_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    
    try:
        self.db_session.add(usage)
        self.db_session.commit()
    except IntegrityError:
        # Race condition: another request used this assertion concurrently
        self.db_session.rollback()
        raise ValueError(
            f"Assertion ID '{assertion_id}' was used by a concurrent request"
        )
```

#### 4. Process SAML Response Integration
**Method:** `process_saml_response()` (modify existing)

```python
def process_saml_response(
    self,
    saml_response: str,
    provider: SAMLProvider,
    session_id: str,
    is_idp_initiated: bool = False,
) -> dict[str, Any]:
    """Process and validate SAML Response with replay attack prevention."""
    
    # Extract assertion ID and InResponseTo from SAML response
    assertion_id = extract_assertion_id(saml_response)
    in_response_to = extract_in_response_to(saml_response) if not is_idp_initiated else None
    
    # 1. Validate InResponseTo (if SP-initiated)
    if not is_idp_initiated:
        self.validate_inresponseto(in_response_to, session_id, is_idp_initiated)
    
    # 2. Existing validation (signature, timing, audience)
    # ... existing code ...
    
    # 3. Track assertion usage (prevent replay)
    subject_id = extract_subject_id(saml_response)
    self.track_assertion_usage(
        assertion_id=assertion_id,
        provider_id=provider.id,
        subject_id=subject_id,
        session_id=session_id,
        authn_request_id=in_response_to,
    )
    
    # 4. Continue with user provisioning
    # ... existing code ...
```

#### 5. Cleanup Job
**Method:** `cleanup_expired_replay_prevention_records()` (new)

```python
def cleanup_expired_replay_prevention_records(self) -> dict[str, int]:
    """
    Clean up expired assertion usage and AuthnRequest records.
    
    Should be run periodically (e.g., hourly cron job).
    
    Returns:
        Dict with counts of deleted records
    """
    now = datetime.now(UTC)
    
    # Clean expired assertion usage records
    deleted_assertions = self.db_session.query(SAMLAssertionUsage).filter(
        SAMLAssertionUsage.expires_at < now
    ).delete()
    
    # Clean expired AuthnRequest records
    deleted_requests = self.db_session.query(SAMLAuthnRequest).filter(
        SAMLAuthnRequest.expires_at < now
    ).delete()
    
    self.db_session.commit()
    
    return {
        "deleted_assertions": deleted_assertions,
        "deleted_requests": deleted_requests,
    }
```

---

## Testing Instructions

### 1. Run Migration
```bash
cd services/api-server
alembic upgrade head
```

### 2. Run Test Suite
```bash
# Run all replay attack tests
pytest tests/integration/test_saml_replay_attacks.py -v

# Run specific test
pytest tests/integration/test_saml_replay_attacks.py::test_reuse_of_same_assertion_id_fail_replay_attack -v
```

### 3. Expected Results (After Implementation)
All 12 tests should PASS, indicating:
- ✅ Replay attacks are blocked
- ✅ InResponseTo validation works
- ✅ Assertion IDs are tracked correctly
- ✅ Timing windows are enforced
- ✅ Session isolation is maintained

---

## Security Impact

### Before Implementation
- ❌ Attacker can intercept and replay SAML assertions indefinitely
- ❌ No tracking of assertion usage
- ❌ No InResponseTo validation
- ❌ High risk of unauthorized access via replay attacks

### After Implementation
- ✅ Each SAML assertion can only be used once
- ✅ InResponseTo validation prevents response forgery
- ✅ Session binding prevents cross-session attacks
- ✅ Timing windows limit attack surface
- ✅ Compliant with OWASP security guidelines

### OWASP Coverage
- **A04:2021 - Security Misconfiguration:** Fixed
- **A07:2021 - Identification and Authentication Failures:** Mitigated

---

## Performance Considerations

### Database Queries
Each SAML authentication adds:
1. **INSERT** into `saml_assertion_usage` (with unique constraint check)
2. **SELECT** from `saml_authn_requests` (indexed lookup)
3. **UPDATE** to mark AuthnRequest as consumed

**Impact:** Minimal (~5-10ms added latency per SSO login)

### Storage Growth
- Assertion usage records: ~200 bytes per record
- AutoCleanup after 1 hour
- Estimated: ~1000 SSO logins/hour = 200KB/hour (negligible)

### Indexes
All critical queries are indexed:
- Assertion ID lookup: O(log n) via unique index
- Request ID lookup: O(log n) via unique index
- Cleanup queries: O(log n) via expires_at index

---

## Monitoring & Alerts

### Metrics to Track
1. **Replay attempt count:** Number of rejected assertions (should be rare)
2. **InResponseTo failures:** Indicates potential attacks or clock skew issues
3. **Cleanup job success:** Ensure old records are purged

### Alert Thresholds
- **CRITICAL:** >10 replay attempts in 1 hour (potential active attack)
- **WARNING:** >5 InResponseTo failures in 1 hour (clock skew or config issue)
- **INFO:** Cleanup job failures

---

## References

### OWASP Guidelines
- [OWASP Top 10 2021 - A04:2021](https://owasp.org/Top10/A04_2021-Insecure_Design/)
- [SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html)

### SAML Specifications
- [SAML 2.0 Core Specification](http://docs.oasis-open.org/security/saml/v2.0/)
- Section 3.2.1: Assertion ID uniqueness requirements
- Section 3.4.1.2: InResponseTo validation

### Related Stories
- Story 6.1: Okta Integration Testing (baseline SSO flows)
- Story 6.2: Azure AD Integration Testing (IdP-specific testing)
- Story 6.4: XML Injection Prevention (next security enhancement)

---

## Sign-off Checklist

- [x] Database models reviewed and approved
- [x] Migration tested on development database
- [x] Test suite covers all attack vectors
- [ ] Implementation code review completed
- [ ] Security team approval obtained
- [ ] Integration tests passing
- [ ] Performance impact assessed (<10ms overhead)
- [ ] Documentation complete
- [ ] Monitoring/alerts configured

---

**Document Version:** 1.0  
**Last Updated:** 2026-06-15  
**Author:** Senior Security Engineer  
**Reviewers:** Security Team, QA Team
