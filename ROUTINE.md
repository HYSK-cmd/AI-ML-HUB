# Daily HUB routine

You are publishing today's AI/ML brief for a university student (CS/ML, interested in LLMs, agents, robotics/robot hands, ML infra/AWS): **exactly 3 items, one 입문, one 중급, one 심화**, plus a Korean news-style video of them. Run this top to bottom, then stop.

## 1. Guards
`TODAY=$(TZ=America/Los_Angeles date +%F)`. Stop without doing anything if:
- `data/$TODAY.json` already exists (today is done), or
- `TZ=America/Los_Angeles date +%H` is `08` (the schedule fires at 16:00 and 17:00 UTC so one of them is 09:00 PT across daylight saving; the 08:00 one is the extra).

## 2. Collect (corpus overlap is removed here)
```
pip install -q edge-tts gTTS pillow imageio-ffmpeg
python collect.py > candidates.json
```
`collect.py` already drops every candidate that overlaps the corpus (all items in `data/2*.json` plus `data/seen.json`, matched by URL, arXiv id and title) and merges the same paper arriving from HF and arXiv. Its stderr prints per-source counts and a `dedup:` line; keep both for the final report. Reddit / GitHub Trending / blogs failing is fine. If `hf_papers`, `arxiv` and `hacker_news` are all empty, stop without committing.

Also WebFetch `https://www.anthropic.com/news` and consider any post from the last 3 days. Before using it, confirm its URL is not already in `data/` (`grep -rF "<url>" data/`).

## 3. Select exactly 3
One per level, judged for a CS undergrad:
- **입문**: readable after one intro ML course. Practical tips, tools, repos you can run today, industry/policy news with a clear takeaway.
- **중급**: needs deep learning basics (transformers, fine-tuning, RL basics). Recipes, systems write-ups, hands-on tutorials, approachable papers.
- **심화**: research-level paper or technical deep dive worth reading slowly.

Within each level, rank for learning value, not hype: a new idea worth understanding, widely discussed (HF upvotes, HN points, GitHub stars today), or hands-on (code, open weights). Prefer 3 different categories and at least one non-paper when a good one exists. Favor robotics/embodied when a strong one exists. Drop funding/sales/customer stories and anything you can't verify.

Read beyond the snippet (WebFetch the page) for all 3. Never invent numbers or claims. Legal/news items: say whose claim it is.

## 4. Write `data/$TODAY.json`
Items ordered 입문, 중급, 심화. Fixed categories (exact strings): `LLM`, `Agents`, `Multimodal & Vision`, `Robotics & Embodied`, `RL`, `ML Systems & Infra`, `Research Fundamentals`, `Open Source & Tools`, `Industry & Policy`. Never use em-dashes in any text; use a period, comma or colon.

```json
{ "date": "YYYY-MM-DD",
  "headline": "오늘 세 소식을 잇는 한 문장 (한국어)",
  "items": [{
    "title": "Coding Agents for Generalized Task and Motion Planning Problems",
    "url": "https://huggingface.co/papers/2609.30233",
    "source": "HF Papers",
    "categories": ["Robotics & Embodied", "Agents"],
    "level": "심화",
    "headline_ko": "코딩 에이전트가 로봇 motion planning 코드 작성",
    "summary": "한국어 3-4문장. 무엇을, 어떻게, 결과. 기술 용어는 영어 그대로.",
    "why": "대학생으로서 왜 봐야 하나, 무엇을 배울 수 있나 (1-2문장).",
    "keywords": ["TAMP", "program synthesis", "coding agent"],
    "narration": "세 번째는 심화 소식입니다. Claude Code와 Codex에게 시뮬레이터만 주고, 여러 문제에 일반화되는 로봇 planning 프로그램을 직접 짜게 한 연구입니다. 완성된 프로그램은 고정한 채, 처음 보는 28개 환경에서 평가했습니다. 코딩 에이전트와 로봇을 연결하는 연구를 한다면 평가 방식을 참고할 만합니다."
  }]
}
```
- `source`: one of HF Papers, arXiv, Hacker News, r/MachineLearning, r/LocalLLaMA, GitHub Trending, OpenAI, Anthropic, Google DeepMind, Google Research, Hugging Face, AWS ML, BAIR.
- `headline_ko`: Korean news-caption headline, 22 characters or fewer.
- `narration`: what the anchor reads aloud. 3-4 short sentences, about 20-30 seconds, opening with "첫 번째는 입문 소식입니다." / "두 번째는 중급 소식입니다." / "세 번째는 심화 소식입니다.". Spoken Korean: no URLs, no brackets, no emoji, no bullet symbols. Each sentence ends with `.`, `!` or `?` (one sentence = one slide and subtitle).

Then `python make_video.py --validate data/$TODAY.json`. It exits 2 and lists problems (wrong count or order, missing fields, unknown category, em-dash, already published); fix them and re-run until it prints `OK`.

## 5. Video
```
python make_video.py data/$TODAY.json
```
Renders `videos/$TODAY.mp4` and `videos/$TODAY.jpg` (Korean TTS narration, one slide per sentence with the item's og:image as material) and adds `"video"` to the day file. If it fails, retry once; if it still fails, publish without the video and say so in the report.

## 6. Index, validate, publish
- Prepend `$TODAY` to the array in `data/index.json` (no duplicates, newest first).
- `python -m json.tool data/index.json > /dev/null && python make_video.py --validate data/$TODAY.json`
- `git add data videos && git commit -m "brief: $TODAY" && git push origin HEAD:main`

GitHub Pages redeploys from `main` automatically. Do not edit any other file.

Final report, one line: date, the 3 titles with levels, video yes/no, per-source counts and the `dedup:` line.
