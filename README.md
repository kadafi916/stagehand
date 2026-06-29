# Stagehand

**This software is somewhat half-baked. It only works (though it works well)
if you have an [Easynews](https://easynews.com) account. Generic NNTP isn't
supported yet (but help is welcome).**


## What it is

Stagehand is a manager for your favourite TV series. It automatically
downloads new episodes of the TV shows in your library, and provides a
convenient web interface for managing your collection.

Key features:

* Modern dark single-page UI (Semantic UI, plain ES6 — no CoffeeScript required)
* Support for multiple TV metadata providers (TheTVDB and TVmaze): choose the authoritative provider per series
* Exclusive support for Easynews HTTP-based global search
* Per-episode status management: mark episodes as Needed, Ignored, or delete and re-download
* Runs on Python 3.11+ (Docker image uses Python 3.13)

## What it isn't

The core is quite robust, but several features are missing:

* NZB and NNTP support (for non-Easynews Usenet services): the most critical missing piece
* BitTorrent
* Web-based settings UI (credentials must be set in the config file for now)
* Ability to import an existing TV library
* ... and a bazillion FIXMEs and TODOs in the source


## How to run it

The included `Dockerfile` is the easiest way to get started.

```bash
docker build -t stagehand .

docker run -d -p 8088:8088 \
  -v $HOME/.config/stagehand:/root/.config/stagehand \
  -v /path/to/tv:/tv \
  stagehand
```

Change `/path/to/tv` to the directory where you want episodes saved.

The web interface is at **http://localhost:8088**.


## How to configure it

Settings are managed via a plain-text config file. On first run Stagehand
creates it at `~/.config/stagehand/config` (inside the container this maps
to the host path you mounted above).

To enable Easynews search, append these lines:

```
searchers.enabled[+] = easynews
searchers.easynews.username = your_easynews_username
searchers.easynews.password = your_easynews_password
```

No restart needed — Stagehand watches the config file and picks up changes
automatically.


## Using the UI

| Page | How to get there |
|------|-----------------|
| TV library | Click **TV Shows** in the nav bar |
| Add a series | Click **Add TV Show** or use the search box in the nav bar |
| Show detail & episodes | Click any banner in the library |
| Mark an episode | On the show detail page, click the colored **●** next to any episode |
| Downloads | Click **Downloads** in the nav bar |

### Episode status dots

| Color | Meaning |
|-------|---------|
| 🟢 Green | Downloaded |
| 🩷 Pink | Needed (will be downloaded) |
| ⚫ Gray | Ignored or not yet aired |

Click any dot to open an action menu: **Mark as Needed**, **Mark as Ignored**, or **Delete File + Ignore**.
