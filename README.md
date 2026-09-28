# HUB

Daily AI/ML brief for a university student: every morning at 09:00 PT, three picks (입문, 중급, 심화) summarized in Korean, plus a Korean news-style video of them.

Live: https://hysk-cmd.github.io/hub/

## Agent workflow

A scheduled Claude cloud routine runs `ROUTINE.md` in this repo. Nothing runs on a laptop.

```mermaid
flowchart TD
    cron["Cloud routine<br/>cron 0 16,17 * * * (UTC)"] --> guard{"data/TODAY.json exists?<br/>or PT hour is 08?"}
    guard -- yes --> stop(["Stop, nothing to do"])
    guard -- no --> collect

    subgraph collect_step ["collect.py"]
        collect["Fetch sources<br/>HF Daily Papers, arXiv, Hacker News,<br/>Reddit, GitHub Trending, lab blogs"] --> corpus{"Overlaps the corpus?<br/>data/2*.json + data/seen.json<br/>by URL, arXiv id, title"}
        corpus -- yes --> drop(["Dropped"])
        corpus -- no --> xdup{"Same paper from<br/>two sources?"}
        xdup -- yes --> merge(["Kept once"])
        xdup -- no --> cands[("candidates.json")]
    end

    cands --> anth["WebFetch anthropic.com/news<br/>(grep data/ to skip known URLs)"]
    anth --> select["Agent selects exactly 3<br/>입문 / 중급 / 심화<br/>reads each source page"]
    select --> write["Write data/TODAY.json<br/>summary, why, keywords,<br/>headline_ko, narration"]
    write --> validate{"make_video.py --validate<br/>3 items in level order, fields,<br/>categories, no em-dash, not in corpus"}
    validate -- errors --> write
    validate -- OK --> video

    subgraph video_step ["make_video.py"]
        video["Split narration into sentences"] --> tts["Korean TTS per sentence<br/>edge-tts, gTTS fallback"]
        video --> slides["News slide per sentence<br/>og:image material, level tag,<br/>lower third, subtitle"]
        tts --> ffmpeg["ffmpeg: segment per slide, concat"]
        slides --> ffmpeg
        ffmpeg --> mp4[("videos/TODAY.mp4 + .jpg")]
    end

    mp4 --> publish["Prepend TODAY to data/index.json<br/>commit + push to main"]
    video -. "fails twice" .-> publish
    publish --> pages["GitHub Pages redeploy"] --> site(["Site: day view with video,<br/>category and level filters across the archive"])
```

## Files

| File | What it does |
|---|---|
| `ROUTINE.md` | Instructions the daily agent follows. Change selection rules and the schema here. |
| `collect.py` | Pulls candidates and removes anything already in the corpus. stdlib only. `python collect.py --check` self-tests. |
| `make_video.py` | Validates a day file and renders the news video. `--validate FILE`, `--check`. |
| `data/YYYY-MM-DD.json` | One day: 3 items. `data/index.json` lists the days. |
| `data/seen.json` | Extra URLs to never show again (items retired from the site). |
| `videos/` | Daily MP4 + poster JPG. |
| `index.html` | The site. No build step. Preview with `python -m http.server`. |

Local deps for the video: `pip install edge-tts gTTS pillow imageio-ffmpeg`.
