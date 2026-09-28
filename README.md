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
        xdup -- no --> cands[("candidates.json<br/>committed to main")]
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
        render["make_video.py for days without a video"] --> tts["Korean TTS per sentence<br/>edge-tts, gTTS fallback"]
        render --> slides["News slide per sentence<br/>og:image material, level tag,<br/>lower third, subtitle"]
        tts --> ffmpeg["ffmpeg: segment per slide, concat"]
        slides --> ffmpeg
        ffmpeg --> mp4[("videos/TODAY.mp4 + .jpg<br/>committed")]
        mp4 --> deploy["Deploy GitHub Pages"]
    end

    push --> render
    deploy --> site(["Site: day view with video,<br/>category and level filters across the archive"])
```

## Files

| File | What it does |
|---|---|
| `ROUTINE.md` | Instructions the daily Claude routine follows. Change selection rules and the schema here. |
| `collect.py` | Pulls candidates and removes anything already in the corpus. stdlib only. `python collect.py --check` self-tests. |
| `make_video.py` | Validates a day file and renders the news video. `--validate FILE`, `--check`. |
| `.github/workflows/collect.yml` | Morning run of `collect.py`, commits `candidates.json`. |
| `.github/workflows/publish.yml` | On push: renders missing videos, commits them, deploys Pages. |
| `data/YYYY-MM-DD.json` | One day: 3 items. `data/index.json` lists the days. |
| `data/seen.json` | Extra URLs to never show again (items retired from the site). |
| `videos/` | Daily MP4 + poster JPG. |
| `index.html` | The site. No build step. Preview with `python -m http.server`. |

Local deps for the video: `pip install edge-tts gTTS pillow imageio-ffmpeg`.
