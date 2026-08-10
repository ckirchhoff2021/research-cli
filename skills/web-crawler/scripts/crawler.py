#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web-crawler 核心脚本：通用网页抓取 / 站内深度爬取 / 话题资料采集

三种模式：
  fetch  抓取单个 URL，提取标题、正文、链接
  crawl  从种子 URL 出发做同域 BFS 爬取（限深度、限页数）
  topic  按话题关键词搜索全网相关页面，逐页抓取并汇总为资料包

仅依赖 requests + beautifulsoup4。所有输出写入 outputs/ 目录。
"""

import argparse
import json
import os
import random
import re
import sys
import time
from collections import deque
from datetime import datetime
from urllib.parse import urljoin, urlparse, urldefrag, quote

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

STRIP_TAGS = [
    "script", "style", "noscript", "iframe", "svg", "form",
    "nav", "header", "footer", "aside", "button", "select", "textarea",
]

MAX_TEXT_CHARS = 20000  # 单页正文截断上限，避免输出爆炸

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def project_root() -> str:
    """定位项目根目录（skills/web-crawler/scripts/crawler.py 向上 3 级）。"""
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def default_out_dir(sub: str) -> str:
    out = os.path.join(project_root(), "outputs", "web-crawler", sub)
    os.makedirs(out, exist_ok=True)
    return out


def make_session(cookie: str = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    s.headers["User-Agent"] = random.choice(USER_AGENTS)
    if cookie:
        s.headers["Cookie"] = cookie
    adapter = requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(
            total=2, backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
    )
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url.strip())
    return url.rstrip("/")


def same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def polite_sleep(base: float):
    time.sleep(base + random.uniform(0, base * 0.5))


# ---------------------------------------------------------------------------
# robots.txt（尽力而为，失败不阻塞）
# ---------------------------------------------------------------------------

_robots_cache = {}


def allowed_by_robots(session: requests.Session, url: str) -> bool:
    """检查 robots.txt；解析失败时默认放行并提示。"""
    try:
        from urllib import robotparser
    except ImportError:  # pragma: no cover
        return True
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _robots_cache:
        rp = robotparser.RobotFileParser()
        try:
            resp = session.get(base + "/robots.txt", timeout=10)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])  # 无 robots 文件，视为全放行
        except requests.RequestException:
            rp.parse([])
        _robots_cache[base] = rp
    try:
        return _robots_cache[base].can_fetch("*", url)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# 页面抓取与内容提取
# ---------------------------------------------------------------------------


def fetch_page(session: requests.Session, url: str, timeout: int = 15) -> dict:
    """抓取一个页面，返回 {url, status, ok, content_type, html, error}。"""
    result = {"url": url, "status": None, "ok": False,
              "content_type": "", "html": "", "error": ""}
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        result["status"] = resp.status_code
        result["final_url"] = resp.url
        ctype = resp.headers.get("Content-Type", "")
        result["content_type"] = ctype
        if resp.status_code == 200 and "text/html" in ctype:
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            result["html"] = resp.text
            result["ok"] = True
        elif resp.status_code == 200:
            result["error"] = f"非 HTML 内容: {ctype}"
        else:
            result["error"] = f"HTTP {resp.status_code}"
    except requests.RequestException as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def extract_content(html: str, base_url: str) -> dict:
    """从 HTML 提取标题、正文、链接。"""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.get_text(strip=True)

    # meta description
    desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        desc = meta["content"].strip()

    # 链接（在清洗前提取）
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href.startswith(("http://", "https://")):
            text = a.get_text(" ", strip=True)[:80]
            links.append({"href": normalize_url(href), "text": text})

    # 清洗噪音标签
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()

    # 主内容定位：article > main > 文本最长的 div
    main = soup.find("article") or soup.find("main")
    if main is None:
        divs = soup.find_all("div")
        if divs:
            main = max(divs, key=lambda d: len(d.get_text(strip=True)))
    root = main or soup.body or soup

    text = root.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n...[正文已截断]"

    return {"title": title, "description": desc,
            "text": text, "links": links}


def _site_fallbacks(url: str, error: str) -> list:
    """站点级失败回退 URL 候选。

    知乎专栏 zhuanlan.zhihu.com 反爬严格（403），但同一篇文章的
    tardis 镜像 www.zhihu.com/tardis/zm/art/{id} 通常可直接访问。
    """
    fallbacks = []
    if "403" in error:
        m = re.match(r"https?://zhuanlan\.zhihu\.com/p/(\d+)", url)
        if m:
            fallbacks.append(f"https://www.zhihu.com/tardis/zm/art/{m.group(1)}")
    return fallbacks


def crawl_one(session: requests.Session, url: str,
              check_robots: bool = True) -> dict:
    """抓取并解析单个页面，统一返回结构。失败时尝试站点级回退。"""
    item = _crawl_once(session, url, check_robots)
    if not item["ok"]:
        for alt in _site_fallbacks(url, item["error"]):
            alt_item = _crawl_once(session, alt, check_robots)
            if alt_item["ok"]:
                alt_item["url"] = url          # 保留原始 URL 作为来源
                alt_item["fallback_url"] = alt
                return alt_item
    return item


def _crawl_once(session: requests.Session, url: str,
                check_robots: bool = True) -> dict:
    item = {"url": url, "ok": False, "error": "",
            "title": "", "description": "", "text": "", "links": []}
    if check_robots and not allowed_by_robots(session, url):
        item["error"] = "robots.txt 禁止抓取"
        return item
    page = fetch_page(session, url)
    item["status"] = page["status"]
    if not page["ok"]:
        item["error"] = page["error"]
        return item
    content = extract_content(page["html"], page.get("final_url", url))
    item.update(content)
    item["ok"] = True
    return item


# ---------------------------------------------------------------------------
# 模式一：fetch 单页抓取
# ---------------------------------------------------------------------------


def run_fetch(args):
    session = make_session(args.cookie)
    item = crawl_one(session, args.url, check_robots=not args.ignore_robots)

    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_",
                  urlparse(args.url).netloc + urlparse(args.url).path)[:60]
    out_dir = args.out or default_out_dir(f"fetch_{slug}")

    with open(os.path.join(out_dir, "page.json"), "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(out_dir, "page.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {item['title'] or item['url']}\n\n")
        f.write(f"- 来源: {item['url']}\n")
        f.write(f"- 抓取时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"- 状态: {'成功' if item['ok'] else '失败 - ' + item['error']}\n\n")
        if item["ok"]:
            if item["description"]:
                f.write(f"> {item['description']}\n\n")
            f.write("## 正文\n\n" + item["text"] + "\n")

    print(json.dumps({
        "status": "ok" if item["ok"] else "failed",
        "url": item["url"],
        "title": item["title"],
        "error": item["error"],
        "text_length": len(item["text"]),
        "link_count": len(item["links"]),
        "output_dir": out_dir,
        "markdown": md_path,
    }, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 模式二：crawl 同域深度爬取
# ---------------------------------------------------------------------------


def run_crawl(args):
    session = make_session(args.cookie)
    seed = normalize_url(args.url)

    queue = deque([(seed, 0)])          # (url, depth)
    visited, results, failed = set(), [], []

    while queue and len(results) < args.max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        item = crawl_one(session, url, check_robots=not args.ignore_robots)
        if item["ok"]:
            item["depth"] = depth
            results.append(item)
            if depth < args.max_depth:
                for link in item["links"]:
                    href = link["href"]
                    if (href not in visited
                            and same_domain(seed, href)
                            and href not in queue):
                        queue.append((href, depth + 1))
        else:
            failed.append({"url": url, "error": item["error"]})

        polite_sleep(args.delay)

    slug = re.sub(r"[^\w]+", "_", urlparse(seed).netloc)[:40]
    out_dir = args.out or default_out_dir(f"crawl_{slug}")

    with open(os.path.join(out_dir, "pages.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": seed, "crawled_at": datetime.now().isoformat(),
                   "pages": results, "failed": failed},
                  f, ensure_ascii=False, indent=2)

    idx_path = os.path.join(out_dir, "index.md")
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write(f"# 爬取索引：{seed}\n\n")
        f.write(f"- 成功 {len(results)} 页，失败 {len(failed)} 页\n\n")
        for i, p in enumerate(results, 1):
            f.write(f"{i}. [{p['title'] or p['url']}]({p['url']}) "
                    f"(depth={p['depth']}, {len(p['text'])}字)\n")
        if failed:
            f.write("\n## 失败列表\n\n")
            for p in failed:
                f.write(f"- {p['url']} — {p['error']}\n")

    print(json.dumps({
        "status": "ok",
        "seed": seed,
        "success": len(results),
        "failed": len(failed),
        "output_dir": out_dir,
        "index": idx_path,
    }, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 模式三：topic 话题资料采集
# ---------------------------------------------------------------------------


def _bing_one_page(query: str, first: int = 1) -> list:
    """Bing 单页搜索，返回 [{title, url, snippet}]。

    注意：每次调用都新建 Session。实测发现 Bing 对复用 Session 的
    连续请求会降级返回低质量结果（中文查询尤其明显），新 Session 可规避。
    """
    session = make_session()
    try:
        resp = session.get(
            "https://www.bing.com/search",
            params={"q": query, "first": first, "count": 10},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] 搜索请求失败 q={query!r} first={first}: {e}", file=sys.stderr)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    hits = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        snippet_node = li.select_one(".b_caption p, p")
        hits.append({
            "title": a.get_text(" ", strip=True),
            "url": normalize_url(a["href"]),
            "snippet": snippet_node.get_text(" ", strip=True)
            if snippet_node else "",
        })
    return hits


def _query_variants(query: str) -> list:
    """生成查询变体。Bing 对长中文多词查询容易拆词降级
    （如"大模型 RAG 检索增强生成"被拆成单字"大"），
    通过多变体探测找到能返回高质量结果的写法。"""
    q = query.strip()
    variants = [f'"{q}"', q]
    tokens = q.split()
    if len(tokens) > 2:
        # 逐步截断：保留前 2 个词往往相关性最好
        variants.append(" ".join(tokens[:2]))
    if " " in q:
        variants.append(q.replace(" ", ""))
    # 去重保序
    seen, out = set(), []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _relevance_score(item: dict, query: str) -> int:
    """用查询词在标题+摘要中的命中数衡量相关性。"""
    text = (item["title"] + " " + item["snippet"] + " " + item["url"]).lower()
    tokens = [t for t in re.split(r"\s+", query.lower()) if t]
    return sum(1 for t in tokens if t in text)


def search_bing(session: requests.Session, query: str, count: int) -> list:
    """Bing 网页搜索，返回按相关性排序的 [{title, url, snippet}]。

    策略：对每个查询变体各抓 1-2 页，合并后按关键词重合度打分排序，
    过滤零分结果（拆词降级时返回的无关结果会被自然淘汰）。
    """
    merged, seen = [], set()
    for variant in _query_variants(query):
        for first in (1, 11):
            hits = _bing_one_page(variant, first)
            if not hits:
                break
            for h in hits:
                if h["url"] not in seen:
                    seen.add(h["url"])
                    merged.append(h)
            polite_sleep(1.5)
            # 已有足够候选就提前收手，省请求
            if len(merged) >= count * 3:
                break
        if len(merged) >= count * 3:
            break

    # 打分排序：零分结果（与查询完全无关）直接丢弃
    scored = [(item, _relevance_score(item, query)) for item in merged]
    scored = [(item, s) for item, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    results = [item for item, _ in scored[:count]]

    # 若打分后一条不剩（极端情况），退回原始顺序
    if not results:
        results = merged[:count]
    return results


def run_topic(args):
    session = make_session(args.cookie)
    query = args.query

    print(f"[1/3] 搜索话题相关页面: {query!r} (目标 {args.count} 条)...",
          file=sys.stderr)
    hits = search_bing(session, query, args.count)
    print(f"      命中 {len(hits)} 条搜索结果", file=sys.stderr)

    print("[2/3] 逐页抓取正文...", file=sys.stderr)
    docs = []
    for i, hit in enumerate(hits, 1):
        item = crawl_one(session, hit["url"],
                         check_robots=not args.ignore_robots)
        doc = {
            "rank": i,
            "search_title": hit["title"],
            "snippet": hit["snippet"],
            "url": hit["url"],
            "ok": item["ok"],
            "error": item["error"],
            "title": item["title"] or hit["title"],
            "text": item["text"] if item["ok"] else "",
        }
        docs.append(doc)
        mark = "✓" if item["ok"] else f"✗ {item['error']}"
        print(f"      [{i}/{len(hits)}] {mark} {hit['url']}", file=sys.stderr)
        polite_sleep(args.delay)

    ok_docs = [d for d in docs if d["ok"]]
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", query)[:40]
    out_dir = args.out or default_out_dir(f"topic_{slug}")

    with open(os.path.join(out_dir, "raw_docs.json"), "w",
              encoding="utf-8") as f:
        json.dump({"query": query,
                   "crawled_at": datetime.now().isoformat(),
                   "docs": docs}, f, ensure_ascii=False, indent=2)

    # 资料包 Markdown：供上层智能体阅读并整理成报告
    digest_path = os.path.join(out_dir, "digest.md")
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(f"# 话题资料包：{query}\n\n")
        f.write(f"- 采集时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"- 搜索命中: {len(docs)} 条，成功抓取: {len(ok_docs)} 条\n\n")
        f.write("## 来源清单\n\n")
        for d in docs:
            status = "成功" if d["ok"] else f"失败({d['error']})"
            f.write(f"{d['rank']}. [{d['title']}]({d['url']}) — {status}\n")
        f.write("\n---\n\n")
        for d in ok_docs:
            f.write(f"## [{d['rank']}] {d['title']}\n\n")
            f.write(f"- 来源: {d['url']}\n")
            if d["snippet"]:
                f.write(f"- 摘要: {d['snippet']}\n")
            f.write("\n" + d["text"] + "\n\n---\n\n")

    print(json.dumps({
        "status": "ok",
        "query": query,
        "search_hits": len(docs),
        "fetched_ok": len(ok_docs),
        "fetched_failed": len(docs) - len(ok_docs),
        "output_dir": out_dir,
        "digest": digest_path,
    }, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="web-crawler 核心脚本")
    parser.add_argument("--cookie", default=None,
                        help="可选：登录态 Cookie（目标站需要登录时提供）")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_fetch = sub.add_parser("fetch", help="抓取单个 URL")
    p_fetch.add_argument("--url", required=True)
    p_fetch.add_argument("--out", default=None)
    p_fetch.add_argument("--ignore-robots", action="store_true")
    p_fetch.set_defaults(func=run_fetch)

    p_crawl = sub.add_parser("crawl", help="同域深度爬取")
    p_crawl.add_argument("--url", required=True, help="种子 URL")
    p_crawl.add_argument("--max-pages", type=int, default=10)
    p_crawl.add_argument("--max-depth", type=int, default=2)
    p_crawl.add_argument("--delay", type=float, default=1.0)
    p_crawl.add_argument("--out", default=None)
    p_crawl.add_argument("--ignore-robots", action="store_true")
    p_crawl.set_defaults(func=run_crawl)

    p_topic = sub.add_parser("topic", help="按话题采集资料")
    p_topic.add_argument("--query", required=True, help="话题关键词")
    p_topic.add_argument("--count", type=int, default=8,
                         help="搜索结果条数上限")
    p_topic.add_argument("--delay", type=float, default=1.5)
    p_topic.add_argument("--out", default=None)
    p_topic.add_argument("--ignore-robots", action="store_true")
    p_topic.set_defaults(func=run_topic)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
