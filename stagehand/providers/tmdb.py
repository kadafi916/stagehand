import logging
import urllib
import time
import json
import asyncio
import itertools

from .base import ProviderBase, ProviderSearchResultBase, ProviderError
from ..toolbox import db
from ..toolbox.net import download
from ..toolbox.utils import tostr
from ..config import config
from .tmdb_config import config as modconfig

__all__ = ['Provider', 'modconfig']

log = logging.getLogger('stagehand.providers.tmdb')

IMAGE_BASE = 'https://image.tmdb.org/t/p/original'


class ProviderSearchResult(ProviderSearchResultBase):
    @property
    def pid(self):
        return str(self._attrs.get('id'))

    @property
    def name(self):
        return self._attrs.get('name')

    @property
    def names(self):
        yield self.name

    @property
    def overview(self):
        return self._attrs.get('overview')

    @property
    def imdb(self):
        # Not available in search results; only on the series details call.
        return None

    @property
    def year(self):
        started = self.started
        if started and len(started.split('-')) == 3:
            return started.split('-')[0]
        else:
            return started

    @property
    def started(self):
        return self._attrs.get('first_air_date')

    @property
    def banner(self):
        path = self._attrs.get('backdrop_path') or self._attrs.get('poster_path')
        if path:
            return IMAGE_BASE + path


class Provider(ProviderBase):
    NAME = 'tmdb'
    NAME_PRINTABLE = 'TMDB'
    IDATTR = 'tmdbid'
    CACHEATTR = 'tmdbcache'

    def __init__(self, db):
        super().__init__(db)
        self.hostname = 'https://www.themoviedb.org'

        db.register_object_type_attrs('series',
            tmdbid = (str, db.ATTR_SEARCHABLE | db.ATTR_INDEXED),
            tmdbcache = (dict, db.ATTR_SIMPLE)
        )

        db.register_object_type_attrs('episode',
            tmdbid = (str, db.ATTR_SEARCHABLE),
        )


    async def _api(self, path, params=None):
        """
        Invokes a TMDB v3 API method.  Returns (status, response).

        A missing or rejected API key surfaces as a ProviderError rather than
        a plain non-200 status, since it's a configuration problem the user
        needs to know about (not a transient failure like other providers'
        non-200 handling).
        """
        apikey = str(modconfig.apikey).strip()
        if not apikey:
            raise ProviderError('TMDB API key not configured (Configure -> Settings -> TMDB)')

        query = dict(params or {})
        query['api_key'] = apikey
        query.setdefault('language', config.misc.language.lower())
        url = 'https://api.themoviedb.org/3' + path + '?' + urllib.parse.urlencode(query)
        headers = {'Accept': 'application/json'}
        status, data = await download(url, retry=4, headers=headers)
        response = json.loads(data.decode('utf8')) if data else None
        if status == 401:
            raise ProviderError('TMDB API rejected the configured API key')
        log.debug('API %s returned status %d', path, status)
        return status, response


    async def search(self, name):
        results = []
        quoted = urllib.parse.quote(name.replace('-', ' ').replace('_', ' '))
        log.info('searching TMDB for %s', name)
        status, response = await self._api('/search/tv', {'query': quoted})
        if status == 200:
            if 'results' not in response:
                log.warning('results element missing from response')
            else:
                for result in response['results']:
                    results.append(ProviderSearchResult(self, result))
        return results


    async def get_series(self, id):
        log.debug('retrieving series data for %s', id)
        if not self.get_last_updated():
            # DB doesn't know about server time.  Set to current time so that
            # subsequent calls to get_changed_series_ids() have a reference
            # point.
            self.db.set_metadata('tmdb::servertime', int(time.time()))

        series = {'episodes': []}
        log.info('fetching series %s from TMDB', id)
        status, data = await self._api('/tv/' + id, {'append_to_response': 'external_ids'})
        if status != 200 or not data or 'id' not in data:
            return series

        try:
            runtimes = data.get('episode_run_time') or []
            if runtimes:
                series['runtime'] = int(runtimes[0])
        except (ValueError, TypeError):
            pass

        # Get any existing series and see if we need to fetch banner data.
        existing = self.db.get_series_by_id('tmdb:{}'.format(data['id']))
        missing = not existing or not existing.banner_data
        image_path = data.get('backdrop_path') or data.get('poster_path')
        if missing and image_path:
            url = IMAGE_BASE + image_path
            log.debug('refresh series banner %s', url)
            status, banner_data = await download(url, retry=3)
            if status == 200:
                series['banner_data'] = banner_data
            else:
                log.error('banner download failed for series %s', data.get('name', data['id']))

        from ..tvdb import Series
        status_str = (data.get('status') or '').lower()
        if status_str in ('returning series', 'in production', 'planned', 'pilot'):
            status = Series.STATUS_RUNNING
        elif status_str in ('ended', 'canceled', 'cancelled'):
            status = Series.STATUS_ENDED
        else:
            status = Series.STATUS_UNKNOWN

        series.update({
            'id': str(data['id']),
            'name': data.get('name'),
            'poster': IMAGE_BASE + data['poster_path'] if data.get('poster_path') else None,
            'banner': IMAGE_BASE + data['backdrop_path'] if data.get('backdrop_path') else None,
            'overview': data.get('overview'),
            'genres': [g['name'].strip().lower() for g in data.get('genres', []) if g.get('name')],
            'started': data.get('first_air_date'),
            'status': status,
            'imdbid': (data.get('external_ids') or {}).get('imdb_id')
        })

        # TMDB has no flat "all episodes" endpoint; fetch each season
        # individually based on the seasons list in the series details.
        for season in data.get('seasons', []):
            season_number = season.get('season_number')
            if season_number is None or not season.get('episode_count'):
                continue
            status, sdata = await self._api('/tv/{}/season/{}'.format(id, season_number))
            if status != 200 or not sdata:
                continue
            for episode in sdata.get('episodes', []):
                try:
                    series['episodes'].append({
                        'id': str(episode['id']),
                        'name': episode.get('name'),
                        'season': int(episode['season_number']),
                        'episode': int(episode['episode_number']),
                        'airdate': episode.get('air_date'),
                        'overview': episode.get('overview')
                    })
                except Exception as e:
                    log.exception("failed to extract episode details: %s %s", e, episode)

        return series


    async def get_changed_series_ids(self):
        servertime = self.get_last_updated()
        if not servertime:
            # No servertime stored, so there must not be any series in db.
            return
        now = int(time.time())

        series = set([o[self.IDATTR] for o in self.db.query(type='series', attrs=[self.IDATTR])])
        if now - servertime > 60*60*24*14:
            # TMDB's changes endpoint only covers the last 14 days.
            log.warning("haven't updated in over 14 days, returning all series")
            self.db.set_metadata('tmdb::servertime', now)
            return list(series)

        ids = []
        start = time.strftime('%Y-%m-%d', time.gmtime(servertime))
        end = time.strftime('%Y-%m-%d', time.gmtime(now))
        for page in itertools.count(1):
            status, response = await self._api('/tv/changes', {'start_date': start, 'end_date': end, 'page': page})
            if status != 200 or not response or 'results' not in response:
                break
            for result in response['results']:
                if 'id' in result:
                    ids.append(str(result['id']))
            if page >= response.get('total_pages', 1):
                break
        self.db.set_metadata('tmdb::servertime', now)
        log.debug('set servertime %s', now)
        return ids


    def get_last_updated(self):
        return int(self.db.get_metadata('tmdb::servertime', 0))
