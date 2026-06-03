from __future__ import annotations

import asyncio
import json
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib import request
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertEvent, NotificationChannel
from app.security.secrets import SECRET_PURPOSE_NOTIFICATION, resolve_secret

SECRET_KEYS = {"password", "token", "secret", "webhook_url", "smtp_password"}


@dataclass(frozen=True)
class NotificationDispatchResult:
    channel_id: str
    kind: str
    status: str
    error_message: str | None = None


def redact_channel_config(config: dict | None) -> dict:
    redacted = {}
    for key, value in (config or {}).items():
        if key.lower() in SECRET_KEYS:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def validate_channel_config(*, kind: str, config: dict | None, verified: bool) -> None:
    config = config or {}
    if kind in {"slack", "webhook"}:
        webhook_url = str(config.get("webhook_url") or config.get("url") or "")
        webhook_ref = str(
            config.get("webhook_url_secret_ref") or config.get("url_secret_ref") or ""
        )
        if verified and not (webhook_url or webhook_ref):
            raise ValueError("verified Slack/Webhook channels require webhook_url")
        if webhook_url:
            _validate_http_url(webhook_url)
    elif kind == "email":
        if verified and (not config.get("to") or not config.get("smtp_host")):
            raise ValueError("verified email channels require to and smtp_host")
    else:
        raise ValueError(f"unsupported channel kind: {kind}")


def dispatch_alert_event(
    *,
    session: Session,
    event: AlertEvent,
    channel_selectors: list[str],
) -> list[NotificationDispatchResult]:
    channels = _resolve_channels(
        session=session,
        organization_id=event.organization_id,
        selectors=channel_selectors,
    )
    results = [
        _dispatch_one(session=session, channel=channel, payload=_alert_payload(event, channel))
        for channel in channels
    ]
    event.context_json = {
        **(event.context_json or {}),
        "notification_dispatch": [
            {
                "channel_id": result.channel_id,
                "kind": result.kind,
                "status": result.status,
                "error_message": result.error_message,
            }
            for result in results
        ],
    }
    return results


def _resolve_channels(
    *,
    session: Session,
    organization_id: str | None,
    selectors: list[str],
) -> list[NotificationChannel]:
    external_selectors = [selector for selector in selectors if selector != "in_app"]
    if not external_selectors or organization_id is None:
        return []
    kinds = {selector.split(":", 1)[0] for selector in external_selectors if ":" in selector}
    statement = select(NotificationChannel).where(
        NotificationChannel.organization_id == organization_id,
        NotificationChannel.verified.is_(True),
    )
    if kinds:
        statement = statement.where(NotificationChannel.kind.in_(sorted(kinds)))
    candidates = list(session.execute(statement).scalars())
    return [
        channel
        for channel in candidates
        if any(_selector_matches_channel(selector, channel) for selector in external_selectors)
    ]


def _selector_matches_channel(selector: str, channel: NotificationChannel) -> bool:
    if ":" not in selector:
        return False
    kind, target = selector.split(":", 1)
    if kind != channel.kind:
        return False
    if kind == "email":
        return target == "*" or target == str(channel.config_json.get("to") or "")
    if kind == "slack":
        return target == "*" or target == str(channel.config_json.get("channel") or channel.name)
    return target == "*" or target == channel.name or target == channel.id


def _alert_payload(event: AlertEvent, channel: NotificationChannel) -> dict[str, Any]:
    return {
        "type": "harness.alert",
        "channel_id": channel.id,
        "organization_id": event.organization_id,
        "alert_event_id": event.id,
        "rule_id": event.rule_id,
        "rule_name": event.rule_name,
        "severity": event.severity,
        "status": event.status,
        "message": event.message,
        "metric": event.metric,
        "observed_value": event.observed_value,
        "threshold": event.threshold,
        "triggered_at": event.triggered_at.isoformat(),
    }


def _dispatch_one(
    *,
    session: Session,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> NotificationDispatchResult:
    try:
        if channel.kind == "slack":
            _dispatch_slack(session, channel, payload)
        elif channel.kind == "email":
            _dispatch_email(session, channel, payload)
        elif channel.kind == "webhook":
            _dispatch_webhook(session, channel, payload)
        else:
            raise ValueError(f"unsupported channel kind: {channel.kind}")
    except Exception as exc:
        return NotificationDispatchResult(
            channel_id=channel.id,
            kind=channel.kind,
            status="failed",
            error_message=str(exc),
        )
    return NotificationDispatchResult(channel_id=channel.id, kind=channel.kind, status="sent")


def _dispatch_slack(
    session: Session,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> None:
    webhook_url = _channel_secret(session, channel, "webhook_url") or str(
        channel.config_json.get("webhook_url") or ""
    )
    if not webhook_url:
        raise ValueError("missing Slack webhook_url")
    _validate_http_url(webhook_url)
    body = {
        "text": f"[{payload['severity']}] {payload['message']}",
        "channel": channel.config_json.get("channel"),
        "attachments": [{"text": json.dumps(payload, ensure_ascii=False)}],
    }
    _post_json(webhook_url, body)


def _dispatch_webhook(
    session: Session,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> None:
    webhook_url = (
        _channel_secret(session, channel, "webhook_url")
        or _channel_secret(session, channel, "url")
        or str(channel.config_json.get("webhook_url") or channel.config_json.get("url") or "")
    )
    if not webhook_url:
        raise ValueError("missing webhook url")
    _validate_http_url(webhook_url)
    _post_json(webhook_url, payload)


def _dispatch_email(
    session: Session,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> None:
    config = channel.config_json
    to_address = str(config.get("to") or "")
    host = str(config.get("smtp_host") or "")
    if not to_address or not host:
        raise ValueError("missing email to or smtp_host")
    message = EmailMessage()
    message["Subject"] = f"Harness alert: {payload['rule_name']}"
    message["From"] = str(config.get("from") or "harness-alerts@example.invalid")
    message["To"] = to_address
    message.set_content(json.dumps(payload, ensure_ascii=False, indent=2))
    password = _channel_secret(session, channel, "smtp_password") or config.get("smtp_password")
    if config.get("use_aiosmtplib"):
        _dispatch_email_async({**config, "smtp_password": password}, message)
        return
    with smtplib.SMTP(host, int(config.get("smtp_port") or 25), timeout=10) as smtp:
        if config.get("starttls"):
            smtp.starttls()
        username = config.get("smtp_username")
        if username and password:
            smtp.login(str(username), str(password))
        smtp.send_message(message)


def _dispatch_email_async(config: dict, message: EmailMessage) -> None:
    try:
        import aiosmtplib
    except ImportError as exc:
        raise RuntimeError("aiosmtplib is not installed") from exc

    async def send() -> None:
        await aiosmtplib.send(
            message,
            hostname=str(config.get("smtp_host")),
            port=int(config.get("smtp_port") or 25),
            username=config.get("smtp_username"),
            password=config.get("smtp_password"),
            start_tls=bool(config.get("starttls")),
            timeout=10,
        )

    asyncio.run(send())


def _post_json(url: str, payload: dict[str, Any]) -> None:
    http_request = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=10) as response:
        if response.status >= 400:
            raise RuntimeError(f"webhook returned HTTP {response.status}")


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("webhook_url must be an absolute HTTP(S) URL")


def _channel_secret(session: Session, channel: NotificationChannel, field: str) -> str:
    secret_ref = str(channel.config_json.get(f"{field}_secret_ref") or "").strip()
    if not secret_ref:
        return ""
    resolved = resolve_secret(
        session,
        organization_id=channel.organization_id,
        user_id=channel.created_by,
        provider=f"notification.{channel.id}.{field}",
        purpose=SECRET_PURPOSE_NOTIFICATION,
        env_candidates=[],
    )
    return resolved.value if resolved.found else ""
