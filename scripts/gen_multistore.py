# -*- coding: utf-8 -*-
"""由 config/sources.json + output/ 快照生成根目录接口产物（全部自动生成，请勿手改）。
- tvbox_config.json        完整版：storeHouse + urls 双格式，线路指向本仓库快照（每日自动更新）
- tvbox_config_lite.json   精简版：纯 urls，只含 "lite": true 的主力线路（同样指向本仓库快照）
- tvbox_config_merged.json 聚合单仓：全部单仓型源的 sites/lives/parses 等合并去重（多仓型源不参与）
- SOURCES.md               线路清单与最新状态
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_FILE, ROOT, SNAPSHOT_DIR

COMPAT_LABEL = {"tvbox": "影视仓/TVBox", "fongmi": "OK影视/FongMi", "both": "通用"}
# GitHub Actions 会自动注入 GITHUB_REPOSITORY=Kwei168/tvbox；本地运行用同一默认值
OWN_REPO = os.environ.get("GITHUB_REPOSITORY", "Kwei168/tvbox")
RAW_BASE = "https://raw.githubusercontent.com/%s/main" % OWN_REPO


def load_entries():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def snapshot_path(entry_id):
    return os.path.join(SNAPSHOT_DIR, entry_id + ".json")


def snapshot_url(entry_id):
    return RAW_BASE + "/output/" + entry_id + ".json"


def load_snapshots(entries):
    """读取每个源的本地快照，返回 {id: meta}；meta 含 ok/kind/sites/lives/lines/spider/content。"""
    snaps = {}
    for e in entries:
        meta = {"ok": False, "kind": "", "sites": 0, "lives": 0, "lines": 0,
                "spider": False, "content": None}
        p = snapshot_path(e["id"])
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    j = json.load(f)
                lines_u = len(j.get("urls") or [])
                lines_sh = len(j.get("storeHouse") or [])
                meta.update({"ok": True,
                             "kind": "multi" if (lines_u or lines_sh) else "config",
                             "lines": lines_u or lines_sh,
                             "sites": len(j.get("sites") or []),
                             "lives": len(j.get("lives") or []),
                             "spider": bool(j.get("spider")),
                             "content": j})
            except Exception:
                pass
        snaps[e["id"]] = meta
    return snaps


def build_storehouse(entries, snaps):
    return {"storeHouse": [
        {"sourceName": e["name"], "sourceUrl": snapshot_url(e["id"])}
        for e in entries
        if e.get("compat") in ("tvbox", "both") and snaps[e["id"]]["ok"]
    ]}


def build_urls(entries, snaps):
    return {"urls": [
        {"url": snapshot_url(e["id"]), "name": e["name"]}
        for e in entries
        if e.get("compat") in ("fongmi", "both") and snaps[e["id"]]["ok"]
    ]}


def build_lite(entries, snaps):
    return {"urls": [
        {"url": snapshot_url(e["id"]), "name": e["name"]}
        for e in entries
        if e.get("lite") and e.get("compat") in ("fongmi", "both") and snaps[e["id"]]["ok"]
    ]}


def _item_ident(item):
    if isinstance(item, dict):
        return (item.get("name") or item.get("url")
                or json.dumps(item, ensure_ascii=False, sort_keys=True))
    return str(item)


def build_merged(entries, snaps):
    """聚合全部单仓型源：第一个成功源做基底（保留其 spider 等全局字段），
    其余源的 sites/lives/parses/rules/flags/doh/ijk 合并去重。
    所有源的站点 key 全局唯一：重复 key 加源 id 前缀（仍冲突则继续加前缀）；
    无 key 的站点按 name 去重。其他源若依赖自己的 spider jar，
    会给缺少 jar 字段的站点补上该源的 jar（相对路径已在快照阶段改写为绝对地址）。"""
    merged = None
    base_spider = ""
    seen_keys = set()
    seen_lists = {}
    for e in entries:
        s = snaps[e["id"]]
        if not s["ok"] or s["kind"] != "config":
            continue
        data = s["content"]
        if merged is None:
            merged = {k: (list(v) if isinstance(v, list) else v)
                      for k, v in data.items() if k != "sites"}
            merged["sites"] = []
            merged.setdefault("lives", [])
            base_spider = str(data.get("spider") or "")
            jar = ""
            for field in ("lives", "parses", "rules", "flags", "doh", "ijk"):
                seen = seen_lists.setdefault(field, set())
                for item in (data.get(field) or []):
                    seen.add(_item_ident(item))
        else:
            src_spider = str(data.get("spider") or "")
            jar = src_spider.split(";")[0] if (src_spider and src_spider != base_spider) else ""
        for st in (data.get("sites") or []):
            k = st.get("key")
            if k:
                if k in seen_keys:
                    nk = "%s_%s" % (e["id"], k)
                    while nk in seen_keys:
                        nk = "x_" + nk
                    st = dict(st)
                    st["key"] = nk
                    seen_keys.add(nk)
                else:
                    seen_keys.add(k)
            else:
                ident = "name:" + str(st.get("name", ""))
                if ident in seen_keys:
                    continue
                seen_keys.add(ident)
            if jar and not st.get("jar"):
                st = dict(st)
                st["jar"] = jar
            merged["sites"].append(st)
        for field in ("lives", "parses", "rules", "flags", "doh", "ijk"):
            seen = seen_lists.setdefault(field, set())
            out = merged.setdefault(field, [])
            for item in (data.get(field) or []):
                ident = _item_ident(item)
                if ident in seen:
                    continue
                seen.add(ident)
                out.append(item)
    return merged


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:  # 自检：产物必须能重新加载
        json.load(f)


def write_all(entries=None, metas=None):
    """生成根目录三个接口产物 + SOURCES.md。
    metas：每日复测传入的最新状态（可空；为空时状态列按本地快照推断）。"""
    if entries is None:
        entries = load_entries()
    snaps = load_snapshots(entries)
    full = {"storeHouse": build_storehouse(entries, snaps)["storeHouse"],
            "urls": build_urls(entries, snaps)["urls"]}
    lite = build_lite(entries, snaps)
    _dump(os.path.join(ROOT, "tvbox_config.json"), full)
    _dump(os.path.join(ROOT, "tvbox_config_lite.json"), lite)
    merged = build_merged(entries, snaps)
    merged_sites = len((merged or {}).get("sites") or [])
    if merged_sites:
        _dump(os.path.join(ROOT, "tvbox_config_merged.json"), merged)

    status_by_id = {m["id"]: m for m in (metas or [])}
    md = ["# 线路清单与最新状态（自动生成，请勿手改）", "",
          "数据源：[config/sources.json](config/sources.json)，由 `scripts/gen_multistore.py` 生成。",
          "接口产物中的线路指向本仓库快照 `output/<id>.json`（每日自动抓取上游最新内容）。", "",
          "| # | 线路 | 适用壳 | 精简版 | 聚合 | 最新状态 | 上游主线 |", "|---|---|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        s = snaps[e["id"]]
        m = status_by_id.get(e["id"])
        if m:
            state = ("正常 " + (m["detail"] or "")) if m["status"] == "ok" else \
                    ("失效%s %s" % (("（连续%d天）" % m["streak"]) if m["streak"] else "",
                                   m["detail"] or ""))
        else:
            state = ("快照正常 " + (s["detail"] if False else
                     ("多仓=%d线路" % s["lines"] if s["kind"] == "multi"
                      else "sites=%d lives=%d" % (s["sites"], s["lives"]))) if s["ok"]
                     else "快照缺失（待每日复测）")
        in_agg = "是" if (s["ok"] and s["kind"] == "config") else "—"
        md.append("| %d | %s | %s | %s | %s | %s | `%s` |"
                  % (i, e["name"], COMPAT_LABEL.get(e.get("compat"), "?"),
                     "是" if e.get("lite") else "", in_agg, state, e["urls"][0]))
    with open(os.path.join(ROOT, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return {"entries": len(entries), "storehouse": len(full["storeHouse"]),
            "urls": len(full["urls"]), "lite": len(lite["urls"]), "merged_sites": merged_sites}


def main():
    stat = write_all()
    print("OK  entries=%(entries)d  tvbox_config(storeHouse=%(storehouse)d, urls=%(urls)d)"
          "  lite(urls=%(lite)d)  merged(sites=%(merged_sites)d)" % stat)


if __name__ == "__main__":
    main()
