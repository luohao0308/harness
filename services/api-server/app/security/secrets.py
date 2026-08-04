from __future__ import annotations

import base64
import hashlib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - production dependency guard
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]

from app.core.config import get_settings
from app.db.models import StoredSecret, utc_now

SECRET_SCOPE_USER = "user"
SECRET_SCOPE_ORG = "org"
SECRET_SOURCE_USER = "stored_secret_user"
SECRET_SOURCE_ORG = "stored_secret_org"

SECRET_PURPOSE_MODEL_PROVIDER = "model_provider"
SECRET_PURPOSE_KNOWLEDGE_CONNECTOR = "knowledge_connector"
SECRET_PURPOSE_MCP_RUNTIME = "mcp_runtime"
SECRET_PURPOSE_WEB_RESEARCH = "web_research"
SECRET_PURPOSE_NOTIFICATION = "notification_channel"

SECRET_PURPOSES = {
    SECRET_PURPOSE_MODEL_PROVIDER,
    SECRET_PURPOSE_KNOWLEDGE_CONNECTOR,
    SECRET_PURPOSE_MCP_RUNTIME,
    SECRET_PURPOSE_WEB_RESEARCH,
    SECRET_PURPOSE_NOTIFICATION,
}


class SecretStoreError(RuntimeError):
    pass


class SecretEncryptionError(SecretStoreError):
    pass


@dataclass(frozen=True)
class SecretResolution:
    value: str
    source: str
    secret_id: str | None = None
    scope: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.value)


def normalize_secret_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("secret key value is required")
    return normalized[:128]


def encrypted_secret_configured() -> bool:
    if Fernet is None and get_settings().app_env.strip().lower() in {"development", "test"}:
        return True
    try:
        _fernet()
        return True
    except SecretEncryptionError:
        return False


def encrypt_secret(value: str) -> str:
    if Fernet is None:
        return _fallback_encrypt(value)
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    if value.startswith("dev-fallback:"):
        return _fallback_decrypt(value)
    if Fernet is None:
        raise SecretEncryptionError("cryptography is required to decrypt stored secrets")
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretEncryptionError("stored secret cannot be decrypted") from exc


def upsert_secret(
    session: Session,
    *,
    organization_id: str,
    actor_id: str | None,
    scope: str,
    provider: str,
    purpose: str,
    secret_value: str,
    owner_user_id: str | None = None,
    secret_ref: str | None = None,
) -> StoredSecret:
    normalized_scope = _validate_scope(scope)
    normalized_provider = normalize_secret_key(provider)
    normalized_purpose = _validate_purpose(purpose)
    value = secret_value.strip()
    if not value:
        raise ValueError("secret_value is required")
    if len(value.encode("utf-8")) > 10_000:
        raise ValueError("secret_value is too large")
    owner = owner_user_id if normalized_scope == SECRET_SCOPE_USER else None
    if normalized_scope == SECRET_SCOPE_USER and not owner:
        raise ValueError("owner_user_id is required for user scoped secrets")
    existing = _active_secret(
        session,
        organization_id=organization_id,
        scope=normalized_scope,
        owner_user_id=owner,
        provider=normalized_provider,
        purpose=normalized_purpose,
    )
    now = utc_now()
    encrypted_value = encrypt_secret(value)
    key_id = get_settings().harness_secret_encryption_key_id.strip() or "local-v1"
    if existing is None:
        existing = StoredSecret(
            organization_id=organization_id,
            owner_user_id=owner,
            scope=normalized_scope,
            provider=normalized_provider,
            purpose=normalized_purpose,
            secret_ref=_clean_secret_ref(secret_ref),
            encrypted_value=encrypted_value,
            encryption_key_id=key_id,
            status="active",
            created_by=actor_id,
            updated_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.secret_ref = _clean_secret_ref(secret_ref) or existing.secret_ref
        existing.encrypted_value = encrypted_value
        existing.encryption_key_id = key_id
        existing.updated_by = actor_id
        existing.updated_at = now
    session.flush()
    return existing


def resolve_secret(
    session: Session | None,
    *,
    organization_id: str | None,
    user_id: str | None,
    provider: str,
    purpose: str,
    env_candidates: Iterable[str] = (),
) -> SecretResolution:
    if organization_id and session is not None:
        normalized_provider = normalize_secret_key(provider)
        normalized_purpose = _validate_purpose(purpose)
        if user_id:
            user_secret = _active_secret(
                session,
                organization_id=organization_id,
                scope=SECRET_SCOPE_USER,
                owner_user_id=user_id,
                provider=normalized_provider,
                purpose=normalized_purpose,
            )
            if user_secret is not None:
                return _resolution_from_row(session, user_secret, SECRET_SOURCE_USER)
        org_secret = _active_secret(
            session,
            organization_id=organization_id,
            scope=SECRET_SCOPE_ORG,
            owner_user_id=None,
            provider=normalized_provider,
            purpose=normalized_purpose,
        )
        if org_secret is not None:
            return _resolution_from_row(session, org_secret, SECRET_SOURCE_ORG)
    if get_settings().legacy_env_secret_fallback_enabled:
        for candidate in env_candidates:
            env_name = candidate.strip()
            if not env_name:
                continue
            value = os.environ.get(env_name, "").strip()
            if value:
                return SecretResolution(value=value, source="env_legacy")
    return SecretResolution(value="", source="missing")


def list_secrets(
    session: Session,
    *,
    organization_id: str,
    user_id: str,
    include_org: bool,
) -> list[StoredSecret]:
    statement = select(StoredSecret).where(
        StoredSecret.organization_id == organization_id,
        StoredSecret.status == "active",
    )
    if include_org:
        statement = statement.where(
            (StoredSecret.scope == SECRET_SCOPE_ORG)
            | (
                (StoredSecret.scope == SECRET_SCOPE_USER)
                & (StoredSecret.owner_user_id == user_id)
            )
        )
    else:
        statement = statement.where(
            StoredSecret.scope == SECRET_SCOPE_USER,
            StoredSecret.owner_user_id == user_id,
        )
    return list(
        session.execute(
            statement.order_by(
                StoredSecret.scope.asc(),
                StoredSecret.provider.asc(),
                StoredSecret.purpose.asc(),
            )
        ).scalars()
    )


def disable_secret(
    session: Session,
    *,
    organization_id: str,
    actor_id: str | None,
    secret_id: str,
    allow_org: bool,
) -> StoredSecret | None:
    row = session.get(StoredSecret, secret_id)
    if row is None or row.organization_id != organization_id:
        return None
    if row.scope == SECRET_SCOPE_ORG and not allow_org:
        return None
    if row.scope == SECRET_SCOPE_USER and row.owner_user_id != actor_id:
        return None
    row.status = "disabled"
    row.updated_by = actor_id
    row.updated_at = utc_now()
    session.flush()
    return row


def env_candidates_for_provider(provider: str, configured_env: str | None = None) -> list[str]:
    candidates = []
    if configured_env:
        candidates.append(configured_env)
    slug = re.sub(r"[^A-Z0-9]+", "_", provider.strip().upper()).strip("_")
    if slug:
        candidates.extend([f"{slug}_API_KEY", f"{slug}_KEY"])
    aliases = {
        "chybenzun-openai-compatible": ["AI_PROVIDER_API_KEY"],
        "deepseek-flash": ["DEEPSEEK_API_KEY"],
        "deepseek-pro": ["DEEPSEEK_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
        "openai-compatible": ["OPENAI_API_KEY"],
        "dify": ["DIFY_API_KEY", "DIFY_CLOUD_API_KEY", "DIFY_KNOWLEDGE_API_KEY"],
        "coze": ["COZE_API_KEY", "COZE_PAT", "COZE_PERSONAL_ACCESS_TOKEN"],
        "tavily": ["TAVILY_API_KEY"],
    }
    candidates.extend(aliases.get(provider.strip().lower(), []))
    deduped: list[str] = []
    for candidate in candidates:
        name = candidate.strip().upper()
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def _active_secret(
    session: Session,
    *,
    organization_id: str,
    scope: str,
    owner_user_id: str | None,
    provider: str,
    purpose: str,
) -> StoredSecret | None:
    statement = select(StoredSecret).where(
        StoredSecret.organization_id == organization_id,
        StoredSecret.scope == scope,
        StoredSecret.provider == provider,
        StoredSecret.purpose == purpose,
        StoredSecret.status == "active",
    )
    if scope == SECRET_SCOPE_USER:
        statement = statement.where(StoredSecret.owner_user_id == owner_user_id)
    else:
        statement = statement.where(StoredSecret.owner_user_id.is_(None))
    return session.execute(statement).scalar_one_or_none()


def _resolution_from_row(session: Session, row: StoredSecret, source: str) -> SecretResolution:
    row.last_used_at = utc_now()
    session.flush()
    return SecretResolution(
        value=decrypt_secret(row.encrypted_value),
        source=source,
        secret_id=row.id,
        scope=row.scope,
    )


def _validate_scope(scope: str) -> str:
    normalized = scope.strip().lower()
    if normalized not in {SECRET_SCOPE_USER, SECRET_SCOPE_ORG}:
        raise ValueError("scope must be user or org")
    return normalized


def _validate_purpose(purpose: str) -> str:
    normalized = normalize_secret_key(purpose)
    if normalized not in SECRET_PURPOSES:
        raise ValueError("unsupported secret purpose")
    return normalized


def _clean_secret_ref(secret_ref: str | None) -> str | None:
    if not isinstance(secret_ref, str):
        return None
    value = secret_ref.strip()
    return value[:500] if value else None


def _fernet() -> Fernet:
    if Fernet is None:
        if get_settings().app_env.strip().lower() in {"development", "test"}:
            raise SecretEncryptionError("cryptography is unavailable; using fallback cipher")
        raise SecretEncryptionError("cryptography is required for encrypted secrets")
    settings = get_settings()
    raw_key = settings.harness_secret_encryption_key.strip()
    if not raw_key:
        env = settings.app_env.strip().lower()
        if env in {"development", "test"}:
            raw_key = "dev-only-harness-secret-encryption-key"
        else:
            raise SecretEncryptionError("HARNESS_SECRET_ENCRYPTION_KEY is required")
    try:
        return Fernet(raw_key.encode("utf-8"))
    except Exception:
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def _fallback_key() -> bytes:
    settings = get_settings()
    raw_key = (
        settings.harness_secret_encryption_key.strip()
        or "dev-only-harness-secret-encryption-key"
    )
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def _fallback_encrypt(value: str) -> str:
    if get_settings().app_env.strip().lower() not in {"development", "test"}:
        raise SecretEncryptionError("cryptography is required for encrypted secrets")
    key = _fallback_key()
    data = value.encode("utf-8")
    encrypted = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))
    return "dev-fallback:" + base64.urlsafe_b64encode(encrypted).decode("utf-8")


def _fallback_decrypt(value: str) -> str:
    if get_settings().app_env.strip().lower() not in {"development", "test"}:
        raise SecretEncryptionError("cryptography is required to decrypt stored secrets")
    key = _fallback_key()
    data = base64.urlsafe_b64decode(value.removeprefix("dev-fallback:").encode("utf-8"))
    decrypted = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))
    return decrypted.decode("utf-8")
