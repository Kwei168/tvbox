# -*- coding: utf-8 -*-
"""共享工具：路径常量、抓取、宽容 JSON 解析、接口可用性判定。仅依赖 Python 标准库。"""
import json
import os
import ssl
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "config", "sources.json")
REPORTS_DIR = os.path.join(ROOT, "reports")
SNAPSHOT_DIR = os.path.join(ROOT, "output")
HISTORY_FILE = os.path.join(ROOT, "check_history.json")

USER_AGENT = "okhttp/4.9.3"
TIMEOUT = 12
MAX_RETRIES = 2
READ_CAP = 3 * 1024 * 1024

# GitHub Actions 自动注入；本地未设置则走未认证限额
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def idn_encode(url):
    """中文国际化域名转 punycode，避免 DNS 解析失败（如 肥猫.love）。"""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        encoded = host.encode("idna").decode("ascii")
        netloc = encoded + (":%d" % parsed.port if parsed.port else "")
        return urllib.parse.urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )
    except Exception:
        return url


def fetch(url, timeout=TIMEOUT):
    """抓取原始字节，返回 (status, bytes)；异常向上抛。"""
    req = urllib.request.Request(
        idn_encode(url),
        headers={"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.status, r.read(READ_CAP)


def _strip_comments(text):
    """剔除 JSON 内嵌的 // 与 /* */ 注释（保持字符串内容不动）。"""
    out = []
    i, n = 0, len(text)
    in_str = False
    esc = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def lenient_parse(text):
    """宽容解析：去 BOM、剔注释、strict=False；兼容多段拼接 JSON 取第一段。失败抛 ValueError。"""
    text = text.lstrip("\ufeff").strip()
    cleaned = _strip_comments(text)
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder(strict=False)
        obj, _ = decoder.raw_decode(cleaned)
        return obj


def load_text(data):
    """多编码尝试解码字节。"""
    for enc in ("utf-8-sig", "gbk"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", "ignore")


def describe(url, timeout=TIMEOUT):
    """实测单个接口地址，返回判定结果：
    status: ok/dead；kind: multi/config/empty/bad/net；
    lines=多仓线路数；sites/lives=单仓规模；multi_key=urls/storeHouse。"""
    last, last_kind = "", "net"
    for _attempt in range(1, MAX_RETRIES + 1):
        try:
            _st, data = fetch(url, timeout)
            txt = load_text(data).strip()
            size = len(data)
            # 先做宽容解析（去 BOM/剔注释），不要根据首字符提前判死——
            # 有些源（如流光 m.json）以 // 注释开头，App 照样能解析
            try:
                j = lenient_parse(txt)
            except ValueError:
                raise ValueError("非JSON或JSON损坏: " + txt[:56].replace("\n", " "))
            if isinstance(j, list):
                return {"status": "ok", "kind": "multi", "multi_key": "storeHouse",
                        "lines": len(j), "sites": 0, "lives": 0, "spider": False,
                        "detail": "多仓(list)=%d线路" % len(j), "size": size}
            if not isinstance(j, dict):
                return {"status": "dead", "kind": "bad", "size": size, "detail": "JSON顶层非对象"}
            lines_sh = len(j.get("storeHouse") or [])
            lines_u = len(j.get("urls") or [])
            if lines_sh or lines_u:
                key = "urls" if lines_u else "storeHouse"
                lines = lines_u or lines_sh
                return {"status": "ok", "kind": "multi", "multi_key": key, "lines": lines,
                        "sites": 0, "lives": 0, "spider": bool(j.get("spider")),
                        "detail": "多仓(%s)=%d线路" % (key, lines), "size": size}
            sites = len(j.get("sites") or [])
            lives = len(j.get("lives") or [])
            if sites or lives:
                return {"status": "ok", "kind": "config", "sites": sites, "lives": lives,
                        "spider": bool(j.get("spider")),
                        "detail": "sites=%d lives=%d" % (sites, lives), "size": size}
            return {"status": "dead", "kind": "empty", "size": size,
                    "detail": "JSON无有效内容 keys=%s" % ",".join(list(j.keys())[:6])}
        except ValueError as e:
            last, last_kind = "JSON损坏: %s" % str(e)[:50], "bad"
        except Exception as e:
            last, last_kind = "%s %s" % (type(e).__name__, str(e)[:55]), "net"
    return {"status": "dead", "kind": last_kind, "detail": last, "size": 0}


def load_sources():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sources(entries):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
