import logging
import aiohttp

from .base import NotifierBase
from .homeassistant_config import config as modconfig

__all__ = ['Notifier', 'modconfig']

log = logging.getLogger('stagehand.notifiers.homeassistant')


class Notifier(NotifierBase):
    async def _notify(self, episodes):
        url = str(modconfig.url).strip()
        if not url:
            log.error('Home Assistant webhook URL not configured, skipping notification')
            return

        async with aiohttp.ClientSession() as session:
            for ep in episodes:
                payload = {
                    'event': 'episode_downloaded',
                    'show': ep.series.name,
                    'code': ep.code,
                    'season': ep.season.number,
                    'episode': ep.number,
                    'title': ep.name or '',
                    'filename': ep.filename or '',
                    'overview': ep.overview or '',
                }
                try:
                    async with session.post(url, json=payload,
                                            timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status >= 400:
                            log.error('Home Assistant webhook returned HTTP %d', resp.status)
                        else:
                            log.info('sent Home Assistant webhook for %s %s', ep.series.name, ep.code)
                except aiohttp.ClientError as e:
                    log.error('failed to reach Home Assistant webhook: %s', e)
