# -*- coding: utf-8 -*-
"""每日复测 + 内容镜像（GitHub Actions 定时跑，也可本地手动运行）：
1. 逐源尝试「主线 + 备用」多条地址，抓取上游最新配置内容
2. 成功的源把最新内容快照到 output/<id>.json（本仓库自托管；相对路径的 spider/jar/ext 会改写为上游绝对地址，快照可独立使用）
3. 失效计入 check_history.json；连续 DEAD_DAYS 天失效的自动移除（同时删除其快照）
4. 重新生成根目录 tvbox_config.json / tvbox_config_lite.json / tvbox_config_merged.json 与 SOURCES.md
5. 写 reports/YYYY-MM-DD.md 与 reports/status.json
"""
import datetime
import json
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (HISTORY_FILE, REPORTS_DIR, SNAPSHOT_DIR, TIMEOUT,
                    fetch, lenient_parse, load_sources, load_text, save_sources)
import gen_multistore as G

DEAD_DAYS = 3
TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _abs_url(base, v):
    """把 ./ 或 ../ 开头的相对地址改写为基于上游 base 目录的绝对地址。"""
    if not isinstance(v, str):
        return v
    v2 = v.strip()
    if v2.startswith("./") or v2.startswith("../"):
        return urllib.parse.urljoin(base, v2)
    return v


def _rewrite_relative(j, url_used):
    """镜像快照前，把内容里指向上游的相对路径（spider/jar/ext/wallpaper/logo）改写为绝对地址，
    否则快照放到自己仓库后 ./xxx.jar 会解析到自己仓库而 404。"""
    if not isinstance(j, dict):
        return j
    base = urllib.parse.urljoin(url_used, "./")
    for k in ("spider", "wallpaper", "logo"):
        v = j.get(k)
        if not isinstance(v, str):
            continue
        head, sep, tail = v.partition(";")
        if head.strip().startswith(("./", "../")):
            j[k] = _abs_url(base, head) + (sep + tail if sep else "")
        else:
            j[k] = _abs_url(base, v)
    for st in (j.get("sites") or []):
        if not isinstance(st, dict):
            continue
        if "jar" in st:
            st["jar"] = _abs_url(base, st["jar"])
        if isinstance(st.get("ext"), str):
            st["ext"] = _abs_url(base, st["ext"])
    return j


def fetch_source(entry):
    """依次尝试一个源的多条地址，成功返回 (meta, content)，全部失败返回 (meta, None)。"""
    meta = {"id": entry["id"], "name": entry["name"], "status": "dead", "url_used": "",
            "kind": "", "sites": 0, "lives": 0, "lines": 0, "spider": False,
            "streak": 0, "detail": ""}
    last_err = ""
    for url in entry.get("urls", []):
        for _attempt in range(2):
            try:
                _st, data = fetch(url, TIMEOUT)
                txt = load_text(data).strip()
                try:
                    j = lenient_parse(txt)
                except ValueError:
                    raise ValueError("非JSON或JSON损坏: " + txt[:50].replace("\n", " "))
                if not isinstance(j, dict):
                    raise ValueError("JSON顶层非对象")
                lines_u = len(j.get("urls") or [])
                lines_sh = len(j.get("storeHouse") or [])
                sites = len(j.get("sites") or [])
                lives = len(j.get("lives") or [])
                if not (lines_u or lines_sh or sites or lives):
                    raise ValueError("JSON无有效内容")
                is_multi = bool(lines_u or lines_sh)
                meta.update({"status": "ok", "url_used": url,
                             "kind": "multi" if is_multi else "config",
                             "lines": lines_u or lines_sh, "sites": sites, "lives": lives,
                             "spider": bool(j.get("spider")),
                             "detail": ("多仓=%d线路" % (lines_u or lines_sh)) if is_multi
                                       else "sites=%d lives=%d" % (sites, lives)})
                return meta, _rewrite_relative(j, url)
            except ValueError as e:
                last_err = str(e)
            except Exception as e:
                last_err = "%s %s" % (type(e).__name__, str(e)[:50])
    meta["detail"] = last_err[:80]
    return meta, None


def main():
    entries = load_sources()
    hist = {"dead_streak": {}, "history": {}}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            hist = json.load(f)
    hist.setdefault("dead_streak", {})
    hist.setdefault("history", {})

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(fetch_source, entries))

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    day = {}
    recovered = []
    for entry, (meta, content) in zip(entries, results):
        name = entry["name"]
        if meta["status"] == "ok":
            if hist["dead_streak"].get(name, 0) > 0:
                recovered.append(name)
            hist["dead_streak"].pop(name, None)
            with open(os.path.join(SNAPSHOT_DIR, entry["id"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            hist["dead_streak"][name] = hist["dead_streak"].get(name, 0) + 1
        meta["streak"] = hist["dead_streak"].get(name, 0)
        day[name] = {k: meta[k] for k in ("status", "kind", "sites", "lives", "lines", "detail")}

    removed = [e["name"] for e, (m, _c) in zip(entries, results)
               if hist["dead_streak"].get(e["name"], 0) >= DEAD_DAYS]
    if removed:
        removed_ids = [e["id"] for e in entries if e["name"] in removed]
        keep = [(e, r) for e, r in zip(entries, results) if e["name"] not in removed]
        entries = [e for e, _r in keep]
        results = [r for _e, r in keep]
        save_sources(entries)
        for n in removed:
            hist["dead_streak"].pop(n, None)
        for rid in removed_ids:
            p = os.path.join(SNAPSHOT_DIR, rid + ".json")
            if os.path.exists(p):
                os.remove(p)

    hist["history"][TODAY] = day
    for k in sorted(hist["history"].keys())[:-30]:
        hist["history"].pop(k, None)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

    metas = [m for _e, (m, _c) in zip(entries, results)]
    G.write_all(entries, metas)

    ok_n = sum(1 for m in metas if m["status"] == "ok")
    dead_n = len(metas) - ok_n
    os.makedirs(REPORTS_DIR, exist_ok=True)
    status = {"date": TODAY, "checked_at": NOW_ISO,
              "total": len(metas), "ok": ok_n, "dead": dead_n,
              "removed": removed, "recovered": recovered, "entries_now": len(entries),
              "sources": {m["id"]: {k: m[k] for k in ("name", "status", "url_used", "kind",
                                                       "sites", "lives", "lines", "spider", "streak")}
                          for m in metas}}
    with open(os.path.join(REPORTS_DIR, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    rep = ["# 每日复测报告 %s" % TODAY, "",
           "- 总计 %d 条：可用 %d，失效 %d" % (len(metas), ok_n, dead_n),
           "- 移除（连续 %d 天失效）：%s" % (DEAD_DAYS, "、".join(removed) if removed else "无"),
           "- 恢复：%s" % ("、".join(recovered) if recovered else "无"),
           "",
           "| # | 线路 | 结果 | 实测规模 | 实际使用地址 | 备注 |", "|---|---|---|---|---|---|"]
    for i, m in enumerate(metas, 1):
        mark = "可用" if m["status"] == "ok" else "失效"
        note = ("连续失效%d天" % m["streak"]) if m["streak"] else ""
        rep.append("| %d | %s | %s | %s | `%s` | %s |"
                   % (i, m["name"], mark, m["detail"] or "-", m["url_used"] or "-", note))
    with open(os.path.join(REPORTS_DIR, "%s.md" % TODAY), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")

    print("== 每日复测+镜像完成 %s ==" % TODAY)
    print("总计 %d | 可用 %d | 失效 %d | 移除 %d | 恢复 %d"
          % (len(metas), ok_n, dead_n, len(removed), len(recovered)))
    for m in metas:
        print("%-4s %-26s %s" % ("OK" if m["status"] == "ok" else "DEAD",
                                 m["name"], (m["detail"] or "")[:56]))
    if removed:
        print("已移除: " + "、".join(removed))


if __name__ == "__main__":
    main()
