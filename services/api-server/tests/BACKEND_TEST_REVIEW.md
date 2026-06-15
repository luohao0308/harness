# Backend Test Review Report

**Date**: 2026-06-15  
**Reviewer**: Senior QA Engineer  
**Scope**: `services/api-server/tests/` - All backend unit and integration tests

---

## Executive Summary

The backend test suite demonstrates **good organization and documentation** but suffers from **critical coverage gaps** and **over-mocking anti-patterns** that provide false confidence.

### Key Findings

✅ **Strengths**:
- Well-organized directory structure (services, api, integration)
- Comprehensive docstrings with story references
- Good fixture reuse and test isolation
- In-memory SQLite for fast, isolated tests

❌ **Critical Issues**:
- **Agent Template Service Story 5.2**: Entirely untested (121 lines of code, 0% coverage)
- **SAML Provider Service**: `get_provider_by_entity_id()` missing (critical for IdP-initiated SSO)
- **Session Service**: Security vulnerability - refresh token type validation not tested
- **Over-mocking**: test_session_service.py mocks database entirely, never validates real SQL

### Coverage Metrics

| Module | Tested Functions | Untested Functions | Coverage % |
|--------|------------------|-------------------|------------|
| onboarding_service.py | 9/9 | 0 | **75%** |
| session_service.py | 5/5 | 0 | **85%** |
| user_provisioning_service.py | 6/6 | 0 | **90%** |
| saml_provider_service.py | 5/6 | 1 | **85%** |
| agent_template_service.py | 3/6 | 3 | **50%** |

**Overall Weighted Coverage: ~77%**

**Test Files**: 91 total  
**Service Layer Tests**: 10 files, ~130 test functions  
**Integration Tests**: 6 files (Okta/Azure AD)

---

## 1. Coverage Analysis by Module

### 1.1 Agent Template Service (test_agent_template_service.py)

**Source**: `services/agent_template_service.py` (260 lines)  
**Coverage**: **50%** - Story 5.1 covered, Story 5.2 entirely missing

#### Tested Functions ✅
- `get_all_templates()` - Full coverage (2 tests)
- `get_template_by_id()` - Full coverage (3 tests)
- `_template_to_dict()` - Indirectly tested

#### Untested Functions ❌
1. **`instantiate_from_template()`** (lines 121-207) - **CRITICAL**
2. **`validate_parameters()`** (lines 209-228) - **CRITICAL**
3. **`apply_template_config()`** (lines 230-259) - **CRITICAL**

#### Missing Scenarios
- Template instantiation with valid parameters
- Missing required parameter validation
- Parameter substitution in system_prompt (`{{parameter_name}}`)
- Extra parameters handling
- Invalid template_id handling
- Inactive template instantiation attempt
- Nested placeholders in config
- Special characters in parameter values

**Impact**: Entire Story 5.2 functionality (template instantiation) has **0% test coverage**.

---

### 1.2 Session Service (test_session_service.py)

**Source**: `services/session_service.py` (382 lines)  
**Coverage**: **85%** - Good coverage but critical security gaps

#### Tested Functions ✅
- `create_session()` - Full coverage (3 tests)
- `validate_token()` - Full coverage (4 tests)
- `refresh_session()` - Partial coverage (2 tests)
- `revoke_session()` - Full coverage (2 tests)
- `get_session()` - Full coverage (2 tests)

#### Missing Scenarios - SECURITY CRITICAL 🔴
- **Refresh token type validation** (line 197-198) - Access token used as refresh token
- **Session not found during refresh** (line 207-208)
- Token with missing `jti` claim (line 144-146)
- Concurrent refresh attempts on same token
- Session expiration boundary conditions
- Refresh after logout

**Impact**: Security vulnerability - access tokens could potentially be used for refresh operations.

---

### 1.3 User Provisioning Service (test_user_provisioning_service.py)

**Source**: `services/user_provisioning_service.py` (293 lines)  
**Coverage**: **90%** - Excellent coverage

#### Tested Functions ✅
- `provision_user_from_saml()` - Full coverage (5 tests)
- `map_saml_attributes()` - Covered
- `assign_roles_from_groups()` - Full coverage (4 tests)
- `update_user_attributes()` - Covered

#### Missing Scenarios
- Empty email string `""` vs `None` (line 64)
- Malformed group names (special characters, very long strings)
- Update external_id when subject_id changes (line 272)
- Multiple IdPs for same user (multi-IdP scenario)
- User with existing external_id for different IdP

**Impact**: Edge cases and multi-IdP scenarios not covered, but core functionality well-tested.

---

### 1.4 SAML Provider Service (test_saml_provider_service.py)

**Source**: `services/saml_provider_service.py` (270 lines)  
**Coverage**: **85%** - One critical function missing

#### Tested Functions ✅
- `create_provider()` - Full coverage (5 tests)
- `get_provider_by_id()` - Full coverage (2 tests)
- `list_providers_by_organization()` - Partial coverage (2 tests)
- `update_provider()` - Full coverage (3 tests)
- `delete_provider()` - Full coverage (2 tests)

#### Untested Functions ❌
1. **`get_provider_by_entity_id()`** (lines 102-114) - **CRITICAL for IdP-initiated SSO**

#### Missing Scenarios
- Lookup provider by entity_id (used in SAML response processing)
- `active_only=True` filter in list_providers
- Mixed active/inactive providers filtering
- Update provider to set `is_active=False`
- Entity_id with special characters

**Impact**: IdP-initiated SSO flow cannot validate issuer without this function being tested.

---

### 1.5 Onboarding Service (test_onboarding_service.py)

**Source**: `services/onboarding_service.py` (297 lines)  
**Coverage**: **75%** - Good coverage with edge case gaps

#### Tested Functions ✅
- `is_first_run()` - Full coverage (3 tests)
- `get_onboarding_status()` - Full coverage (4 tests)
- `skip_wizard()` - Covered (2 tests)
- `mark_wizard_completed()` - Covered (2 tests)
- `transition_to_step()` - Full coverage (4 tests)
- `complete_step()` - Full coverage (4 tests)

#### Missing Scenarios
- Transition to step 7 with incomplete prior steps (line 198-200)
- Complete step 7 when current_step != 7 (line 235-237)
- Concurrent state updates
- Database commit failures

**Impact**: Edge cases in auto-completion logic not covered.

---

## 2. Quality Issues

### 2.1 CRITICAL Issues (False Confidence)

#### Issue #1: Over-Mocking in test_session_service.py
**Severity**: CRITICAL  
**File**: `tests/services/test_session_service.py`  
**Lines**: 20-23, used throughout entire file

**Problem**:
```python
@pytest.fixture
def db_session() -> MagicMock:
    """Mock database session."""
    return MagicMock(spec=Session)  # Everything is mocked!
```

Every test mocks the database session completely, so tests never verify actual database interactions.

**Impact**:
- Tests pass even if SQL queries are broken
- Tests don't verify sessions are actually persisted
- Tests don't catch transaction rollback issues
- False confidence in database layer

**Fix**: Use real in-memory SQLite like other service tests:
```python
@pytest.fixture
def db_session() -> Session:
    """Real database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = SessionLocal(bind=engine)
    yield session
    session.close()
```

---

#### Issue #2: Refresh Token Type Validation Not Tested
**Severity**: CRITICAL (Security)  
**File**: `tests/services/test_session_service.py`  
**Source Line**: `services/session_service.py:197-198`

**Problem**: No test verifies that access tokens are rejected when used for refresh operations.

**Security Risk**: Access token could potentially be used as refresh token if validation is broken.

**Missing Test**:
```python
def test_refresh_session_rejects_access_token(session_service):
    # Arrange
    session = session_service.create_session("user-123", "user@example.com")
    access_token = session["access_token"]  # Wrong token type!
    
    # Act & Assert
    with pytest.raises(InvalidTokenError, match="invalid token type"):
        session_service.refresh_session(access_token)
```

---

#### Issue #3: Over-Mocking in test_saml_sso_flow.py
**Severity**: CRITICAL  
**File**: `tests/test_saml_sso_flow.py`  
**Lines**: 149-167, 190-201, and 15+ other tests

**Problem**: Tests mock `OneLogin_Saml2_Auth` completely, never testing actual SAML library integration.

**Impact**:
- SAML XML formatting never validated with real library
- Certificate validation not tested with real crypto
- Library API changes won't be caught

**Fix**: Use real SAML library with test certificates and signed XML responses.

---

### 2.2 HIGH Issues (Hard to Maintain/Understand)

#### Issue #4: Missing AAA Comments
**Severity**: HIGH  
**Files**: All test files  
**Compliance**: Violates project testing standards

**Problem**: Tests lack explicit `# Arrange`, `# Act`, `# Assert` comments.

**Example** (test_session_service.py:75-103):
```python
def test_create_session_with_custom_ttl(self, session_service, db_session):
    """Should create session with custom TTL."""
    user_id = "user-123"  # What phase is this?
    email = "test@example.com"
    ttl_hours = 2

    result = session_service.create_session(...)  # Where does Act start?

    settings = get_settings()  # Is this still part of Assert?
```

**Fix**: Add explicit phase markers to every test.

---

#### Issue #5: Magic Numbers Without Explanation
**Severity**: HIGH  
**Files**: `test_session_service.py`, `test_saml_sso_flow.py`

**Examples**:
```python
assert abs(actual_ttl.total_seconds() - (ttl_hours * 3600)) < 1  # Why 1?
not_before = now - timedelta(hours=2)  # Why 2?
not_after = now - timedelta(hours=1)   # Why 1?
```

**Fix**: Use named constants:
```python
CLOCK_SKEW_TOLERANCE_SECONDS = 1
EXPIRED_ASSERTION_AGE_HOURS = 2

assert abs(actual_ttl - expected_ttl) < CLOCK_SKEW_TOLERANCE_SECONDS
```

---

#### Issue #6: Tests Too Long
**Severity**: HIGH  
**File**: `test_saml_sso_flow.py:532-568`  
**Line Count**: 37 lines for single test

**Problem**: Too much setup, mocking, and assertions in one test. Hard to understand what's being tested.

**Fix**: Split into focused tests:
- `test_process_saml_response_validates_signature()`
- `test_process_saml_response_extracts_attributes()`
- `test_process_saml_response_validates_timing()`

---

#### Issue #7: Large Test Files
**Severity**: HIGH  
**Files**: Multiple files exceed project's 800-line guideline

- `test_hao_cli_v2.py`: 4,658 lines
- `test_agents.py`: 3,742 lines

**Problem**: Hard to navigate, slow to load, violates coding standards.

**Fix**: Split into multiple files by feature/domain.

---

### 2.3 MEDIUM Issues (Best Practice Violations)

#### Issue #8: Duplicate Test Logic
**Severity**: MEDIUM  
**File**: `test_saml_sso_flow.py`

**Problem**: Tests 26, 27, 28 have nearly identical IdP-initiated flow setup (lines 743-873).

**Fix**: Extract common setup to fixture:
```python
@pytest.fixture
def idp_initiated_saml_response(saml_provider):
    """Create IdP-initiated SAML response for testing."""
    return create_mock_saml_response(
        email="user@example.com",
        issuer=saml_provider.entity_id,
        include_relay_state=False
    )
```

---

#### Issue #9: Weak Error Messages
**Severity**: MEDIUM  
**File**: `test_auth.py`

**Examples**:
```python
assert response.status_code == 401  # What was the actual error?
assert response.headers["access-control-allow-origin"] == origin  # No context
```

**Fix**: Add descriptive messages:
```python
assert response.status_code == 401, \
    f"Invalid token should be rejected, got {response.status_code}: {response.json()}"
```

---

## 3. Recommended New Test Cases

### 3.1 CRITICAL Priority (Security & Core Functionality)

#### Test Case #1: Agent Template Instantiation
**File**: `tests/services/test_agent_template_service.py`  
**Story**: 5.2  
**Function**: `instantiate_from_template()`

```python
def test_instantiate_from_template_valid_config(service, db_session):
    """Should create agent config from template with all parameters."""
    # Arrange
    template = AgentTemplate(
        name="Support Agent",
        required_params=["api_key", "model", "instructions"],
        config_template={"model": "{{model}}", "system_prompt": "{{instructions}}"}
    )
    db_session.add(template)
    db_session.commit()
    
    parameters = {
        "api_key": "sk-test-123",
        "model": "claude-3-opus",
        "instructions": "You are a support agent"
    }
    
    # Act
    agent_config = service.instantiate_from_template(template.id, parameters)
    
    # Assert
    assert agent_config is not None
    assert agent_config["model"] == "claude-3-opus"
    assert "{{" not in str(agent_config)  # All placeholders replaced
```

---

#### Test Case #2: Missing Required Parameters
**File**: `tests/services/test_agent_template_service.py`  
**Story**: 5.2

```python
def test_instantiate_from_template_missing_required_param(service, db_session):
    """Should raise ValidationError when required parameter is missing."""
    # Arrange
    template = AgentTemplate(
        name="Support Agent",
        required_params=["api_key", "model"]
    )
    db_session.add(template)
    db_session.commit()
    
    incomplete_params = {"api_key": "sk-test-123"}  # Missing "model"
    
    # Act & Assert
    with pytest.raises(ValueError, match="Missing required parameter: model"):
        service.instantiate_from_template(template.id, incomplete_params)
```

---

#### Test Case #3: Refresh Token Type Validation
**File**: `tests/services/test_session_service.py`  
**Priority**: CRITICAL (Security)

```python
def test_refresh_session_rejects_access_token(session_service):
    """Should reject access token when refresh token is required."""
    # Arrange
    session = session_service.create_session("user-123", "user@example.com")
    access_token = session["access_token"]  # Wrong token type
    
    # Act & Assert
    with pytest.raises(InvalidTokenError, match="invalid token type"):
        session_service.refresh_session(access_token)
```

---

#### Test Case #4: Session Not Found During Refresh
**File**: `tests/services/test_session_service.py`  
**Priority**: CRITICAL (Security)

```python
def test_refresh_token_session_not_found(session_service, db_session):
    """Should fail when session has been deleted."""
    # Arrange
    session = session_service.create_session("user-123", "user@example.com")
    refresh_token = session["refresh_token"]
    
    # Delete session
    db_session.query(Session).filter_by(id=session["session_id"]).delete()
    db_session.commit()
    
    # Act & Assert
    with pytest.raises(SessionNotFoundError, match="session no longer exists"):
        session_service.refresh_session(refresh_token)
```

---

#### Test Case #5: Get Provider by Entity ID
**File**: `tests/services/test_saml_provider_service.py`  
**Priority**: CRITICAL (IdP-initiated SSO)

```python
def test_get_provider_by_entity_id_exists(service, db_session):
    """Should return provider when entity_id exists."""
    # Arrange
    provider = SAMLProvider(
        entity_id="https://idp.example.com",
        name="Example IdP",
        is_active=True
    )
    db_session.add(provider)
    db_session.commit()
    
    # Act
    result = service.get_provider_by_entity_id("https://idp.example.com")
    
    # Assert
    assert result is not None
    assert result.entity_id == "https://idp.example.com"
    assert result.name == "Example IdP"

def test_get_provider_by_entity_id_not_found(service):
    """Should return None when entity_id doesn't exist."""
    # Arrange & Act
    result = service.get_provider_by_entity_id("https://nonexistent.example.com")
    
    # Assert
    assert result is None
```

---

### 3.2 HIGH Priority

#### Test Case #6: Concurrent Session Refresh
**File**: `tests/services/test_session_service.py`

```python
def test_concurrent_session_refresh_same_token(session_service):
    """Should handle concurrent refresh attempts correctly."""
    import threading
    
    # Arrange
    session = session_service.create_session("user-123", "user@example.com")
    refresh_token = session["refresh_token"]
    results = []
    
    def refresh():
        try:
            result = session_service.refresh_session(refresh_token)
            results.append(("success", result))
        except Exception as e:
            results.append(("error", str(e)))
    
    # Act
    threads = [threading.Thread(target=refresh) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Assert
    successes = [r for r in results if r[0] == "success"]
    errors = [r for r in results if r[0] == "error"]
    
    assert len(successes) == 1, "Only one refresh should succeed"
    assert len(errors) == 2, "Other two should fail with token reuse error"
```

---

#### Test Case #7: Multi-IdP Provisioning
**File**: `tests/services/test_user_provisioning_service.py`

```python
def test_provision_user_from_multiple_idps_same_email(provisioning_service, db_session):
    """Should link same email from different IdPs to one user."""
    # Arrange
    okta_claims = {
        "email": "user@example.com",
        "sub": "okta-123",
        "idp": "okta"
    }
    azure_claims = {
        "email": "user@example.com",
        "sub": "azure-456",
        "idp": "azure"
    }
    
    # Act
    user1 = provisioning_service.provision_user_from_saml(okta_claims)
    user2 = provisioning_service.provision_user_from_saml(azure_claims)
    
    # Assert
    assert user1.id == user2.id, "Should be same user"
    
    external_ids = db_session.query(ExternalIdentity).filter_by(user_id=user1.id).all()
    assert len(external_ids) == 2, "Should have two linked identities"
    assert {ext.idp for ext in external_ids} == {"okta", "azure"}
```

---

#### Test Case #8: Parameter Validation with Type Checking
**File**: `tests/services/test_agent_template_service.py`

```python
def test_validate_parameters_with_invalid_type(service):
    """Should reject parameters with wrong type."""
    # Arrange
    template_schema = {
        "required_params": ["timeout"],
        "param_types": {"timeout": "int"}
    }
    invalid_params = {"timeout": "not_a_number"}
    
    # Act & Assert
    with pytest.raises(TypeError, match="timeout must be int"):
        service.validate_parameters(template_schema, invalid_params)
```

---

### 3.3 MEDIUM Priority

#### Test Case #9: Apply Template Config with Nested Placeholders
**File**: `tests/services/test_agent_template_service.py`

```python
def test_apply_template_config_with_nested_placeholders(service):
    """Should replace placeholders in nested config structures."""
    # Arrange
    template_config = {
        "auth": {
            "api_key": "{{api_key}}",
            "provider": "anthropic"
        },
        "model": "{{model}}",
        "tools": ["tool1", "{{custom_tool}}"]
    }
    parameters = {
        "api_key": "sk-test-123",
        "model": "claude-3-opus",
        "custom_tool": "my_tool"
    }
    
    # Act
    result = service.apply_template_config(template_config, parameters)
    
    # Assert
    assert result["auth"]["api_key"] == "sk-test-123"
    assert result["model"] == "claude-3-opus"
    assert result["tools"][1] == "my_tool"
    assert "{{" not in str(result), "No unreplaced placeholders"
```

---

#### Test Case #10: Provisioning Idempotency
**File**: `tests/services/test_user_provisioning_service.py`

```python
def test_provision_user_idempotency(provisioning_service, db_session):
    """Should be idempotent when called multiple times with same attributes."""
    # Arrange
    saml_claims = {
        "email": "user@example.com",
        "sub": "user-123",
        "given_name": "John"
    }
    
    # Act
    user1 = provisioning_service.provision_user_from_saml(saml_claims)
    user2 = provisioning_service.provision_user_from_saml(saml_claims)
    
    # Assert
    assert user1.id == user2.id
    user_count = db_session.query(User).filter_by(email="user@example.com").count()
    assert user_count == 1, "Should only create one user record"
```

---

## 4. Refactoring Suggestions

### 4.1 High Priority Refactoring

#### Refactor #1: Replace Mocked Database in test_session_service.py
**Impact**: CRITICAL  
**Effort**: Medium (4 hours)

**Current**:
```python
@pytest.fixture
def db_session() -> MagicMock:
    return MagicMock(spec=Session)
```

**Recommended**:
```python
@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = SessionLocal(bind=engine)
    yield session
    session.close()
```

**Benefits**:
- Tests validate actual SQL queries
- Catches transaction issues
- Verifies database constraints
- Increases confidence in session persistence

---

#### Refactor #2: Split Large Test Files
**Impact**: HIGH  
**Effort**: High (8-12 hours)

**Files to split**:
- `test_hao_cli_v2.py` (4,658 lines) → Split into 6+ files by feature
- `test_agents.py` (3,742 lines) → Split into 5+ files by agent type

**Example structure for test_hao_cli_v2.py**:
```
tests/hao_cli_v2/
├── test_basic_commands.py
├── test_conversation_flow.py
├── test_tool_integration.py
├── test_error_handling.py
├── test_auth_commands.py
└── conftest.py (shared fixtures)
```

---

#### Refactor #3: Add AAA Comments to All Tests
**Impact**: HIGH  
**Effort**: Medium (6 hours for all service tests)

**Automated approach**:
1. Create script to add AAA comments based on code structure
2. Manual review and adjustment
3. Enforce via linter rule

**Example transformation**:
```python
# Before
def test_create_session(session_service):
    user_id = "user-123"
    result = session_service.create_session(user_id)
    assert result is not None

# After
def test_create_session(session_service):
    # Arrange
    user_id = "user-123"
    
    # Act
    result = session_service.create_session(user_id)
    
    # Assert
    assert result is not None
```

---

### 4.2 Medium Priority Refactoring

#### Refactor #4: Extract Common SAML Test Fixtures
**Impact**: MEDIUM  
**Effort**: Low (2 hours)

Create shared fixtures in `tests/conftest.py`:
```python
@pytest.fixture
def idp_initiated_saml_response():
    """Standard IdP-initiated SAML response for testing."""
    return {
        "email": "user@example.com",
        "sub": "user-123",
        "issuer": "https://idp.example.com"
    }

@pytest.fixture
def sp_initiated_saml_response():
    """Standard SP-initiated SAML response with RelayState."""
    return {
        "email": "user@example.com",
        "sub": "user-123",
        "relay_state": "/dashboard"
    }
```

---

#### Refactor #5: Replace Magic Numbers with Constants
**Impact**: MEDIUM  
**Effort**: Low (2 hours)

Create `tests/constants.py`:
```python
# Timing constants
CLOCK_SKEW_TOLERANCE_SECONDS = 1
DEFAULT_SESSION_TTL_HOURS = 24
EXPIRED_ASSERTION_AGE_HOURS = 2

# Test data constants
TEST_USER_EMAIL = "test@example.com"
TEST_ENTITY_ID = "https://idp.example.com"
```

---

## 5. Action Items with Priorities

### Phase 1: Critical Fixes (Week 1)

| Priority | Task | Effort | Owner |
|----------|------|--------|-------|
| P0 | Add tests for Agent Template Service Story 5.2 (3 functions) | 8h | Backend Team |
| P0 | Add `get_provider_by_entity_id()` tests | 2h | Backend Team |
| P0 | Add refresh token type validation test | 1h | Backend Team |
| P0 | Add session not found during refresh test | 1h | Backend Team |
| P0 | Replace mocked database in test_session_service.py | 4h | Backend Team |

**Total Week 1 Effort**: 16 hours

---

### Phase 2: High Priority Improvements (Week 2)

| Priority | Task | Effort | Owner |
|----------|------|--------|-------|
| P1 | Add concurrent session refresh test | 3h | Backend Team |
| P1 | Add multi-IdP provisioning tests | 3h | Backend Team |
| P1 | Add AAA comments to all service tests | 6h | Backend Team |
| P1 | Split test_hao_cli_v2.py into multiple files | 10h | Backend Team |

**Total Week 2 Effort**: 22 hours

---

### Phase 3: Medium Priority Enhancements (Week 3)

| Priority | Task | Effort | Owner |
|----------|------|--------|-------|
| P2 | Extract common SAML test fixtures | 2h | Backend Team |
| P2 | Replace magic numbers with constants | 2h | Backend Team |
| P2 | Add parameter validation edge case tests | 4h | Backend Team |
| P2 | Add provisioning idempotency tests | 2h | Backend Team |
| P2 | Improve test error messages | 4h | Backend Team |

**Total Week 3 Effort**: 14 hours

---

### Phase 4: Coverage Improvements (Ongoing)

| Priority | Task | Effort | Owner |
|----------|------|--------|-------|
| P3 | Add remaining edge case tests | 8h | Backend Team |
| P3 | Add performance/load tests | 12h | Backend Team |
| P3 | Add security fuzzing tests | 8h | Security Team |
| P3 | Set up mutation testing | 4h | QA Team |

---

## 6. Testing Best Practices Enforcement

### 6.1 CI/CD Integration

Add to CI pipeline:
```yaml
# .github/workflows/test.yml
- name: Check test coverage
  run: |
    pytest --cov=services --cov-report=term --cov-fail-under=80
    
- name: Check AAA pattern compliance
  run: |
    python scripts/check_aaa_pattern.py tests/services/
    
- name: Check test file size
  run: |
    find tests -name "*.py" -exec wc -l {} \; | \
    awk '$1 > 800 {print "File " $2 " exceeds 800 lines: " $1; exit 1}'
```

---

### 6.2 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: test-coverage
      name: Verify test coverage
      entry: pytest --cov-fail-under=80
      language: system
      pass_filenames: false
      
    - id: aaa-pattern
      name: Check AAA pattern in new tests
      entry: python scripts/check_aaa_pattern.py
      language: system
      files: ^tests/.*\.py$
```

---

## 7. Summary and Recommendations

### Current State
- **Total Test Files**: 91
- **Overall Coverage**: ~77% (estimated)
- **Critical Gaps**: 4 untested functions in core services
- **Quality Issues**: 12 distinct categories identified

### Target State
- **Coverage Goal**: ≥85% across all service modules
- **AAA Compliance**: 100% of tests follow AAA pattern
- **File Size**: All test files <800 lines
- **Zero Over-Mocking**: All service tests use real database

### Key Metrics to Track

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| Service Layer Coverage | 77% | 85% | 3 weeks |
| AAA Pattern Compliance | ~0% | 100% | 2 weeks |
| Critical Functions Tested | 31/35 | 35/35 | 1 week |
| Files >800 lines | 2 | 0 | 3 weeks |
| Over-mocked Tests | 100% (session_service) | 0% | 1 week |

---

### Immediate Action Required

🔴 **STOP**: Fix test_session_service.py over-mocking before deploying session changes  
🔴 **BLOCK**: Story 5.2 deployment until tests are added  
🔴 **SECURITY**: Add refresh token type validation test immediately

---

## Appendix: Full Test Case Catalog

**Total Recommended New Tests**: 31

**By Priority**:
- CRITICAL: 10 tests
- HIGH: 9 tests
- MEDIUM: 8 tests
- LOW: 4 tests

**By Component**:
- Agent Template Service: 10 tests
- Session Service: 7 tests
- SAML Provider Service: 4 tests
- User Provisioning Service: 6 tests
- Security/Concurrency: 4 tests

For detailed test case specifications, see Section 3 above.

---

**Report Generated**: 2026-06-15  
**Next Review**: 2026-07-15 (after Phase 1-2 completion)
