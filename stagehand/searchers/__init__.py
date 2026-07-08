import logging
import re
from datetime import timedelta
import asyncio

from ..utils import load_plugins, invoke_plugins
from ..config import config
from .base import SearcherError, SearchResult

log = logging.getLogger('stagehand.searchers')

plugins, broken_plugins = load_plugins('searchers', ['easynews'])

# For each quality tier: (minimum MB per minute, ideal MB per minute).
# A result smaller than runtime * min is disqualified; ideal drives the
# size portion of result ranking.
QUALITY_SIZES = {
    'UHD': (30, 120),
    'HD': (10, 25),
    'SD': (2, 8),
    'Any': (2, 20),
}

# Which resolutions each tier accepts (2160p is disqualified for HD, etc).
QUALITY_RESOLUTIONS = {
    'UHD': '2160p, 1080p or 720p (prefers 2160p)',
    'HD': '1080p or 720p (prefers 1080p; 2160p rejected)',
    'SD': 'below 720p only',
    'Any': 'anything (prefers highest)',
}

async def start(manager):
    """
    Called when the manager is starting.
    """
    await invoke_plugins(plugins, 'start', manager)
    for name, error in broken_plugins.items():
        log.warning('failed to load searcher plugin %s: %s', name, error)


async def search(series, episodes, skip=[], loop=None):
    try:
        earliest = min(ep.airdate for ep in episodes if ep.airdate)
    except ValueError:
        # Empty sequence: no eps had an airdate.
        earliest = None
    if earliest:
        # Allow for episodes to be posted 10 days before the supposed
        # air date.
        earliest = (earliest - timedelta(days=10)).strftime('%Y-%m-%d')

    mb_per_min = QUALITY_SIZES[str(series.cfg.quality) or 'Any']
    runtime = series.runtime or 30
    min_size_bytes = runtime * mb_per_min[0] * 1024 * 1024
    ideal_size_bytes = runtime * mb_per_min[1] * 1024 * 1024

    tried = set()
    always = [name for name in plugins if plugins[name].Searcher.ALWAYS_ENABLED]
    for name in config.searchers.enabled + always:
        if name not in plugins or name in skip or name in tried:
            continue
        tried.add(name)
        searcher = plugins[name].Searcher(loop=loop)
        try:
            results = await searcher.search(series, episodes, earliest, min_size_bytes, ideal_size_bytes, series.cfg.quality)
        except SearcherError as e:
            log.warning('%s failed: %s', name, e.args[0])
        except Exception:
            log.exception('%s failed with unhandled error', name)
        else:
            # FIXME: if some episodes don't have results, need to try other searchers.
            if results:
                return results
            else:
                log.debug2('%s found no results', name)
    return {}
