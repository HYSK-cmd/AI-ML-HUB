# Daily HUB routine

You are publishing today's AI/ML brief for a university student (CS/ML, interested in LLMs, agents, robotics/robot hands, ML infra/AWS). Run this top to bottom, then stop.

## 1. Date
`TODAY=$(TZ=America/Los_Angeles date +%F)`. If `data/$TODAY.json` already exists, stop — today is done.

## 2. Collect
```
python collect.py > candidates.json
```
Per-source counts go to stderr. Reddit / GitHub Trending / blogs failing is fine. If `hf_papers`, `arxiv` and `hacker_news` are all empty, stop without committing.

Also WebFetch `https://www.anthropic.com/news` and add any post from the last 3 days as a candidate.

## 3. Select 12–20 items
Rank for **learning value to a student**, not hype:
- New idea or method worth understanding (HF Papers upvotes are a good popularity signal; arXiv entries have no score — pick only standout titles).
- Widely discussed (HN points/comments, Reddit rank, GitHub stars today).
- Hands-on: code, tutorial, open weights you can actually run.
- Mix sources and categories. At most ~8 papers. Cover robotics/embodied when there is anything decent.
- Drop: funding/sales/customer-story posts, duplicates (merge same story from several sources, keep the best URL), items you can't verify.

For each pick, read beyond the snippet when it's thin (WebFetch the page). Never invent numbers or claims. If a page can't be fetched and the snippet is too thin, skip the item. Legal/news items: say whose claim it is.

## 4. Write `data/$TODAY.json`
```json
{ "date": "YYYY-MM-DD",
  "headline": "한 줄: 오늘 가장 중요한 흐름 (한국어)",
  "items": [{
    "title": "original English title",
    "url": "https://...",
    "source": "HF Papers | arXiv | Hacker News | r/MachineLearning | r/LocalLLaMA | GitHub Trending | OpenAI | Anthropic | Google DeepMind | Google Research | Hugging Face | AWS ML | BAIR",
    "categories": ["1–3 of the fixed list below"],
    "summary": "한국어 3–4문장. 무엇을/어떻게/결과. 기술 용어는 영어 그대로.",
    "why": "대학생으로서 왜 봐야 하나, 무엇을 배울 수 있나 (1–2문장)",
    "level": "입문 | 중급 | 심화",
    "keywords": ["2–5 English terms"]
  }]
}
```
Fixed categories (use exactly these strings): `LLM`, `Agents`, `Multimodal & Vision`, `Robotics & Embodied`, `RL`, `ML Systems & Infra`, `Research Fundamentals`, `Open Source & Tools`, `Industry & Policy`.

Order items by importance (first = must-read). Never use em-dashes (—) in any text; use a period, comma or colon. See `data/2026-09-28.json` for tone and depth.

## 5. Index, validate, publish
- Prepend `$TODAY` to the array in `data/index.json` (no duplicates, newest first).
- `python -m json.tool data/$TODAY.json > /dev/null && python -m json.tool data/index.json > /dev/null`
- `git add data && git commit -m "brief: $TODAY" && git push origin HEAD:main`

GitHub Pages redeploys from `main` automatically. Do not edit any other file.
