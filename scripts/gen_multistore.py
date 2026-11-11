# -*- coding: utf-8 -*-
"""由 config/sources.json 生成仓库根目录的两个接口文件与 SOURCES.md。
产物全部自动生成，请勿手改；要增删线路请编辑 config/sources.json。
- tvbox_config.json       完整版：storeHouse + urls 双格式（影视仓/TVBox 与 OK影视/FongMi 通用）
- tvbox_config_lite.json  精简版：纯 urls 格式，只含标记 "lite": true 的主力线路
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CONFIG_FILE, ROOT

COMPAT_LABEL = {"tvbox": "影视仓/TVBox", "fongmi": "OK影视/FongMi", "both": "通用"}


def load_entries():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_storehouse(entries):
    return {"storeHouse": [
        {"sourceName": e["name"], "sourceUrl": e["url"]}
        for e in entries if e.get("compat") in ("tvbox", "both")
    ]}


def build_urls(entries):
    return {"urls": [
        {"url": e["url"], "name": e["name"]}
        for e in entries if e.get("compat") in ("fongmi", "both")
    ]}


def build_lite(entries):
    return {"urls": [
        {"url": e["url"], "name": e["name"]}
        for e in entries if e.get("lite") and e.get("compat") in ("fongmi", "both")
    ]}


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:  # 自检：产物必须能重新加载
        json.load(f)


def write_all(entries=None):
    """生成根目录 tvbox_config.json / tvbox_config_lite.json + SOURCES.md。"""
    if entries is None:
        entries = load_entries()
    full = {"storeHouse": build_storehouse(entries)["storeHouse"],
            "urls": build_urls(entries)["urls"]}
    lite = build_lite(entries)
    _dump(os.path.join(ROOT, "tvbox_config.json"), full)
    _dump(os.path.join(ROOT, "tvbox_config_lite.json"), lite)

    md = ["# 线路清单（自动生成，请勿手改）", "",
          "数据源：[config/sources.json](config/sources.json)，由 `scripts/gen_multistore.py` 生成。",
          "`lite=true` 的条目会进入精简版 tvbox_config_lite.json。", "",
          "| # | 线路 | 适用壳 | 进精简版 | 地址 |", "|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        md.append("| %d | %s | %s | %s | `%s` |"
                  % (i, e["name"], COMPAT_LABEL.get(e.get("compat"), "?"),
                     "是" if e.get("lite") else "", e["url"]))
    with open(os.path.join(ROOT, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return entries


def main():
    entries = write_all()
    full_sh = len(build_storehouse(entries)["storeHouse"])
    full_ur = len(build_urls(entries)["urls"])
    lite_n = len(build_lite(entries)["urls"])
    print("OK  entries=%d  tvbox_config(storeHouse=%d, urls=%d)  tvbox_config_lite(urls=%d)"
          % (len(entries), full_sh, full_ur, lite_n))


if __name__ == "__main__":
    main()
