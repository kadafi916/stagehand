import json
import logging
import re
import os
import time
import asyncio
import aiohttp

from ..config import config
from .base import NotifierBase, NotifierError
from .xbmc_config import config as modconfig

__all__ = ['Notifier']

log = logging.getLogger('stagehand.notifiers.kodi')


class Notifier(NotifierBase):
    """
    Kodi notifier using HTTP JSON-RPC (Settings -> Services -> Control ->
    "Allow remote control via HTTP" must be enabled in Kodi).
    """

    async def _jsonrpc(self, session, method, params=None):
        request = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params or {},
            'id': 1,
        }
        log.debug2('issuing JSON-RPC method=%s params=%s', method, params)
        url = 'http://%s:%d/jsonrpc' % (str(modconfig.hostname), int(modconfig.http_port))
        async with session.post(url, json=request,
                                timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 401:
                raise NotifierError('Kodi rejected credentials: check username/password')
            elif resp.status != 200:
                raise NotifierError('Kodi JSON-RPC returned HTTP %d' % resp.status)
            response = await resp.json()
        if 'error' in response:
            raise NotifierError('Kodi JSON-RPC error: %s' % response['error'])
        return response.get('result')


    async def _wait_for_idle(self, session, timeout=120):
        t0 = time.time()
        while time.time() - t0 < timeout:
            result = await self._jsonrpc(session, 'XBMC.GetInfoBooleans',
                                         {'booleans': ['Library.IsScanningVideo']})
            if not result or result.get('Library.IsScanningVideo') != True:
                return True
            log.debug2('Kodi busy scanning, waiting')
            await asyncio.sleep(1)
        return False


    async def _do_notify(self, episodes):
        auth = None
        if str(modconfig.username):
            auth = aiohttp.BasicAuth(str(modconfig.username), str(modconfig.password))

        async with aiohttp.ClientSession(auth=auth) as session:
            result = await self._jsonrpc(session, 'JSONRPC.Version')
            if result:
                v = result.get('version', {})
                log.debug('Kodi JSON-RPC version %s.%s', v.get('major', '?'), v.get('minor', '?'))

            dirs = set(ep.series.path for ep in episodes)
            if modconfig.tvdir:
                frm = os.path.normpath(str(config.misc.tvdir)) + '/'
                to = os.path.normpath(str(modconfig.tvdir)) + '/'
                dirs = set(re.sub(r'^' + re.escape(frm), to, d + '/').rstrip('/') for d in dirs)

            await self._wait_for_idle(session)
            if modconfig.individual:
                for d in dirs:
                    await self._jsonrpc(session, 'VideoLibrary.Scan',
                                        {'directory': d + '/', 'showdialogs': False})
                    await self._wait_for_idle(session)
            else:
                await self._jsonrpc(session, 'VideoLibrary.Scan', {'showdialogs': False})

            if modconfig.notify:
                if len(episodes) == 1:
                    ep = episodes[0]
                    msg = '%s %s available.' % (ep.series.name, ep.code)
                else:
                    msg = '%d new episodes added to library.' % len(episodes)
                await self._jsonrpc(session, 'GUI.ShowNotification',
                                    {'title': 'New TV Episodes', 'message': msg,
                                     'displaytime': 8000})

        log.info('updated Kodi library with %d episodes', len(episodes))


    async def _notify(self, episodes):
        try:
            await self._do_notify(episodes)
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            log.error('could not reach Kodi at %s:%s: %s',
                      modconfig.hostname, modconfig.http_port, e or 'timeout')
        except NotifierError as e:
            log.error('%s', e.args[0])
