# Stagehand

**Requires an [Easynews](https://easynews.com) account. Easynews is the only supported backend, by design — NZB/generic NNTP and BitTorrent support are out of scope.**

Stagehand is a TV series manager that automatically downloads new episodes and provides a web UI for managing your collection.

---

## Features

- Single-page web UI — no page reloads, hash-based routing
- Dark and light themes — toggle with the sun/moon icon in the nav bar (persisted per browser)
- Multiple metadata providers per series (TheTVDB and TVmaze)
- Easynews HTTP global search (enabled by default)
- Per-episode and per-season status management
- Live log streaming in the browser
- Full settings UI — no config file editing required for common options
- Home Assistant integration — status sensors via `/api/status` and per-episode webhook events
- Email and Kodi notifications on download completion
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
| TV library | Click **TV Shows** in the nav bar — toggle between banner grid and a sortable list view |
| Add a series | Search box in the nav bar, or click **Add TV Show** |
| Show detail & episodes | Click any banner in the library |
| Upcoming episodes | Click **Upcoming** — the next 7/14/30 days grouped by day |
| Downloads | Click **Downloads** in the nav bar |
| Download history | Click **History** — every completed download with time, quality, and size |
| Statistics | Click **Stats** — show/episode counts, a 30-day download chart, disk usage, per-show totals |
| Settings & log | Click **Configure** in the nav bar |

Download history is recorded to `history.jsonl` next to the database from 0.4.18 onward, so the History page and download stats start accumulating from upgrade time.

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

### Season offset

Sometimes releases are posted with a different season number than TheTVDB/TVmaze use (e.g. the provider says season 2 but files are posted as `S03E06`). Set **Season Offset** in the show's Advanced Settings to the difference (in that example, `1`). The offset applies to searching and result matching only — the library, episode list, and file naming keep the provider's numbering.

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
| Home Assistant | Enable toggle + webhook URL (see Home Assistant integration below) |
| Email Notifications | Enable toggle, SMTP host/port/SSL, optional auth, sender, recipients |
| Kodi | Enable toggle, hostname, HTTP port, username/password, on-screen notification, per-show library update, path remapping. Requires "Allow remote control via HTTP" in Kodi (Settings → Services → Control). |
| Episode Check Schedule | Checkboxes for each hour of the day; quick-select All / None / Every 2h / Every 4h |
| System | Trigger an immediate episode check |

When a notifier is enabled, it fires after episodes finish downloading: Home Assistant gets one webhook event per episode, Email gets a summary message per batch, and Kodi gets an on-screen notification plus a library refresh.

---

## Home Assistant integration

There are two halves, usable independently: **sensors** (Home Assistant polls Stagehand) and **events** (Stagehand pushes to Home Assistant when an episode is downloaded).

### Sensors

Stagehand exposes an aggregate status document at `GET /api/status`:

```json
{
  "version": "0.4.14",
  "downloads": { "active": 1, "queued": 2, "speed_kbps": 4200,
                 "current": [{ "show": "...", "code": "s01e01", "percent": 42.0,
                               "mb_done": 800.0, "mb_total": 1900.0, "speed_kbps": 4200 }] },
  "episodes": { "needed": 3, "airing_today": 2, "airing_today_list": [ ... ],
                "downloaded_today": 1, "downloaded_this_week": 5 },
  "shows": { "count": 12, "paused": 1 },
  "next_check": "2026-07-06T18:34:00-04:00",
  "tvdir_free_gb": 512.3,
  "easynews_ok": true
}
```

Add a RESTful sensor group to Home Assistant's `configuration.yaml` (one HTTP request feeds all sensors):

```yaml
rest:
  - resource: http://YOUR_NAS:8088/api/status
    scan_interval: 60
    # If you enabled Web Access auth in Stagehand:
    # authentication: basic
    # username: !secret stagehand_user
    # password: !secret stagehand_pass
    sensor:
      - name: Stagehand Active Downloads
        value_template: "{{ value_json.downloads.active }}"
      - name: Stagehand Queued Downloads
        value_template: "{{ value_json.downloads.queued }}"
      - name: Stagehand Download Speed
        value_template: "{{ value_json.downloads.speed_kbps }}"
        unit_of_measurement: "kB/s"
      - name: Stagehand Episodes Needed
        value_template: "{{ value_json.episodes.needed }}"
      - name: Stagehand Airing Today
        value_template: "{{ value_json.episodes.airing_today }}"
        json_attributes_path: "$.episodes"
        json_attributes: ["airing_today_list"]
      - name: Stagehand Downloaded This Week
        value_template: "{{ value_json.episodes.downloaded_this_week }}"
      - name: Stagehand Next Check
        value_template: "{{ value_json.next_check }}"
        device_class: timestamp
      - name: Stagehand TV Free Space
        value_template: "{{ value_json.tvdir_free_gb }}"
        unit_of_measurement: "GB"
    binary_sensor:
      - name: Stagehand Downloading
        value_template: "{{ value_json.downloads.active > 0 }}"
        device_class: running
      - name: Stagehand Easynews OK
        value_template: "{{ value_json.easynews_ok != false }}"
        device_class: problem
```

`downloaded_today` / `downloaded_this_week` count downloaded episodes by their air date. `easynews_ok` is `null` until the first search after startup, then `true`/`false` based on whether Easynews accepted your credentials.

### Events (webhook)

1. In Home Assistant, create an automation with a **Webhook** trigger and choose an ID, e.g. `stagehand`. The webhook URL is then `http://YOUR_HA:8123/api/webhook/stagehand`.
2. In Stagehand, go to **Configure → Settings → Home Assistant**, check **Enabled**, paste the webhook URL, and click Save.

Each downloaded episode sends a JSON POST:

```json
{
  "event": "episode_downloaded",
  "show": "Some Show",
  "code": "s01e04",
  "season": 1,
  "episode": 4,
  "title": "Episode Title",
  "filename": "Some.Show.s01e04.mkv",
  "overview": "..."
}
```

Example automation — announce a download on a media player:

```yaml
automation:
  - alias: Stagehand episode downloaded
    # queued is important: parallel downloads finish together and send
    # webhooks milliseconds apart. The default mode (single) silently drops
    # triggers that arrive while a previous run is still executing.
    mode: queued
    max: 10
    triggers:
      - trigger: webhook
        webhook_id: stagehand
        local_only: true
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "Episode downloaded"
          message: "{{ trigger.json.show }} {{ trigger.json.code }} — {{ trigger.json.title }}"
```

### Quality preference and result ranking

Each show's quality setting (UHD / HD / SD / Any) controls three things — which resolutions are allowed, the minimum acceptable file size, and the "ideal" size used for ranking. Sizes scale with the show's runtime; the show's Advanced Settings display the computed numbers for the selected tier.

| Setting | Resolutions | Min size | Ideal size |
|---------|-------------|----------|------------|
| UHD | up to 2160p (prefers 2160p) | 30 MB/min | 120 MB/min |
| HD | 1080p/720p — 2160p rejected | 10 MB/min | 25 MB/min |
| SD | below 720p only | 2 MB/min | 8 MB/min |
| Any | anything (prefers highest) | 2 MB/min | 20 MB/min |

For a typical 42-minute HD show that means: files under ~420 MB are rejected, and ~1 GB is considered ideal.

Candidate results are then ranked by comparing these criteria **in order** — a result that wins on an earlier criterion wins outright, and later criteria only break ties:

1. **Filename match** — the episode code + show title found in the actual filename beats a match only in the post subject
2. **No audio description** — "with Audio Description" releases rank below every clean alternative regardless of resolution or size, and are only used when nothing else is available
3. **Container** — mkv > mp4 > avi; wmv/mpg/ts/rar are disqualified
4. **Resolution** — 2160p > 1080p > 720p (within what the tier allows)
5. **Codec/audio** — resolution-aware: x264 preferred for HD (device compatibility), x265 preferred for 2160p (the 4K standard); surround audio (DDP/EAC-3/AC3/TrueHD/DTS) is a bonus and Atmos a bigger one; AAC is penalized
6. **Size** — results between 0.6× and 4× of ideal are "in range" and bigger wins; out-of-range results rank below in-range ones, closest to ideal first
7. **Release modifiers** — blu-ray > proper > repack > web-dl, etc.
8. **Post date** — newer wins

Every search logs its ranked results with the reasons, e.g.:

```
result: 1. <SearchResult Some.Show.S01E04.1080p.WEB-DL.DDP5.1.H.264-GRP.mkv> [mkv, 1080p, x264+surround audio, 1.4x ideal size, web-dl]
disqualifying result <...2160p...>: 2160p exceeds HD quality setting
disqualifying result <...>: size 210MB below tier minimum 420MB
```

The winning result's ranking summary is also recorded in the download history — click any row on the History page to see the original release name, what it was renamed to, and why that file was picked.

---

## Known limitations

- Timezone-aware airdate handling (airtimes are compared against server local time)
- Various minor FIXMEs and TODOs in the source

NZB/generic NNTP, BitTorrent, and import of an existing TV library are intentionally out of scope and will not be implemented.
