# -*- coding: utf-8 -*-
"""每周扫描 GitHub 新增影视仓/TVBox 接口源（GitHub Actions 定时跑；本地可 --dry-run 只测不改）。
流程：搜索近 30 天活跃仓库 → 抓 README 提取接口地址 → 归一化去重 → 并发实测 →
按门槛与评分收录最多 5 条 → 更新 config/sources.json 并重新生成根目录 tvbox_config.json / tvbox_config_lite.json → 写 reports/scan-YYYY-MM-DD.md。
Actions 中 GITHUB_TOKEN 自动注入，可大幅提升 API 限额。
"""
import base64
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CTX, REPORTS_DIR, TOKEN, USER_AGENT, describe, load_sources, save_sources
import gen_multistore as G

QUERIES = ["tvbox 接口", "影视仓 接口", "tvbox 配置", "OK影视 配置", "影视仓 多仓"]
RECENT_DAYS = 30
MAX_REPOS = 20
MAX_CANDIDATES = 30
ADD_MAX = 5
SKIP_PAT = re.compile(r"r18|18\+|porn|福利", re.I)
PROXY_PREFIXES = (
    "https://gh-proxy.com/", "https://gh-proxy.org/", "https://ghproxy.net/",
    "https://ghfast.top/", "https://ghp.ci/", "https://ghproxy.com/",
    "https://github.moeyy.xyz/",
)
TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def api(url):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def normalize_url(url):
    """剥掉加速前缀、jsdelivr 转 raw，得到规范地址用于去重。"""
    u = url.strip().rstrip(".,;、）)]\"'")
    for p in PROXY_PREFIXES:
        if u.startswith(p):
            u = u[len(p):]
            break
    m = re.match(r"^https?://(?:fastly\.)?cdn\.jsdelivr\.net/gh/([^/\s]+)/([^/\s]+)@([^/\s]+)/(.+)$", u)
    if m:
        u = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (m.group(1), m.group(2), m.group(3), m.group(4))
    return u


def extract_urls(text):
    out = []
    for m in re.finditer(r"https?://[A-Za-z0-9\-._~%/?:&=#\+\$\,\;@\[\]!'\*]+", text):
        u = m.group(0).rstrip(".,;")
        low = u.lower()
        if low.endswith(".json") or low.endswith(".txt") or ".json?" in low:
            out.append(u)
    return out


def repo_from_url(u):
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/", u)
    if m:
        return (m.group(1) + "/" + m.group(2)).lower()
    return None


def main():
    dry = "--dry-run" in sys.argv
    entries = load_sources()
    existing = {normalize_url(e["url"]) for e in entries}
    known_repos = {repo_from_url(e["url"]) for e in entries} - {None}

    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
    repos = {}
    for q in QUERIES:
        try:
            data = api("https://api.github.com/search/repositories?q="
                       + urllib.parse.quote(q) + "&sort=updated&per_page=12")
        except Exception as e:
            print("搜索失败 %s: %s" % (q, type(e).__name__))
            continue
        for it in data.get("items", []):
            fn = it.get("full_name", "")
            if it.get("fork") or not fn or fn.lower() in repos:
                continue
            if fn.lower() in known_repos:
                continue
            if (it.get("pushed_at") or "")[:10] < cutoff:
                continue
            if SKIP_PAT.search(fn + " " + (it.get("description") or "")):
                continue
            repos[fn.lower()] = {"full_name": fn, "pushed_at": it.get("pushed_at", ""),
                                 "stars": it.get("stargazers_count", 0)}
        time.sleep(2)
    repo_list = list(repos.values())[:MAX_REPOS]
    print("候选仓库 %d 个（近 %d 天有更新）" % (len(repo_list), RECENT_DAYS))

    candidates = {}
    for rv in repo_list:
        fn = rv["full_name"]
        try:
            rm = api("https://api.github.com/repos/%s/readme" % fn)
            text = base64.b64decode(re.sub(r"\s", "", rm.get("content", ""))).decode("utf-8", "ignore")
        except Exception as e:
            print("README失败 %s: %s" % (fn, type(e).__name__))
            continue
        for u in extract_urls(text):
            nu = normalize_url(u)
            if nu in existing or nu in candidates:
                continue
            candidates[nu] = {"url": nu, "repo": fn,
                              "pushed_at": rv["pushed_at"], "stars": rv["stars"]}
        time.sleep(0.5)
    cands = list(candidates.values())[:MAX_CANDIDATES]
    print("候选接口 %d 个" % len(cands))

    with ThreadPoolExecutor(max_workers=8) as ex:
        tested = list(ex.map(lambda c: (c, describe(c["url"])), cands))

    def qualified(r):
        return r["status"] == "ok" and (r.get("lines", 0) >= 3
                                        or r.get("sites", 0) >= 30
                                        or r.get("lives", 0) >= 10)

    def score(c, r):
        recent = (c["pushed_at"] or "")[:10] >= (datetime.datetime.now(datetime.timezone.utc)
                                                 - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        return r.get("lines", 0) * 60 + r.get("sites", 0) + r.get("lives", 0) * 3 + (10 if recent else 0)

    good = [(c, r) for c, r in tested if qualified(r)]
    good.sort(key=lambda cr: -score(cr[0], cr[1]))
    picked = good[:ADD_MAX]

    added = []
    for c, r in picked:
        # 命名优先用接口真实所属仓库（raw 地址能反查出 owner/name），否则用发现它的仓库
        src_repo = repo_from_url(c["url"]) or c["repo"]
        repo_short = src_repo.split("/")[-1]
        if r.get("lines"):
            scale = "%d线路" % r["lines"]
            compat = "fongmi" if r.get("multi_key") == "urls" else "tvbox"
        else:
            scale = "%d源" % r.get("sites", 0)
            if r.get("lives", 0) >= 5:
                scale += "%d直播" % r["lives"]
            compat = "both"
        added.append({"name": "%s·%s" % (repo_short, scale), "url": c["url"], "compat": compat})

    os.makedirs(REPORTS_DIR, exist_ok=True)
    rep = ["# 每周扫描报告 %s" % TODAY, "",
           "- 搜索关键词 %d 组，候选仓库 %d 个（近 %d 天有更新）" % (len(QUERIES), len(repo_list), RECENT_DAYS),
           "- 候选接口 %d 个，实测合格 %d 个，收录 %d 条" % (len(cands), len(good), len(added)),
           "", "## 收录明细", ""]
    if added:
        for a in added:
            rep.append("- 收录 %s（%s）`%s`" % (a["name"], {"tvbox": "影视仓", "fongmi": "OK影视", "both": "通用"}[a["compat"]], a["url"]))
    else:
        rep.append("- 本轮无合格新源，未改动配置")
    rep += ["", "## 全部候选实测", "", "| 仓库 | 接口 | 结果 | 实测 | 判定 |", "|---|---|---|---|---|"]
    for c, r in tested:
        if any(a["url"] == c["url"] for a in added):
            mark = "收录"
        elif qualified(r):
            mark = "合格未入选"
        else:
            mark = "淘汰"
        scale = (r.get("detail") or "")[:44]
        rep.append("| %s | `%s` | %s | %s | %s |" % (c["repo"], c["url"][:80], r["status"], scale, mark))
    with open(os.path.join(REPORTS_DIR, "scan-%s.md" % TODAY), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")

    if dry:
        print("== [dry-run] 扫描完成，未改动任何文件 ==")
    elif added:
        save_sources(entries + added)
        G.write_all(entries + added)
        print("== 已收录 %d 条并重新生成配置 ==" % len(added))
    else:
        print("== 无合格新源，配置未改动 ==")

    for c, r in tested:
        print("%-4s %-66s %s" % ("OK" if r["status"] == "ok" else "DEAD",
                                 c["url"][:64], (r.get("detail") or "")[:46]))
    print("收录: " + ("、".join(a["name"] for a in added) if added else "无"))


if __name__ == "__main__":
    main()
