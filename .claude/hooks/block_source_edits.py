#!/usr/bin/env python3
"""java-database PreToolUse 훅 — Claude 가 핵심 코드(*.java)를 대신 쓰는 것을 차단.

이 repo 는 사용자가 KV DB 로우 레벨을 직접 손으로 짜는 학습 프로젝트다
(CLAUDE.md "절대 규칙"). Claude 가 실수로/요청받아 src 코드를 작성하면 학습 목적이
파괴되므로, Write/Edit/NotebookEdit 이 `*.java` 를 대상으로 하면 exit 2 로 막는다.

- 차단 대상: tool_input.file_path 가 .java 로 끝나는 Write/Edit/MultiEdit/NotebookEdit
- 허용: 그 외 전부 (md 문서, .gitignore, 빌드설정, 진단 스크립트 = LLM 잡일 영역)
- 의식적 우회 (사용자가 명시적으로 스캐폴딩을 원할 때):
    JDB_ALLOW_CLAUDE_CODE=1
"""

import json
import os
import sys

# Windows cp949 stdout 에 한글/이모지 못 찍는 문제 회피 (private/.githooks/pre-commit 와 동일)
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

BLOCK_SUFFIXES = (".java",)


def main() -> int:
    if os.environ.get("JDB_ALLOW_CLAUDE_CODE") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 입력 파싱 실패 시 막지 않음 (안전망이지 게이트 아님)

    tool = payload.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or ""
    )
    norm = str(path).replace("\\", "/").lower()

    if norm.endswith(BLOCK_SUFFIXES):
        print(
            "❌ 차단: 이 repo 는 KV DB 핵심 로직을 **사용자가 직접** 짜는 학습 프로젝트다"
            " (CLAUDE.md 절대 규칙).\n"
            f"   Claude 는 {os.path.basename(str(path))} 같은 *.java 소스를 대신 작성하지 않는다.\n"
            "   → 대신: 개념·함정·표준 API/자료구조 이름·DDIA 챕터 포인터만 제공하고, 코드는 사용자가.\n"
            "   (정말 스캐폴딩이 필요하면 사용자가 의식적으로 JDB_ALLOW_CLAUDE_CODE=1 설정)",
            file=sys.stderr,
        )
        return 2  # PreToolUse: exit 2 = 도구 호출 차단, stderr 를 Claude 에 피드백

    return 0


if __name__ == "__main__":
    sys.exit(main())
