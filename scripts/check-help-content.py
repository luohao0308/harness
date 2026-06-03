#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELP_ROOT = ROOT / "apps/agent-console/public/help"
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
OLD_ENGLISH_PHRASES = [
    "Getting Started",
    "Specialist routing",
    "Troubleshooting",
    "Symptom:",
    "Check ",
    "Fix ",
    "Logs live",
    "Cost dashboard",
    "Trace explorer",
    "Alerts and channels",
    "Users and RBAC",
    "Retention, export",
    "Agent Console",
    "Agent Studio",
    "Agent Workspace",
    "Agent Run",
    "Run Detail",
    "Prompt Manifest",
    "Run Manifest",
    "Context Manifest",
    "Tool Call",
    "Demo Run",
    "Demo Task",
    "Team Mode",
    "Is this a chatbot",
    "Does every task",
    "What is the safest",
]


def fail(message: str) -> None:
    print(f"help content check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    index_path = HELP_ROOT / "index.json"
    if not index_path.is_file():
        fail("missing public/help/index.json")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    docs = index.get("docs")
    categories = index.get("categories")
    if not isinstance(categories, list) or len(categories) < 8:
        fail("index must define at least 8 categories")
    for category in categories:
        if not isinstance(category, str) or not CHINESE_PATTERN.search(category):
            fail(f"help category must be Chinese: {category}")
    if not isinstance(docs, list) or len(docs) < 20:
        fail("index must define at least 20 documents")
    seen_ids: set[str] = set()
    expert_hits = 0
    for doc in docs:
        if not isinstance(doc, dict):
            fail("doc entries must be objects")
        doc_id = str(doc.get("id") or "")
        title = str(doc.get("title") or "")
        path = str(doc.get("path") or "")
        keywords = doc.get("keywords")
        if not doc_id or doc_id in seen_ids:
            fail(f"duplicate or missing doc id: {doc_id}")
        seen_ids.add(doc_id)
        if not title or not path.startswith("/help/") or not isinstance(keywords, list):
            fail(f"invalid doc metadata for {doc_id}")
        if not CHINESE_PATTERN.search(title):
            fail(f"help document title must include Chinese: {doc_id}")
        if not CHINESE_PATTERN.search(" ".join(str(item) for item in keywords)):
            fail(f"help document keywords must include Chinese: {doc_id}")
        file_path = ROOT / "apps/agent-console/public" / path.removeprefix("/")
        if not file_path.is_file():
            fail(f"indexed help document missing: {path}")
        text = file_path.read_text(encoding="utf-8")
        chinese_chars = len(CHINESE_PATTERN.findall(text))
        if chinese_chars < 120:
            fail(f"help document has too little Chinese content: {path}")
        for phrase in OLD_ENGLISH_PHRASES:
            if phrase in text:
                fail(f"help document contains old English help prose '{phrase}': {path}")
        combined = " ".join([title, *[str(item) for item in keywords], text])
        if "专家" in combined or "子智能体" in combined:
            expert_hits += 1
    troubleshooting = HELP_ROOT / "troubleshooting.md"
    cases = [
        line
        for line in troubleshooting.read_text(encoding="utf-8").splitlines()
        if line.startswith("### ")
    ]
    if len(cases) < 50:
        fail("troubleshooting.md must contain at least 50 cases")
    if expert_hits < 3:
        fail("search corpus must include 专家 or 子智能体 in at least 3 documents")
    print(f"help content ok: docs={len(docs)} troubleshooting_cases={len(cases)} chinese_docs={len(docs)}")


if __name__ == "__main__":
    main()
