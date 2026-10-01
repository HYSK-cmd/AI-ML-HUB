"""Pick today's 3 items from candidates.json and write data/<today>.json (Gemini API, prompt in PICK.md).

Usage: python pick.py   (needs GEMINI_API_KEY; exits non-zero on failure so the workflow stops before publish)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import collect
import make_video

ROOT = Path(__file__).parent
TODAY = subprocess.check_output(["date", "+%F"], env={**os.environ, "TZ": "America/Los_Angeles"}, text=True).strip()
SYSTEM = (ROOT / "PICK.md").read_text(encoding="utf-8")


def ask(user, retries=0):
    for attempt in range(retries + 1):
        text = collect.generate(user, system_instruction=SYSTEM, response_mime_type="application/json")
        try:
            return json.loads(text[text.index("{"):text.rindex("}") + 1])
        except ValueError:
            if attempt == retries:
                raise


cand = json.loads((ROOT / "candidates.json").read_text(encoding="utf-8"))
if cand["date"] != TODAY or not cand["items"]:
    sys.exit(f"candidates.json is not for {TODAY} or empty")
out = ROOT / "data" / f"{TODAY}.json"
if out.exists():
    sys.exit(f"{out.name} already exists")

slim = [{k: it.get(k) for k in ("title", "url", "source", "snippet", "score", "judge")} for it in cand["items"]]
picks = ask("Candidates:\n" + json.dumps(slim, ensure_ascii=False) +
            '\n\nStep 1: choose the 3 items. Reply {"beginner": "<url>", "intermediate": "<url>", "advanced": "<url>"}.', 1)
by_url = {it["url"]: it for it in cand["items"]}
chosen = [(lvl, by_url[picks[lvl]]) for lvl in make_video.LEVELS]  # KeyError = model invented a URL, fail loudly
pages = []
for lvl, it in chosen:
    try:
        text = collect.page_text(it["url"])
    except Exception as e:  # page text is optional, the snippet alone is enough
        print(f"page skip {it['url']}: {e}", file=sys.stderr)
        text = ""
    pages.append({"level": lvl, "title": it["title"], "url": it["url"], "source": it["source"],
                  "snippet": it["snippet"], "page": text})

user = ("Step 2: write the day file for date " + TODAY + " from these three picks:\n" +
        json.dumps(pages, ensure_ascii=False) + "\nReply with the JSON object.")
for attempt in range(3):
    day = ask(user, 1)
    out.write_text(json.dumps(day, ensure_ascii=False, indent=2), encoding="utf-8")
    errs = make_video.validate(out)
    if not errs:
        break
    print("validation:", errs, file=sys.stderr)
    user += "\n\nYour previous answer had these problems, fix them and reply with the full JSON again:\n" + "\n".join(errs)
else:
    out.unlink()
    sys.exit("could not produce a valid day file")

idx = ROOT / "data" / "index.json"
days = json.loads(idx.read_text(encoding="utf-8"))
idx.write_text(json.dumps([TODAY] + [d for d in days if d != TODAY], indent=2) + "\n", encoding="utf-8")
print("OK", TODAY, [(i["level"], i["title"]) for i in day["items"]])
