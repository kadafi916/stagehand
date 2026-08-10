import asyncio
import logging

from ..utils import load_plugins, invoke_plugins
from .base import ProviderError

log = logging.getLogger('stagehand.providers')

plugins, broken_plugins = load_plugins('providers', ['thetvdb', 'tvmaze', 'tmdb'])

async def start(manager):
    """
    Called when the manager is starting.
    """
    await invoke_plugins(plugins, 'start', manager)
    for name, error in broken_plugins.items():
        log.warning('failed to load provider plugin %s: %s', name, error)
