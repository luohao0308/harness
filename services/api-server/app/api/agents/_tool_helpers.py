"""Workspace tool-call parsing, execution summary, and trace helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._workspace_chat_helpers import _require_normal_chat_content

def _normalize_tool_mention_payload(tool_name: str, payload: dict, goal: str) -> dict:
    if tool_name == "mcp_context_search" and "query" not in payload:
        return {**payload, "query": goal, "limit": int(payload.get("limit", 5) or 5)}
    if (
        tool_name
        and tool_name not in ToolRegistry.default().tools
        and "query" not in payload
    ):
        return {**payload, "query": goal, "limit": int(payload.get("limit", 5) or 5)}
    if tool_name == "list_files" and "root" not in payload:
        return {**payload, "root": ".", "glob": str(payload.get("glob", "**/*"))}
    if tool_name == "read_file" and "path" not in payload:
        return {**payload, "path": "pyproject.toml"}
    return payload


def _extract_function_call_tool_mentions(content: str) -> list[ToolMention]:
    mentions: list[ToolMention] = []
    for block in FUNCTION_CALLS_BLOCK_RE.finditer(content):
        for invoke in FUNCTION_INVOKE_RE.finditer(block.group(0)):
            attrs = _xml_attributes(invoke.group("attrs"))
            tool_name = str(attrs.get("name") or attrs.get("tool") or "").strip()
            if not tool_name:
                continue
            payload: dict = {}
            for parameter in FUNCTION_PARAMETER_RE.finditer(invoke.group("body")):
                param_attrs = _xml_attributes(parameter.group("attrs"))
                param_name = str(param_attrs.get("name") or "").strip()
                if not param_name:
                    continue
                payload[param_name] = _coerce_xml_parameter_value(parameter.group("value"))
            mentions.append(
                ToolMention(
                    name=tool_name,
                    source="model_function_call",
                    payload=payload,
                )
            )
    return mentions


def _infer_workspace_search_tool_mentions(
    *,
    content: str,
    goal: str,
    registry: ToolRegistry,
) -> list[ToolMention]:
    if not _workspace_content_is_pending_search(content):
        return []
    tool_name = _select_workspace_search_tool(registry)
    if tool_name is None:
        return []
    query = _workspace_search_query(content=content, goal=goal)
    return [
        ToolMention(
            name=tool_name,
            source="model_implicit_search",
            payload={"query": query, "limit": 5},
        )
    ]


def _workspace_content_is_pending_search(content: str) -> bool:
    normalized = re.sub(r"\s+", "", content.casefold())
    if not normalized:
        return False
    search_markers = ("搜索", "查询", "search")
    pending_markers = (
        "正在搜索",
        "正在查询",
        "搜索中",
        "查询中",
        "请稍等",
        "稍等",
        "pleasewait",
        "searching",
        "lookingup",
    )
    result_markers = (
        "返回了",
        "结果如下",
        "摘要如下",
        "已拿到",
        "工具返回",
        "result1",
        "results:",
    )
    return (
        any(marker in normalized for marker in search_markers)
        and any(marker in normalized for marker in pending_markers)
        and not any(marker in normalized for marker in result_markers)
    )


def _select_workspace_search_tool(registry: ToolRegistry) -> str | None:
    candidates: list[tuple[int, str]] = []
    for name, metadata in registry.tools.items():
        if not _workspace_tool_can_run_without_approval(metadata):
            continue
        haystack = " ".join(
            [
                name,
                metadata.description,
                metadata.category,
                metadata.mcp_server or "",
                metadata.mcp_method or "",
            ]
        ).casefold()
        if not any(
            marker in haystack
            for marker in (
                "search",
                "搜索",
                "查询",
                "brave",
                "web",
                "tavily",
                "perplexity",
                "serp",
                "exa",
            )
        ):
            continue
        score = 0
        if "brave" in haystack:
            score += 100
        if "web" in haystack:
            score += 40
        if "search" in haystack or "搜索" in haystack or "查询" in haystack:
            score += 30
        if metadata.mcp_method and "search" in metadata.mcp_method.casefold():
            score += 20
        if name == "mcp_context_search":
            score -= 25
        candidates.append((score, name))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]


def _workspace_tool_can_run_without_approval(metadata: ToolMetadata) -> bool:
    return (
        metadata.source == "mcp"
        and metadata.risk_level == "low"
        and metadata.idempotent
        and not metadata.requires_sandbox
        and metadata.network_policy in {"none", "restricted"}
    )


def _workspace_search_query(*, content: str, goal: str) -> str:
    for pattern in (
        r"[“\"]([^”\"]{1,120})[”\"]",
        r"[‘']([^’']{1,120})[’']",
    ):
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
    return goal.strip() or content.strip()[:120]


def _strip_function_calls(content: str) -> str:
    return FUNCTION_CALLS_BLOCK_RE.sub("", content).strip()


def _resolve_workspace_tool_mention(
    mention: ToolMention,
    *,
    registry: ToolRegistry,
) -> ToolMention:
    if mention.name in registry.tools:
        return mention
    resolved_name = _resolve_workspace_tool_alias(mention.name, registry=registry)
    if resolved_name is None:
        return mention
    metadata = registry.tools.get(resolved_name)
    return mention.model_copy(
        update={
            "name": resolved_name,
            "source": metadata.source if metadata is not None else mention.source,
        }
    )


def _resolve_workspace_tool_alias(tool_name: str, *, registry: ToolRegistry) -> str | None:
    normalized = _tool_alias_key(tool_name)
    by_key = {_tool_alias_key(name): name for name in registry.tools}
    direct = by_key.get(normalized)
    if direct:
        return direct
    candidates: list[str] = []
    for suffix in ("_web_search", "_search", "_tool"):
        if normalized.endswith(suffix):
            candidates.append(normalized[: -len(suffix)])
    for candidate in candidates:
        if candidate in by_key:
            return by_key[candidate]
    for metadata in registry.tools.values():
        metadata_keys = {
            _tool_alias_key(metadata.name),
            _tool_alias_key(metadata.mcp_server or ""),
            _tool_alias_key(metadata.mcp_method or ""),
        }
        expanded = set(metadata_keys)
        for key in metadata_keys:
            if not key:
                continue
            expanded.add(f"{key}_search")
            expanded.add(f"{key}_web_search")
        if normalized in expanded:
            return metadata.name
    return None


def _tool_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _xml_attributes(raw_attrs: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in XML_ATTRIBUTE_RE.finditer(raw_attrs):
        value = match.group(2) if match.group(2) is not None else match.group(3)
        attrs[match.group(1).lower()] = html.unescape(value or "")
    return attrs


def _coerce_xml_parameter_value(raw_value: str) -> object:
    text = html.unescape(re.sub(r"<[^>]+>", "", raw_value).strip())
    if not text:
        return ""
    if text[:1] in {"{", "[", '"'} or text in {"true", "false", "null"}:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _workspace_tool_result_prompt(summaries: list[dict]) -> str:
    safe_summaries: list[dict] = []
    for summary in summaries[:8]:
        safe_summaries.append(
            {
                "tool_name": summary.get("tool_name"),
                "status": summary.get("status"),
                "input_json": summary.get("input_json"),
                "output_summary": summary.get("output_summary"),
                "error_message": summary.get("error_message"),
                "output_json": summary.get("output_json"),
            }
        )
    return json.dumps(safe_summaries, ensure_ascii=False, sort_keys=True, default=str)


def _workspace_tool_answer_with_visible_results(answer: str, summaries: list[dict]) -> str:
    content = _require_normal_chat_content(_strip_function_calls(answer))
    visible_summary = _workspace_visible_tool_result_summary(summaries)
    if not visible_summary:
        return content
    if _workspace_answer_claims_missing_tool_results(content):
        return visible_summary
    if _workspace_answer_mentions_tool_results(content, summaries):
        return content
    return f"{content.rstrip()}\n\n{visible_summary}"


def _workspace_answer_claims_missing_tool_results(content: str) -> bool:
    lowered = content.lower()
    missing_markers = (
        "无法直接查看",
        "无法查看返回",
        "无法查看具体",
        "无法看到返回",
        "无法看到具体",
        "无法获取具体",
        "不能直接查看",
        "没法直接查看",
        "没有看到返回",
        "没拿到具体",
        "看不到返回",
        "看不到具体",
        "把您看到的搜索结果告诉我",
        "提供一下搜索结果",
        "provide the search results",
        "cannot view the returned",
        "can't view the returned",
    )
    return any(marker in lowered for marker in missing_markers)


def _workspace_answer_mentions_tool_results(content: str, summaries: list[dict]) -> bool:
    normalized = content.casefold()
    for summary in summaries:
        for item in _workspace_tool_result_items(summary)[:3]:
            for key in ("title", "name", "snippet", "url"):
                value = str(item.get(key) or "").strip()
                if len(value) >= 12 and value.casefold() in normalized:
                    return True
    return False


def _workspace_visible_tool_result_summary(summaries: list[dict]) -> str:
    sections: list[str] = []
    for summary in summaries:
        if summary.get("status") != "SUCCESS":
            continue
        items = _workspace_tool_result_items(summary)
        if not items:
            continue
        tool_name = str(summary.get("tool_name") or "工具")
        input_json = (
            summary.get("input_json") if isinstance(summary.get("input_json"), dict) else {}
        )
        query = str(input_json.get("query") or "").strip()
        heading = f"`{tool_name}` 返回了 {len(items)} 条结果"
        if query:
            heading += f"（查询：{query}）"
        lines = [heading + "："]
        for index, item in enumerate(items[:5], start=1):
            title = str(item.get("title") or item.get("name") or item.get("id") or f"结果 {index}")
            snippet = str(item.get("snippet") or item.get("description") or item.get("text") or "")
            url = str(item.get("url") or item.get("link") or item.get("uri") or "")
            lines.append(f"{index}. {title}")
            if snippet:
                lines.append(f"   {snippet[:500]}")
            if url:
                lines.append(f"   {url}")
        if len(items) > 5:
            lines.append(f"...还有 {len(items) - 5} 条未显示。")
        note = _workspace_tool_result_note(summary)
        if note:
            lines.append(f"备注：{note}")
        sections.append("\n".join(lines))
    if not sections:
        return ""
    return "已拿到 MCP 工具返回结果，摘要如下：\n\n" + "\n\n".join(sections)


def _workspace_tool_result_items(summary: dict) -> list[dict]:
    output_json = summary.get("output_json")
    if not isinstance(output_json, dict):
        return []
    candidates = [
        output_json.get("items"),
        (output_json.get("result") if isinstance(output_json.get("result"), dict) else {}).get(
            "items"
        ),
        output_json.get("results"),
        (output_json.get("result") if isinstance(output_json.get("result"), dict) else {}).get(
            "results"
        ),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _workspace_tool_result_note(summary: dict) -> str:
    output_json = summary.get("output_json")
    if not isinstance(output_json, dict):
        return ""
    result = output_json.get("result")
    if isinstance(result, dict):
        return str(result.get("note") or "").strip()
    return str(output_json.get("note") or "").strip()

def _trace_id_for_tool_call(tool_call_id: str, *, session: Session) -> str | None:
    event = (
        session.execute(
            select(AgentEvent)
            .where(AgentEvent.payload_json["tool_call_id"].as_string() == tool_call_id)
            .order_by(AgentEvent.sequence.desc())
        )
        .scalars()
        .first()
    )
    return event.trace_id if event is not None else None


def _trace_ids_by_subject(*, events: list[AgentEvent]) -> dict[tuple[str, str], str]:
    trace_ids: dict[tuple[str, str], str] = {}
    for event in events:
        if not isinstance(event.trace_id, str):
            continue
        model_call_id = event.payload_json.get("model_call_id")
        if isinstance(model_call_id, str):
            trace_ids.setdefault(("model", model_call_id), event.trace_id)
        tool_call_id = event.payload_json.get("tool_call_id")
        if isinstance(tool_call_id, str):
            trace_ids.setdefault(("tool", tool_call_id), event.trace_id)
    return trace_ids


def _workspace_tool_status(status_value: str) -> str:
    return {
        "SUCCESS": "success",
        "FAILED": "failed",
        "TIMEOUT": "failed",
        "DENIED": "rejected",
        "PENDING_APPROVAL": "pending_approval",
        "RUNNING": "running",
    }.get(status_value, status_value.lower())

def _tool_output_kind(tool_call: ToolCall, output: dict) -> str:
    if tool_call.status == "DENIED":
        return "policy_denied"
    if tool_call.status == "TIMEOUT":
        return "timeout"
    if "content" in output:
        return "file_content"
    if "files" in output:
        return "file_list"
    if "exit_code" in output:
        return "shell_result"
    if "status_code" in output:
        return "http_response"
    if "path" in output and "bytes_written" in output:
        return "file_write"
    if tool_call.status == "FAILED":
        return "error"
    return "empty" if not output else "json"


def _tool_output_summary(tool_call: ToolCall, output: dict) -> str:
    if tool_call.error_message and tool_call.status in {"DENIED", "FAILED", "TIMEOUT"}:
        return tool_call.error_message[:300]
    if "content" in output:
        content = str(output.get("content") or "")
        return f"文件内容 {len(content)} 字符"
    if "files" in output and isinstance(output.get("files"), list):
        return f"文件列表 {len(output['files'])} 项"
    if "exit_code" in output:
        return f"命令退出码 {output.get('exit_code')}"
    if "status_code" in output:
        return f"HTTP {output.get('status_code')}"
    if "path" in output and "bytes_written" in output:
        return f"写入 {output.get('path')}，{output.get('bytes_written')} bytes"
    if not output:
        return "无输出"
    return f"JSON 输出字段 {len(output)} 个"

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
