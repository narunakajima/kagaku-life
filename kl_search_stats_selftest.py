"""kl_search_stats の動作確認（API を呼ばない）。python3 kl_search_stats_selftest.py"""
import json
import tempfile
from pathlib import Path

import kl_fact_check  # noqa: F401  構文・import 確認
import kl_news_scan   # noqa: F401
import kl_search_stats as k

k.LOG = Path(tempfile.mkdtemp()) / "log.json"


class Resp:
    def __init__(self, text):
        self.text = text
        self.candidates = []


class Client:
    calls = 0

    class models:
        @staticmethod
        def generate_content(model, contents):
            Client.calls += 1
            return Resp('{"a": 1}' if "整形" in contents else "x")


assert k.parse_with_reformat(Client, "m", Resp("not json"), json.loads, "t") == {"a": 1} and Client.calls == 1
assert k.parse_with_reformat(Client, "m", Resp('{"b": 2}'), json.loads, "t") == {"b": 2} and Client.calls == 1
Client.models.generate_content = staticmethod(lambda model, contents: Resp("still bad"))
try:
    k.parse_with_reformat(Client, "m", Resp("bad"), json.loads, "t")
    raise SystemExit("NG: 例外になるはず")
except json.JSONDecodeError:
    pass
try:
    k.parse_with_reformat(Client, "m", Resp(""), json.loads, "t")
    raise SystemExit("NG: 空応答は例外になるはず")
except ValueError:
    pass
Client.models.generate_content = staticmethod(lambda model, contents: Resp("{}"))
try:
    k.parse_with_reformat(Client, "m", Resp("bad"), json.loads, "t")
    raise SystemExit("NG: 空JSONは例外になるはず")
except ValueError:
    pass
t = json.loads(k.LOG.read_text(encoding="utf-8"))["totals"]["t"]
assert t == {"calls": 5, "queries": 0, "json_failed": 4, "reformat_ok": 1, "reformat_failed": 3}, t
print("OK", t)
