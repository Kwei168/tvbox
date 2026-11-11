# -*- coding: utf-8 -*-
"""每日复测（GitHub Actions 定时跑，也可本地手动运行）：
1. 实测 config/sources.json 中全部线路
2. 失效计入 check_history.json；连续 DEAD_DAYS 天失效的自动移除；恢复的清零计数
3. 重新生成根目录 tvbox_config.json / tvbox_config_lite.json；写 reports/YYYY-MM-DD.md 与 reports/status.json
"""
import datetime
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HISTORY_FILE, REPORTS_DIR, describe, load_sources, save_sources
import gen_multistore as G

DEAD_DAYS = 3
TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def main():
    entries = load_sources()
    hist = {"dead_streak": {}, "history": {}}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            hist = json.load(f)
    hist.setdefault("dead_streak", {})
    hist.setdefault("history", {})

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda e: (e, describe(e["url"])), entries))

    removed, recovered = [], []
    day = {}
    for e, r in results:
        name = e["name"]
        day[name] = {"status": r["status"], "kind": r.get("kind", ""),
                     "sites": r.get("sites", 0), "lives": r.get("lives", 0),
                     "lines": r.get("lines", 0), "detail": (r.get("detail") or "")[:80]}
        if r["status"] == "ok":
            if hist["dead_streak"].get(name, 0) > 0:
                recovered.append(name)
            hist["dead_streak"].pop(name, None)
        else:
            hist["dead_streak"][name] = hist["dead_streak"].get(name, 0) + 1

    for e, r in results:
        if hist["dead_streak"].get(e["name"], 0) >= DEAD_DAYS:
            removed.append(e["name"])
    if removed:
        entries = [e for e in entries if e["name"] not in removed]
        save_sources(entries)
        for n in removed:
            hist["dead_streak"].pop(n, None)

    hist["history"][TODAY] = day
    for k in sorted(hist["history"].keys())[:-30]:
        hist["history"].pop(k, None)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

    G.write_all(entries)

    ok_n = sum(1 for _, r in results if r["status"] == "ok")
    dead_n = len(results) - ok_n
    status = {
        "date": TODAY,
        "total": len(results), "ok": ok_n, "dead": dead_n,
        "removed": removed, "recovered": recovered,
        "entries_now": len(entries),
    }
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    rep = ["# 每日复测报告 %s" % TODAY, "",
           "- 总计 %d 条：可用 %d，失效 %d" % (len(results), ok_n, dead_n),
           "- 移除（连续 %d 天失效）：%s" % (DEAD_DAYS, "、".join(removed) if removed else "无"),
           "- 恢复：%s" % ("、".join(recovered) if recovered else "无"),
           "",
           "| # | 线路 | 结果 | 实测规模 | 备注 |", "|---|---|---|---|---|"]
    for i, (e, r) in enumerate(results, 1):
        if r["status"] == "ok":
            mark = "可用"
            scale = ("多仓%d线路" % r["lines"]) if r.get("lines") else \
                    ("sites=%d lives=%d" % (r.get("sites", 0), r.get("lives", 0)))
        else:
            mark = "失效"
            scale = "-"
        rep.append("| %d | %s | %s | %s | %s |"
                   % (i, e["name"], mark, scale, (r.get("detail") or "")[:50]))
    with open(os.path.join(REPORTS_DIR, "%s.md" % TODAY), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")

    print("== 每日复测完成 %s ==" % TODAY)
    print("总计 %d | 可用 %d | 失效 %d | 移除 %d | 恢复 %d"
          % (len(results), ok_n, dead_n, len(removed), len(recovered)))
    for e, r in results:
        print("%-4s %-26s %s" % ("OK" if r["status"] == "ok" else "DEAD",
                                 e["name"], (r.get("detail") or "")[:56]))
    if removed:
        print("已移除: " + "、".join(removed))


if __name__ == "__main__":
    main()
