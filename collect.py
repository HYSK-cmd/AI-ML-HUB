"""Collect AI/ML candidate items for the daily HUB brief.

Usage:
  HUB_DATE=2026-09-28 python collect.py > candidates.json   # {date, counts, dedup, items} to stdout, log to stderr
  python collect.py --check    # assert each source returns something (reddit/github/blogs are best-effort)

Runs in GitHub Actions (.github/workflows/collect.yml) because the Claude cloud routine has no open internet.

stdlib only. Every source is independent: one failing source is logged and skipped.
Candidates already in the corpus (every item in data/2*.json + URLs in data/seen.json) are dropped
before output, and the same paper arriving from two sources (HF + arXiv) is kept once.
"""
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (hub-collector; +https://github.com/HYSK-cmd/AI-ML-HUB)"
NOW = datetime.now(timezone.utc)
AI_WORDS = re.compile(
    r"\b(ai|ml|llm|llms|gpt|claude|gemini|llama|mistral|qwen|deepseek|openai|anthropic|deepmind|"
    r"neural|transformer|diffusion|agent|agents|agentic|rag|embedding|inference|fine-?tun\w*|"
    r"machine learning|deep learning|reinforcement|robot\w*|vision|multimodal|model|models|"
    r"pytorch|jax|cuda|gpu|tpu|nvidia|hugging ?face|benchmark|reasoning)\b",
    re.I,
)
BLOGS = {
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google Research": "https://research.google/blog/rss/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "AWS ML": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "BAIR": "https://bair.berkeley.edu/blog/feed.xml",
}
ATOM = "{http://www.w3.org/2005/Atom}"
DATA = Path(__file__).parent / "data"
ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})")


def get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            # GitHub runners share IPs, so Reddit's per-IP budget is often spent by others; it refills in seconds
            if e.code not in (429, 503) or attempt == retries:
                raise
            hint = e.headers.get("x-ratelimit-reset") or e.headers.get("Retry-After") or ""
            wait = min(float(hint) if hint.replace(".", "", 1).isdigit() and float(hint) > 0 else 10 * (attempt + 1), 30)
            print(f"  {e.code} from {urllib.parse.urlsplit(url).netloc}, retry in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    if body[:2] == b"\x1f\x8b":  # some feeds (DeepMind) gzip regardless of Accept-Encoding
        body = gzip.decompress(body)
    return body.decode("utf-8", "replace")


def clean(s, n=1500):  # the routine can't open pages, so the snippet is what it summarizes from
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def item(source, title, url, snippet="", score=0, published=""):
    return {"source": source, "title": clean(title, 300), "url": url,
            "snippet": clean(snippet), "score": score, "published": published}


def hf_papers():
    out = []
    for p in json.loads(get("https://huggingface.co/api/daily_papers?limit=50")):
        pp = p.get("paper", p)
        out.append(item("HF Papers", pp.get("title", ""), f"https://huggingface.co/papers/{pp['id']}",
                        pp.get("summary", ""), pp.get("upvotes", 0), p.get("publishedAt", "")))
    return sorted(out, key=lambda x: -x["score"])[:30]


def arxiv():
    # From GitHub runner IPs the API answers any OR query with 406, but single-category queries work.
    out = []
    for n, cat in enumerate(("cs.CL", "cs.LG", "cs.AI", "cs.CV", "cs.RO")):
        if n:
            time.sleep(3)  # arXiv API etiquette: one request every 3 seconds
        feed = ET.fromstring(get(f"https://export.arxiv.org/api/query?search_query=cat:{cat}"
                                 "&sortBy=submittedDate&sortOrder=descending&max_results=12"))
        out += [item("arXiv", e.findtext(ATOM + "title"), e.findtext(ATOM + "id"),
                     e.findtext(ATOM + "summary"), 0, e.findtext(ATOM + "published"))
                for e in feed.iter(ATOM + "entry")]
    return out  # cross-listed papers repeat across categories; collect()'s dedupe keeps one


def hacker_news():
    since = int((NOW - timedelta(hours=36)).timestamp())
    data = json.loads(get("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=200"
                          f"&numericFilters=created_at_i>{since},points>40"))
    out = [item("Hacker News", h["title"], h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                f"HN discussion: https://news.ycombinator.com/item?id={h['objectID']} ({h.get('num_comments', 0)} comments)",
                h.get("points", 0), h.get("created_at", ""))
           for h in data["hits"] if AI_WORDS.search(h.get("title") or "")]
    return sorted(out, key=lambda x: -x["score"])[:25]


def reddit():
    # .json is 403 for bots; the Atom feed isn't. Feed order = top of day, no score exposed.
    out = []
    for sub in ("MachineLearning", "LocalLLaMA"):
        time.sleep(3)  # reddit 429s back-to-back requests
        feed =ET.fromstring(get(f"https://www.reddit.com/r/{sub}/top/.rss?t=day&limit=15"))
        for rank, e in enumerate(feed.iter(ATOM + "entry")):
            out.append(item(f"r/{sub}", e.findtext(ATOM + "title"), e.find(ATOM + "link").get("href"),
                            e.findtext(ATOM + "content"), 15 - rank, e.findtext(ATOM + "updated")))
    return out


def github_trending():
    page = get("https://github.com/trending?since=daily")
    out = []
    # ponytail: regex over trending HTML, breaks if GitHub changes markup; switch to search API then
    for block in page.split('<article class="Box-row">')[1:]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', block)
        if not m:
            continue
        desc = re.search(r'<p class="col-9[^"]*">(.*?)</p>', block, re.S)
        stars = re.search(r"([\d,]+)\s+stars today", block)
        text = m.group(1) + " " + (desc.group(1) if desc else "")
        if AI_WORDS.search(clean(text)):
            out.append(item("GitHub Trending", m.group(1), "https://github.com/" + m.group(1),
                            desc.group(1) if desc else "", int(stars.group(1).replace(",", "")) if stars else 0))
    return out


def parse_date(s):
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return None


def blogs():
    out, cutoff = [], NOW - timedelta(hours=72)
    for name, url in BLOGS.items():
        try:
            root = ET.fromstring(get(url))
        except Exception as e:  # one dead feed shouldn't kill the rest
            print(f"  blog {name}: FAIL {e}", file=sys.stderr)
            continue
        entries = root.iter("item") if root.find("channel") is not None else root.iter(ATOM + "entry")
        for e in entries:
            title = e.findtext("title") or e.findtext(ATOM + "title")
            link = e.findtext("link") or (e.find(ATOM + "link").get("href") if e.find(ATOM + "link") is not None else "")
            pub = e.findtext("pubDate") or e.findtext(ATOM + "published") or e.findtext(ATOM + "updated") or ""
            d = parse_date(pub)
            if d and d.tzinfo and d >= cutoff:
                out.append(item(name, title, link.strip(),
                                e.findtext("description") or e.findtext(ATOM + "summary") or "", 0, d.isoformat()))
    return out


def meta(page, prop):
    m = (re.search(rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']*)', page)
         or re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{prop}["\']', page))
    return html.unescape(m.group(1)) if m else ""


def anthropic():
    # no RSS; the sitemap's lastmod on /news/ pages is the closest thing to a publish date
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    root, out, cutoff = ET.fromstring(get("https://www.anthropic.com/sitemap.xml")), [], NOW - timedelta(hours=72)
    for u in root.iter(ns + "url"):
        loc, mod = u.findtext(ns + "loc") or "", parse_date(u.findtext(ns + "lastmod") or "")
        if "/news/" in loc and mod and mod >= cutoff:
            page = get(loc)
            out.append(item("Anthropic", meta(page, "og:title") or loc.rsplit("/", 1)[-1], loc,
                            meta(page, "og:description"), 0, mod.isoformat()))
    return out


SOURCES = {"hf_papers": hf_papers, "arxiv": arxiv, "hacker_news": hacker_news,
           "reddit": reddit, "github_trending": github_trending, "blogs": blogs, "anthropic": anthropic}
BEST_EFFORT = {"reddit", "github_trending", "blogs", "anthropic"}  # Reddit rate limits shared IPs, markup changes, quiet days


def keys(url, title=""):
    """Identity keys: normalized URL, arXiv id (HF papers + arxiv.org share it), normalized title."""
    u = urllib.parse.urlsplit(url or "")
    host = u.netloc.lower().removeprefix("www.")
    ks = {host + u.path.rstrip("/").lower()}
    if host in ("arxiv.org", "export.arxiv.org", "huggingface.co") and (m := ARXIV_ID.search(u.path)):
        ks.add("arxiv:" + m.group(1))
    t = re.sub(r"[\W_]", "", (title or "").lower())  # letters and digits of any script
    if len(t) > 12:
        ks.add("title:" + t)
    return ks


def corpus(exclude=None):
    """Everything already published or explicitly retired. Never shown again."""
    seen = set()
    for p in DATA.glob("2*.json"):
        if exclude and p.resolve() == Path(exclude).resolve():
            continue
        for it in json.loads(p.read_text(encoding="utf-8")).get("items", []):
            seen |= keys(it.get("url"), it.get("title"))
    extra = DATA / "seen.json"
    if extra.exists():
        for url in json.loads(extra.read_text(encoding="utf-8")):
            seen |= keys(url)
    return seen


def page_text(url, n=6000):
    """Readable text of a source page (a repo's README for GitHub links).
    Shared on purpose: the routine writes from it and judge.py verify checks against the same text."""
    if m := re.match(r"https://github\.com/([^/]+/[^/#?]+)/?$", url):
        return clean(get(f"https://raw.githubusercontent.com/{m.group(1)}/HEAD/README.md"), n)
    page = re.sub(r"(?is)<(script|style|nav|header|footer|svg)\b[^>]*>.*?</\1>", " ", get(url))
    return clean(page, n)


def enrich(it):
    """Give thin items real text to summarize from: a repo's README, or the linked page's description."""
    if len(it["snippet"]) >= 300:
        return
    try:
        if it["source"] == "GitHub Trending":
            readme = get(f"https://raw.githubusercontent.com/{it['title']}/HEAD/README.md")
            readme = re.sub(r"!\[[^\]]*\]\([^)]*\)|\[!\[.*?\]\(.*?\)\]\(.*?\)", "", readme)  # drop images/badges
            it["snippet"] = clean(f"{it['snippet']} README: {readme}")
        else:
            page = get(it["url"])
            desc = meta(page, "og:description") or (re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', page) or [None, ""])[1]
            if desc:
                it["snippet"] = clean(f"{desc} ({it['snippet']})" if it["snippet"] else desc)
    except Exception as e:  # enrichment is optional
        print(f"  enrich skip ({it['url']}): {e}", file=sys.stderr)


def collect():
    all_items, counts = [], {}
    for name, fn in SOURCES.items():
        t = time.time()
        try:
            got = fn()
        except Exception as e:
            print(f"{name}: FAIL {e}", file=sys.stderr)
            got = []
        counts[name] = len(got)
        print(f"{name}: {len(got)} ({time.time() - t:.1f}s)", file=sys.stderr)
        all_items += got
    published, today, uniq, old, dup = corpus(), set(), [], 0, 0
    for it in all_items:  # sources are ordered best-first, so HF (upvotes) wins over bare arXiv
        k = keys(it["url"], it["title"])
        if not it["url"] or k & published:
            old += 1
        elif k & today:
            dup += 1
        else:
            today |= k
            uniq.append(it)
    for it in uniq:
        enrich(it)
    dedup = f"dedup: {old} already in corpus, {dup} cross-source duplicates, {len(uniq)} new"
    print(dedup, file=sys.stderr)
    return uniq, counts, dedup


if __name__ == "__main__":
    if "--check" in sys.argv:
        assert keys("https://huggingface.co/papers/2609.28654") & keys("https://arxiv.org/abs/2609.28654v2")
        assert keys("https://www.github.com/a/b/") & keys("https://github.com/A/b")
        assert not keys("https://github.com/a/b") & keys("https://github.com/a/c")
    items, counts, dedup = collect()
    if "--check" in sys.argv:
        hard = [k for k, v in counts.items() if v == 0 and k not in BEST_EFFORT]
        soft = [k for k, v in counts.items() if v == 0 and k in BEST_EFFORT]
        assert all(i["title"] and i["url"].startswith("http") for i in items), "malformed item"
        assert not hard, f"required sources returned nothing: {hard}"
        print(f"OK {len(items)} items" + (f" (warn, empty: {soft})" if soft else ""), file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        day = os.environ.get("HUB_DATE") or datetime.now().date().isoformat()
        json.dump({"date": day, "collected_at": NOW.isoformat(timespec="seconds"), "counts": counts,
                   "dedup": dedup, "items": items}, sys.stdout, ensure_ascii=False, indent=1)
