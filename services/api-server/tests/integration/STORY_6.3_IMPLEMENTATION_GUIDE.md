# Story 6.3 - SAML Replay Attack Prevention
## Quick Implementation Guide

---

## 🚨 CRITICAL SECURITY GAP

**OWASP Classification:** A04:2021 - Security Misconfiguration  
**Risk Level:** CRITICAL  
**CVE Equivalent:** Similar to CVE-2020-13956, CVE-2021-29441

**Attack Scenario:**
```
1. User authenticates via SAML SSO
2. Attacker intercepts SAML assertion (network sniffing, MITM)
3. Attacker replays assertion to gain unauthorized access
4. System accepts replayed assertion → Breach
```

---

## ✅ What Was Done

### 1. Database Tables Created
- **`saml_assertion_usage`** - Tracks used assertion IDs
- **`saml_authn_requests`** - Tracks issued AuthnRequest IDs

### 2. Migration Ready
- File: `alembic/versions/20260615_0041_create_saml_replay_prevention_tables.py`
- Run: `alembic upgrade head`

### 3. Comprehensive Test Suite
- File: `tests/integration/test_saml_replay_attacks.py`
- **12 test scenarios** covering all attack vectors
- **4 test suites:** InResponseTo, Assertion ID, Timing, Combined

---

## ⚠️ What Needs Implementation

### Required Changes to `saml_service.py`

#### Change 1: Track AuthnRequest IDs
**Location:** `generate_authn_request()` method

**Add after generating AuthnRequest:**
```python
from app.db.models import SAMLAuthnRequest

# Store request ID for validation
authn_request = SAMLAuthnRequest(
    request_id=request_id,  # Extract from generated AuthnRequest
    provider_id=provider.id,
    session_id=session_id,
    created_at=datetime.now(UTC),
    expires_at=datetime.now(UTC) + timedelta(minutes=10),
)
db_session.add(authn_request)
db_session.commit()
```

#### Change 2: Validate InResponseTo
**Location:** `process_saml_response()` method

**Add before processing response:**
```python
from app.db.models import SAMLAuthnRequest

if not is_idp_initiated:
    # Extract InResponseTo from SAML response
    in_response_to = extract_in_response_to(saml_response)
    
    # Validate against stored AuthnRequest
    authn_request = db_session.query(SAMLAuthnRequest).filter(
        SAMLAuthnRequest.request_id == in_response_to,
        SAMLAuthnRequest.consumed_at.is_(None),
        SAMLAuthnRequest.expires_at > datetime.now(UTC),
    ).first()
    
    if not authn_request:
        raise ValueError("Invalid or expired InResponseTo")
    
    # Mark as consumed
    authn_request.consumed_at = datetime.now(UTC)
    db_session.commit()
```

#### Change 3: Track Assertion IDs
**Location:** `process_saml_response()` method

**Add before creating user session:**
```python
from app.db.models import SAMLAssertionUsage
from sqlalchemy.exc import IntegrityError

# Extract assertion ID from SAML response
assertion_id = extract_assertion_id(saml_response)

# Check if already used
existing = db_session.query(SAMLAssertionUsage).filter(
    SAMLAssertionUsage.assertion_id == assertion_id
).first()

if existing:
    raise ValueError(f"Assertion ID already used at {existing.used_at}")

# Record usage
try:
    usage = SAMLAssertionUsage(
        assertion_id=assertion_id,
        provider_id=provider.id,
        subject_id=nameid,
        used_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(usage)
    db_session.commit()
except IntegrityError:
    db_session.rollback()
    raise ValueError("Assertion ID already used (concurrent request)")
```

#### Change 4: Cleanup Job
**Location:** New method in `saml_service.py`

**Add new method:**
```python
def cleanup_expired_replay_prevention_records(self) -> dict[str, int]:
    """Remove expired records. Run hourly via cron."""
    now = datetime.now(UTC)
    
    deleted_assertions = self.db_session.query(SAMLAssertionUsage).filter(
        SAMLAssertionUsage.expires_at < now
    ).delete()
    
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

## 🧪 Testing Workflow

### Step 1: Apply Migration
```bash
cd services/api-server
alembic upgrade head
```

### Step 2: Run Tests (Before Implementation)
```bash
pytest tests/integration/test_saml_replay_attacks.py -v
```

**Expected:** Tests will FAIL (implementation not done yet)

### Step 3: Implement Changes
Follow the 4 changes above in `saml_service.py`

### Step 4: Run Tests (After Implementation)
```bash
pytest tests/integration/test_saml_replay_attacks.py -v
```

**Expected:** All 12 tests PASS ✅

### Step 5: Verify with Manual Test
```bash
# Test 1: Normal login - should succeed
curl -X POST http://localhost:8000/api/auth/saml/login \
  -H "Content-Type: application/json" \
  -d '{"provider_id": "test-provider"}'

# Test 2: Replay assertion - should FAIL with 401
# (Use same SAMLResponse twice)
```

---

## 📊 Test Coverage Matrix

| # | Test Scenario | Attack Type | Expected Result |
|---|--------------|-------------|-----------------|
| 1 | Valid InResponseTo | Baseline | ✅ PASS |
| 2 | Missing InResponseTo | Response forgery | ❌ FAIL (401) |
| 3 | Invalid InResponseTo | Response forgery | ❌ FAIL (401) |
| 4 | Cross-session InResponseTo | Session hijacking | ❌ FAIL (401) |
| 5 | First assertion use | Baseline | ✅ PASS |
| 6 | **Replayed assertion** | **Primary replay attack** | **❌ FAIL (401)** |
| 7 | Expired cleanup | Maintenance | ✅ Works |
| 8 | Concurrent replay | Race condition | ❌ FAIL (401) |
| 9 | Within time window | Baseline | ✅ PASS |
| 10 | After time window | Expired assertion | ❌ FAIL (401) |
| 11 | Valid InResponseTo + replay | Sophisticated attack | ❌ FAIL (401) |
| 12 | Cross-session assertion | Session theft | ❌ FAIL (401) |

**Critical Test:** #6 (Replayed assertion) - This is the PRIMARY defense

---

## 🔍 Helper Functions Needed

You'll need to implement these XML parsing helpers:

```python
def extract_assertion_id(saml_response: str) -> str:
    """Extract Assertion ID from SAML Response."""
    import xml.etree.ElementTree as ET
    xml = base64.b64decode(saml_response)
    root = ET.fromstring(xml)
    # Find <Assertion ID="...">
    ns = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}
    assertion = root.find('.//saml:Assertion', ns)
    return assertion.get('ID')

def extract_in_response_to(saml_response: str) -> str | None:
    """Extract InResponseTo from SAML Response."""
    import xml.etree.ElementTree as ET
    xml = base64.b64decode(saml_response)
    root = ET.fromstring(xml)
    return root.get('InResponseTo')

def extract_subject_id(saml_response: str) -> str:
    """Extract Subject NameID from SAML Response."""
    import xml.etree.ElementTree as ET
    xml = base64.b64decode(saml_response)
    root = ET.fromstring(xml)
    ns = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}
    nameid = root.find('.//saml:Subject/saml:NameID', ns)
    return nameid.text
```

---

## 🎯 Success Criteria

### Technical
- [x] Database tables created
- [x] Migration file ready
- [x] Test suite complete (12 tests)
- [ ] Implementation in `saml_service.py`
- [ ] All tests passing
- [ ] Manual replay attack blocked

### Security
- [ ] Replay attacks blocked (Test #6 passes)
- [ ] InResponseTo validation working (Tests #2-4 pass)
- [ ] Timing enforcement working (Test #10 passes)
- [ ] Session isolation working (Tests #4, #12 pass)

### Operations
- [ ] Cleanup job implemented
- [ ] Monitoring alerts configured
- [ ] Documentation complete
- [ ] Security team sign-off

---

## 📈 Performance Impact

**Expected Overhead per SSO Login:**
- 1 INSERT (assertion_id) + 1 SELECT (InResponseTo) + 1 UPDATE (consume)
- ~5-10ms added latency
- Negligible storage (<200KB/hour for 1000 logins)

**Database Load:**
- Indexed lookups: O(log n)
- Unique constraint prevents duplicates at DB level
- Auto-cleanup keeps tables small

---

## 🚀 Deployment Checklist

- [ ] Run migration on DEV database
- [ ] Run tests on DEV (all pass)
- [ ] Code review by security team
- [ ] Run migration on STAGING database
- [ ] Run integration tests on STAGING
- [ ] Monitor STAGING for 24 hours
- [ ] Run migration on PROD database
- [ ] Enable monitoring alerts
- [ ] Document in security audit log

---

## 📞 Support

**Questions?**
- Security concerns: Contact Security Team
- Implementation help: Review `SAML_REPLAY_ATTACK_IMPLEMENTATION.md`
- Test failures: Check test logs in `pytest` output

**References:**
- Test file: `tests/integration/test_saml_replay_attacks.py`
- Implementation doc: `tests/integration/SAML_REPLAY_ATTACK_IMPLEMENTATION.md`
- Integration review: `tests/integration/INTEGRATION_TEST_REVIEW.md`

---

**Priority:** P1 - CRITICAL  
**Estimated Time:** 4-6 hours implementation + 2 hours testing  
**Security Impact:** HIGH - Prevents unauthorized access via replay attacks
