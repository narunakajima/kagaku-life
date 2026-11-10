"""診断（指示 2026-11-10-016）: NHK の RSS の各カテゴリが何を返すかを見る。"""
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0"}
for c in (3, 4, 6):
    u = "https://www.nhk.or.jp/rss/news/cat%d.xml" % c
    try:
        root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read())
        its = root.findall(".//item")
        print("cat%d: %d件 / channel=%s" % (c, len(its), root.findtext(".//channel/title")))
        for i in its[:12]:
            print("   ", (i.findtext("title") or "")[:60])
    except Exception as e:
        print("cat%d: 失敗 %s" % (c, e))
