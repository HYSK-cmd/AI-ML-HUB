# HUB

Daily AI/ML brief for a university student, updated every morning at 09:00 PT.
Live: https://hysk-cmd.github.io/hub/

- `collect.py` pulls candidates (HF Daily Papers, arXiv, Hacker News, Reddit, GitHub Trending, lab blogs). stdlib only. `python collect.py --check` to self-test.
- A scheduled Claude routine follows `ROUTINE.md`: select, summarize in Korean, write `data/YYYY-MM-DD.json`, push.
- `index.html` renders it. No build step. Preview locally with `python -m http.server`.
