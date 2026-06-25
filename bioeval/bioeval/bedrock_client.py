"""Shared AWS Bedrock Converse helpers for BioEval components."""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any

DEFAULT_BEDROCK_API_BASE = "bedrock:us-east-1"


def is_bedrock_api_base(api_base: str | None) -> bool:
    return bool(api_base and api_base.startswith("bedrock"))


def region_from_api_base(api_base: str | None) -> str | None:
    if api_base and api_base.startswith("bedrock:"):
        return api_base.split(":", 1)[1] or None
    return None


def bedrock_api_key_from_aws_credentials(
    profile: str | None = None,
    credentials_path: Path | None = None,
) -> str | None:
    credentials_path = credentials_path or Path(
        os.environ.get("AWS_SHARED_CREDENTIALS_FILE", Path.home() / ".aws" / "credentials")
    )
    if not credentials_path.exists():
        return None

    parser = configparser.RawConfigParser()
    parser.read(credentials_path)
    section = profile or os.environ.get("AWS_PROFILE") or "default"
    if not parser.has_section(section):
        return None

    token = parser.get(section, "aws_session_token", fallback="").strip()
    if token.startswith("ABSK"):
        return token
    return None


def ensure_bedrock_bearer_token(profile: str | None = None) -> None:
    if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        return
    token = bedrock_api_key_from_aws_credentials(profile)
    if token:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token


def prompt_cache_point() -> dict[str, Any] | None:
    raw = os.environ.get("BEDROCK_PROMPT_CACHE_TTL", "1h").strip()
    if raw.lower() in {"", "0", "false", "off", "none"}:
        return None
    cache_point: dict[str, Any] = {"type": "default"}
    if raw:
        cache_point["ttl"] = raw
    return {"cachePoint": cache_point}


def messages_with_cache_point(
    messages: list[dict[str, Any]],
    cache_point: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not cache_point or os.environ.get("BEDROCK_CACHE_CONVERSATION", "1").lower() in {
        "0",
        "false",
        "off",
        "none",
    }:
        return messages
    if not messages:
        return messages

    request_messages = [
        {"role": message["role"], "content": list(message.get("content", []))}
        for message in messages
    ]
    request_messages[-1]["content"].append(cache_point)
    return request_messages


def create_bedrock_client(api_base: str | None = None):
    import boto3
    from botocore.config import Config as BotoConfig

    profile = os.environ.get("AWS_PROFILE")
    ensure_bedrock_bearer_token(profile)
    session_kwargs = {"profile_name": profile} if profile else {}
    session = boto3.Session(**session_kwargs)
    region = (
        region_from_api_base(api_base)
        or os.environ.get("BEDROCK_AWS_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    return session.client(
        "bedrock-runtime",
        region_name=region,
        config=BotoConfig(
            connect_timeout=int(os.environ.get("BEDROCK_CONNECT_TIMEOUT", "10")),
            read_timeout=int(os.environ.get("BEDROCK_READ_TIMEOUT", "1800")),
            retries={"mode": "standard", "total_max_attempts": 1},
        ),
    )


def extract_text_from_response(response: dict[str, Any]) -> str:
    return "\n".join(
        item.get("text", "")
        for item in response.get("output", {}).get("message", {}).get("content", [])
        if isinstance(item, dict) and item.get("text")
    )
