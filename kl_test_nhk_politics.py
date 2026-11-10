"""試験（指示 2026-11-10-016 の1）: NHK の政治ニュースが除外され、科学・技術系が残ることを、直近プール・採点済み候補・NHK RSS の実物で確かめる。
使い方: python3 kl_test_nhk_politics.py [--live]   （--live は NHK の RSS を取得して cat3=科学・文化 / cat4=政治 / cat6=国際 を判定）"""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

import kl_news_scan as ns

ok = True


def check(name, cond):
    global ok
    print(("OK  " if cond else "NG  ") + name)
    ok = ok and cond


# 単体
pol = [{"title": "高市首相 G7オンライン会議欠席", "source": "NHK 科学・文化"},
       {"title": "トランプ大統領 イランとの戦闘再開「必要性極めて低い」", "source": "Googleニュース（x）／NHK", "outlet": "NHK"},
       {"title": "消費税減税法案 参院であす審議入り", "url": "https://news.web.nhk/newsweb/na/nd-1"},
       {"title": "政府 補助金の見直しへ", "source": "NHK 科学・文化"}]
sci = [{"title": "風疹ウイルス感染の“入り口”発見 予防や治療法の開発に期待", "source": "NHK 科学・文化"},
       {"title": "政府 AIロボット導入の研究開発を支援へ", "source": "NHK 科学・文化"},
       {"title": "ニトリに不正アクセス 最大3762万件の個人情報が流出の可能性", "source": "NHK 科学・文化"}]
other = [{"title": "高市首相 AI規制へ", "source": "ITmedia NEWS"}]
for p in pol:
    check("除外: " + p["title"][:30], bool(ns.nhk_politics_reason(p)))
for p in sci:
    check("残る: " + p["title"][:30], not ns.nhk_politics_reason(p))
for p in other:
    check("NHK以外は対象外: " + p["title"][:30], not ns.nhk_politics_reason(p))

# 直近プール
pool = json.loads(ns.POOL_JSON.read_text(encoding="utf-8"))["items"]
nhk = [p for p in pool if ns.is_nhk(p)]
ex = [p for p in nhk if ns.nhk_politics_reason(p)]
print(f"\n直近プール {len(pool)}件のうち NHK {len(nhk)}件、政治で除外 {len(ex)}件、残る {len(nhk) - len(ex)}件")
for p in nhk:
    if not ns.nhk_politics_reason(p):
        print("   残: " + p["title"][:60])
check("プールの NHK 記事（旧 cat6=国際）のうち政治16件が除外される", len(ex) >= 16)
check("政治でない NHK 記事（物価・事故・Nvidia CEO 調査）は残る", len(nhk) - len(ex) >= 1)
todo_after = [p for p in pool if not ns.nhk_politics_reason(p)]
check("採点対象から NHK の政治が消える", not any(ns.is_nhk(p) and ns.nhk_politics_reason(p) for p in todo_after))
others = [p for p in pool if not ns.is_nhk(p)]
check("NHK 以外の記事は1件も除外されない", all(not ns.nhk_politics_reason(p) for p in others))

# 採点枠（select_for_scoring）の前後比較: 除外なし vs あり（cmd_score と同じ前処理）
cand_all = ns.load_candidates()
known = {c["id"] for c in cand_all["items"]}
todo0 = [p for p in pool if p["id"] not in known and not (set(p.get("dup_ids") or []) & known)]
todo0 = [p for p in todo0 if not (ns._pool_age(p) is not None and ns._pool_age(p) > ns.SCORE_MAX_AGE_DAYS)]
before = ns.select_for_scoring(todo0, cand_all["items"], 15, verbose=False)
after = ns.select_for_scoring([p for p in todo0 if not ns.nhk_politics_reason(p)], cand_all["items"], 15, verbose=False)
nb = [p for p in before if ns.is_nhk(p)]
na = [p for p in after if ns.is_nhk(p)]
print(f"\n採点15件枠の NHK 記事: 除外なし {len(nb)}件 → あり {len(na)}件（政治で入っていたもの {sum(1 for p in nb if ns.nhk_politics_reason(p))}件）")
for p in nb:
    print("   旧: " + p["title"][:50] + ("  ← 政治" if ns.nhk_politics_reason(p) else ""))
check("採点15件枠に NHK の政治ニュースが入らない", not any(ns.nhk_politics_reason(p) for p in after))
check("枠は15件のまま埋まる", len(after) == len(before))
print("   非NHK で新たに枠に入った記事: " + str(len({p['id'] for p in after} - {p['id'] for p in before})) + "件")

# 採点済み候補
cands = ns.load_candidates()["items"]
cn = [c for c in cands if ns.is_nhk(c)]
print(f"\n採点済み候補 {len(cands)}件のうち NHK {len(cn)}件、ゲートで落ちる政治 {sum(1 for c in cn if ns.nhk_politics_reason(c))}件")
for c in cn:
    print(f"   {'×' if ns.nhk_politics_reason(c) else '残'} {c['title'][:50]}")

if "--live" in sys.argv:
    UA = {"User-Agent": "Mozilla/5.0"}
    print()
    for cat, label in ((3, "科学・文化"), (4, "政治"), (6, "国際")):
        root = ET.fromstring(urllib.request.urlopen(
            urllib.request.Request("https://www.nhk.or.jp/rss/news/cat%d.xml" % cat, headers=UA), timeout=20).read())
        titles = [(i.findtext("title") or "") for i in root.findall(".//item")]
        ex_t = [t for t in titles if ns.nhk_politics_reason({"title": t, "source": "NHK"})]
        keep = [t for t in titles if t not in ex_t]
        print(f"cat{cat}（{label}）: {len(titles)}件 → 除外 {len(ex_t)}件、残る {len(keep)}件")
        for t in keep[:10]:
            print("   残: " + t[:56])
        if cat == 3:
            for t in ex_t[:6]:
                print("   除: " + t[:56])

print("\n" + ("全OK" if ok else "NGあり"))
sys.exit(0 if ok else 1)
