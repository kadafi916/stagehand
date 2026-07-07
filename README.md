# Stagehand

**Requires an [Easynews](https://easynews.com) account. Easynews is the only supported backend, by design — NZB/generic NNTP and BitTorrent support are out of scope.**

Stagehand is a TV series manager that automatically downloads new episodes and provides a web UI for managing your collection.

---

## Features

- Dark single-page web UI — no page reloads, hash-based routing
- Multiple metadata providers per series (TheTVDB and TVmaze)
- Easynews HTTP global search (enabled by default)
- Per-episode and per-season status management
- Live log streaming in the browser
- Full settings UI — no config file editing required for common options
- Python 3.11+ (Docker image uses Python 3.13)

---

## Quick start

```bash
docker build -t stagehand .

docker run -d -p 8088:8088 \
  -v $HOME/.config/stagehand:/root/.config/stagehand \
  -v /path/to/tv:/tv \
  stagehand
```

Open **http://localhost:8088** in your browser.

---

## Configuration

On first run Stagehand creates `~/.config/stagehand/config` (mapped from the host path above). Most settings are now configurable through the **Settings** page in the UI. The config file is watched for changes and picked up without a restart.

### Easynews credentials

Enter your username and password in **Configure → Settings → Easynews**. Easynews is enabled automatically once credentials are saved.

Alternatively, add them directly to the config file:

```
searchers.easynews.username = your_username
searchers.easynews.password = your_password
```

---

## Using the UI

| Page | How to get there |
|------|-----------------|
| TV library | Click **TV Shows** in the nav bar |
| Add a series | Search box in the nav bar, or click **Add TV Show** |
| Show detail & episodes | Click any banner in the library |
| Downloads & history | Click **Downloads** in the nav bar |
| Settings & log | Click **Configure** in the nav bar |

### Episode status dots

Each episode has a colored dot showing its status. Click a dot to open the action menu.

| Color | Meaning |
|-------|---------|
| Green | Downloaded |
| Pink | Needed — queued for download |
| Gray | Ignored or not yet aired |

Actions: **Mark as Needed**, **Mark as Ignored**, **Delete File + Ignore**

**Mark as Needed** triggers an immediate search regardless of airtime. This is useful for episodes that aired before you added the show (which are auto-ignored on add), episodes you previously ignored and want back, or to force a search now rather than waiting for the next scheduled check. Future episodes are downloaded automatically on schedule without needing to be marked.

A notification is shown after every status change — single episode or full season. Each download also produces a notification when it completes, and clear error notifications are shown for permission problems on the TV directory or bad Easynews credentials.

Pausing a show cancels any of its queued or in-progress downloads (with a notification).

### Season actions

Click the **⋯** button on any season header to apply an action to the entire season at once.

### Per-show folder options

Each show's detail page has two folder controls:

| Option | Effect |
|--------|--------|
| Flatten Seasons | Store all episodes in the show folder with no season subdirectory |
| No Show Folder | Save episodes directly in the TV root — no show subdirectory at all |

These can be combined or used independently per show.

### Downloads page

Active downloads show a progress bar with MB transferred and speed. The page updates automatically when the queue changes — no manual refresh needed.

---

## Settings UI

All common settings are available under **Configure → Settings**. Every section has an explicit **Save** button — nothing is written to disk until you click it.

| Section | Options |
|---------|---------|
| General | TV directory, metadata language, log level |
| Downloads | Max parallel downloads, quality preference (SD / HD / UHD) |
| File Naming | Optional rename toggle; when enabled: word separator, episode code style (`s01e02` / `1x02`), season directory format, episode filename format with live preview. Disable rename to keep original source filenames. |
| Web Access | Optional HTTP basic auth (username + password) |
| Easynews | Username and password |
| Episode Check Schedule | Checkboxes for each hour of the day; quick-select All / None / Every 2h / Every 4h |
| System | Trigger an immediate episode check |

### Quality preference

The quality setting controls both the minimum acceptable file size and which resolutions are allowed:

| Setting | Accepted resolutions | Preferred |
|---------|----------------------|-----------|
| UHD | 2160p, 1080p, 720p | 2160p |
| HD | 1080p, 720p | 1080p |
| SD | below 720p | highest available |

2160p results are automatically disqualified when HD is selected, so a 4K result will never be downloaded when you want HD. Resolution is evaluated before codec and file size, so a 1080p file always beats a 720p file. Within the same resolution, codec preference is resolution-aware: x264 is preferred for HD (wider device compatibility), x265/HEVC is preferred for UHD (standard for 4K). Surround/lossless audio (DDP, TrueHD, DTS, AC3) is preferred over AAC.

---

## Known limitations

- Timezone-aware airdate handling (airtimes are compared against server local time)
- Various minor FIXMEs and TODOs in the source

NZB/generic NNTP, BitTorrent, and import of an existing TV library are intentionally out of scope and will not be implemented.
