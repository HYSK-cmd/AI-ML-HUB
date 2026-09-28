# HUB

Daily AI/ML brief for a university student: every morning at 09:00 PT, three picks (입문, 중급, 심화) summarized in Korean, plus a Korean news-style video of them.

Live: https://hysk-cmd.github.io/hub/

## Agent workflow

Three pieces, all in the cloud. GitHub Actions does everything that needs the open internet (collecting, TTS, og:images, deploying). The Claude routine does the judgment: picking 3 and writing the Korean summaries and narration. Its sandbox has no open internet, so it only reads what Actions committed.

```mermaid
flowchart TD
    subgraph collect_wf ["GitHub Actions: collect.yml, 13:23 UTC"]
        fetch["collect.py fetches<br/>HF Daily Papers, arXiv, Hacker News, Reddit,<br/>GitHub Trending, lab blogs, Anthropic news"] --> corpus{"Overlaps the corpus?<br/>data/2*.json + data/seen.json<br/>by URL, arXiv id, title"}
        corpus -- yes --> drop(["Dropped"])
        corpus -- no --> xdup{"Same paper from<br/>two sources?"}
        xdup -- yes --> merge(["Kept once"])
        xdup -- no --> judge["judge.py candidates (TypeSafe Jev)<br/>injection? substance? learning value?<br/>difficulty, hands-on scores"]
        judge -- "injection, no substance,<br/>low learning value" --> drop2(["Moved to dropped"])
        judge --> sem{"Same work as a published item<br/>or another candidate?<br/>(pairs ranked by word overlap)"}
        sem -- same --> drop2
        sem -- "related / different" --> cands[("candidates.json<br/>with judge scores, committed")]
    end

    subgraph routine ["Claude cloud routine: ROUTINE.md, 16:00 + 17:00 UTC"]
        guard{"data/TODAY.json exists,<br/>or PT hour is 08?"}
        guard -- yes --> stop(["Stop"])
        guard -- no --> fresh{"candidates.json<br/>dated today?"}
        fresh -- no --> stop
        fresh -- yes --> select["Select exactly 3<br/>입문 / 중급 / 심화"]
        select --> write["Write data/TODAY.json<br/>summary, why, keywords,<br/>headline_ko, narration"]
        write --> validate{"make_video.py --validate<br/>3 items in level order, fields,<br/>categories, no em-dash, not in corpus"}
        validate -- errors --> write
        validate -- OK --> push["Prepend to data/index.json<br/>commit + push to main"]
    end

    cands --> fresh

    subgraph publish_wf ["GitHub Actions: publish.yml, on push"]
        verify["judge.py verify (TypeSafe Jev)<br/>each summary/narration sentence vs its source:<br/>supports / contradicts / says nothing"] --> flag["Sentences without confident support<br/>listed as unverified on the site"]
        flag --> render["make_video.py for days without a video"]
        render --> tts["Korean TTS per sentence<br/>edge-tts, gTTS fallback"]
        render --> slides["News slide per sentence<br/>og:image material, level tag,<br/>lower third, subtitle"]
        tts --> ffmpeg["ffmpeg: segment per slide, concat"]
        slides --> ffmpeg
        ffmpeg --> mp4[("videos/TODAY.mp4 + .jpg<br/>committed")]
        mp4 --> deploy["Deploy GitHub Pages"]
    end

    push --> verify
    deploy --> site(["Site: day view with video,<br/>category and level filters across the archive"])
```

## Files

| File | What it does |
|---|---|
| `ROUTINE.md` | Instructions the daily Claude routine follows. Change selection rules and the schema here. |
| `collect.py` | Pulls candidates and removes anything already in the corpus. stdlib only. `python collect.py --check` self-tests. |
| `judge.py` | TypeSafe judgments where code would guess: candidate screen/scores/semantic dedupe, and sentence-level fact check of summaries. Thresholds at the top of the file. Skips cleanly without `TYPESAFE_API_KEY`. `--check` self-tests. |
| `make_video.py` | Validates a day file and renders the news video. `--validate FILE`, `--check`. |
| `.github/workflows/collect.yml` | Morning run of `collect.py` + `judge.py candidates`, commits `candidates.json`. |
| `.github/workflows/publish.yml` | On push: `judge.py verify` + renders missing videos, commits them, deploys Pages. |
| `data/YYYY-MM-DD.json` | One day: 3 items. `data/index.json` lists the days. |
| `data/seen.json` | Extra URLs to never show again (items retired from the site). |
| `videos/` | Daily MP4 + poster JPG. |
| `index.html` | The site. No build step. Preview with `python -m http.server`. |

Local deps: `pip install edge-tts gTTS pillow imageio-ffmpeg typesafe-sdk`. The Actions workflows need a `TYPESAFE_API_KEY` repository secret.

### TypeSafe judgment policy (first tuned on 2026-09-28 data)
- Candidate dropped if injection > 0.7, substance < 0.5, or learning value < 0.9 (of 3; lowered from 1.0 so tool launches scoring ~0.99 survive). On 2026-09-28 this removed 6 non-study HN stories, a partnership announcement and a customer story, and kept every paper plus 3 real HN finds.
- Duplicate pairs: nearest level of different / related / same decides (no threshold). A paper's own code release counts as "same".
- A summary sentence passes only as "supports" with confidence ≥ 0.8; everything else is listed as unverified, never silently published as fact.
- Raw probabilities stay in `candidates.json` (`judge`), for kept and dropped items alike, so thresholds can be retuned without new calls.
- Answers are typed (`response_model` subclasses of `SystemOneResponse`), and requests retry on 429/5xx/timeouts (`RETRY` in `judge.py`).
- If TypeSafe is down: candidates fail open (unjudged items are kept and committed, the routine still runs); verify fails closed (nothing is marked, re-run the publish workflow to retry).
