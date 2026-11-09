#!/usr/bin/env python3
"""
kl_chrome_guard.py — kl_related_auto.py が起動する claude -p に掛ける PreToolUse ガード（KLリポジトリ内で完結）

claude の PreToolUse フック（matcher: mcp__claude-in-chrome__*）として、標準入力の JSON を検査する。
  - 期待する制作専用 Chrome の device_id（環境変数 KL_CHROME_DEVICE_ID）が無ければ拒否（blocked）。
  - ツール入力に device_id / deviceId があり、期待値と違えば拒否。
  - ブラウザの切り替え系ツール（switch_browser 等）は拒否（制作専用以外へ移らない）。
  - ツール入力に含まれる URL のホストが studio.youtube.com / www.youtube.com 以外なら拒否。
拒否したときは KL_GUARD_MARK のファイルに理由を書く（runner が blocked として報告する）。回避はしない。
終了コード 2 + stderr = 拒否、0 = 許可。
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS = {"studio.youtube.com", "www.youtube.com"}
SWITCH_RE = re.compile(r"switch|select_browser|list_browsers|connect", re.I)
URL_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")


def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k, v
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield "", v   # リスト内の値（文字列を含む）も検査対象にする
            yield from walk(v)


def check(data, expected_device):
    """None なら許可、文字列なら拒否理由。"""
    if not expected_device:
        return "制作専用 Chrome の device_id が特定できない"
    tool = str(data.get("tool_name", ""))
    inp = data.get("tool_input") or {}
    if SWITCH_RE.search(tool.split("__")[-1]):
        return f"ブラウザ切り替え系ツールは使えない: {tool}"
    for k, v in walk(inp):
        if str(k) in ("device_id", "deviceId") and v and str(v) != expected_device:
            return "device_id が制作専用 Chrome と一致しない"
    texts = [v for _, v in walk(inp) if isinstance(v, str)]
    for t in texts:
        for u in URL_RE.findall(t):
            p = urlparse(u)
            if p.scheme not in ("https", "http") or (p.hostname or "").lower() not in ALLOWED_HOSTS:
                return f"接続先が許可外: {p.hostname or u[:40]}"
        if t.strip().lower().startswith(("javascript:", "file:", "chrome:", "about:")) and "://" not in t:
            return "許可外のスキーム"
    for k, v in walk(inp):
        if str(k).lower() in ("url", "urls") and isinstance(v, str) and v and "://" not in v:
            return f"URL を判定できない: {v[:40]}"   # 例: 「evil.com」のようなスキーム無し指定
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
        reason = "ガード入力を読めない"
    else:
        try:
            reason = check(data, os.environ.get("KL_CHROME_DEVICE_ID", ""))   # 例外は拒否扱い（fail-closed）
            seen = os.environ.get("KL_GUARD_SEEN")
            if seen and isinstance(data, dict):   # ガードが動いた証拠（ツール名と入力キー名）
                ti = data.get("tool_input")
                with open(seen, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"tool": data.get("tool_name"),
                                        "keys": sorted(ti) if isinstance(ti, dict) else None,
                                        "verdict": reason or "allow"}, ensure_ascii=False) + "\n")
        except Exception as exc:
            reason = f"ガード内部エラー: {type(exc).__name__}"
    if reason:
        mark = os.environ.get("KL_GUARD_MARK")
        if mark:
            try:
                Path(mark).write_text(reason, encoding="utf-8")
            except Exception:
                pass
        print(f"ガードにより拒否（回避せず中断し、RESULT blocked で終えること）: {reason}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


def selftest():
    nav = lambda u: {"tool_name": "mcp__claude-in-chrome__navigate", "tool_input": {"url": u}}
    cases = [
        ("許可: studio", nav("https://studio.youtube.com/video/x/edit"), "d1", True),
        ("許可: www.youtube.com", nav("https://www.youtube.com/watch?v=x"), "d1", True),
        ("拒否: 許可外ホスト", nav("https://evil.example.com/"), "d1", False),
        ("拒否: 似たホスト", nav("https://studio.youtube.com.evil.com/"), "d1", False),
        ("拒否: スキーム無しURL", nav("evil.com"), "d1", False),
        ("拒否: device_id 未特定", nav("https://studio.youtube.com/"), "", False),
        ("拒否: ブラウザ切替", {"tool_name": "mcp__claude-in-chrome__switch_browser", "tool_input": {}}, "d1", False),
        ("拒否: 別 device", {"tool_name": "mcp__claude-in-chrome__tabs_create", "tool_input": {"deviceId": "x"}}, "d1", False),
        ("拒否: リスト内の外部URL", {"tool_name": "mcp__claude-in-chrome__x", "tool_input": {"urls": ["https://evil.example.com/"]}}, "d1", False),
        ("拒否: javascript 内の外部URL", {"tool_name": "mcp__claude-in-chrome__javascript_tool",
                                      "tool_input": {"text": "fetch('https://evil.example.com/x')"}}, "d1", False),
    ]
    bad = 0
    try:
        check([], "d1")   # dict でない入力で例外 → main では拒否扱い
        print("NG  非dict入力で例外にならない（main の try/except で拒否される）")
        bad += 1
    except Exception:
        print("OK  非dict入力は例外 → main で拒否（fail-closed）")
    for name, d, dev, ok in cases:
        r = check(d, dev)
        good = (r is None) == ok
        bad += not good
        print(("OK  " if good else "NG  ") + name + ("" if r is None else f" → {r}"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    main()
