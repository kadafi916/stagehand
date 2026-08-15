import os
import urllib
import urllib.parse
import logging
import re
import json
import asyncio
import warnings
import aiohttp
from datetime import datetime
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# The Easynews RSS feed is XML, but we deliberately parse it with the
# html.parser backend (no extra lxml dependency needed, and it works fine
# since RSS tags are already lowercase). Silence the resulting warning
# rather than adding lxml just to satisfy it.
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

from ..config import config
from ..toolbox import dateutils
from ..toolbox.net import download
from .base import SearcherBase, SearchResult, SearcherError
from .easynews_config import config as modconfig


__all__ = ['Searcher', 'modconfig']

log = logging.getLogger('stagehand.searchers.easynews')

# Result of the last authenticated request: True (ok), False (auth failed),
# or None (no request made yet).  Exposed via /api/status for monitoring.
last_auth_ok = None


class Searcher(SearcherBase):
    NAME = 'easynews'
    PRINTABLE_NAME = 'Easynews Global Search'
    TYPE = 'http'

    DEFAULT_URL_GLOBAL5 = 'https://members.easynews.com/global5/index.html?gps={keywords}&sbj={subject}&from=&ns=&fil=&fex=&vc=&ac=&fty[]=VIDEO&s1=nsubject&s1d=%2B&s2=nrfile&s2d=%2B&s3=dsize&s3d=%2B&pby=500&u=1&svL=&d1={date}&d1t=&d2=&d2t=&b1={size}&b1t=&b2=&b2t=&px1={res}&px1t=&px2=&px2t=&fps1=&fps1t=&fps2=&fps2t=&bps1=&bps1t=&bps2=&bps2t=&hz1=&hz1t=&hz2=&hz2t=&rn1=&rn1t=&rn2=&rn2t=&fly=2&pno=1&sS=5'

    # Fallback JSON search API, used when global5 returns nothing (as of
    # 2026-08 it appears to have stopped returning results entirely, while
    # this endpoint -- confirmed against two independent reverse-engineered
    # clients, github.com/sleeyax/stremio-easynews-addon and
    # github.com/panteLx/easynews-plus-plus -- still works). Same Basic Auth
    # as global5, but no server-side subject/episode-code or size filter, so
    # we search by title alone and let the generic filename/subject matching
    # in SearcherBase.search() bucket results per episode.
    URL_V2 = 'https://members.easynews.com/2.0/search/solr-search/advanced'


    async def _search_global5(self, title, codes, size, date, res):
        if not modconfig.username or not modconfig.password:
            from .base import SearcherError
            raise SearcherError('Easynews credentials not configured')

        if 0 and os.path.exists('result.rss'):
            print('Using cached result.rss')
            return file('result.rss').read()

        url = modconfig.url or Searcher.DEFAULT_URL_GLOBAL5
        url = url.format(keywords=urllib.parse.quote_plus(title), subject=codes,
                         date=urllib.parse.quote_plus(date), size=size, res=res)
        global last_auth_ok
        status, rss = await download(url, retry=modconfig.retries,
                                     auth=aiohttp.BasicAuth(modconfig.username, modconfig.password))
        last_auth_ok = status not in (401, 403)
        if status in (401, 403):
            from .. import web
            web.notify('alert', title='Easynews Authentication Failed',
                       text='Easynews rejected your credentials.  Check the username and '
                            'password under Configure &rarr; Settings &rarr; Easynews.',
                       type='error')
            raise SearcherError('Easynews authentication failed (HTTP %d): check username/password' % status)
        elif status != 200:
            raise SearcherError('HTTP status not ok (%d)' % status)
        #file('result.rss', 'w').write(rss)
        return rss


    async def _search(self, series, episodes, date, min_size, quality):
        title = series.cfg.search_string or series.name
        # Strip problem characters from the title, and substitute alternative apostrophe
        title = self.clean_title(title, apostrophe=Searcher.CLEAN_APOSTROPHE_REGEXP)
        size = '%dM' % (min_size / 1048576) if min_size else '100M'
        # XXX: easynews doesn't support HEVC so remove resolution filtering.
        # res = '1x540' if quality == 'HD' else ''
        res = ''

        results = []
        use_v2 = False
        for i in range(0, len(episodes), 10):
            batch = episodes[i:i+10]
            codelist = [code for episode in batch \
                             for code in self._get_episode_codes_regexp_list([episode])]
            codes = '|'.join(codelist)

            if not use_v2:
                log.debug('searching for %d episodes, minimum size %s and res %s, keywords=%s subject=%s',
                          len(batch), size, res or 'any', title, codes)
                rss = await self._search_global5(title, codes, size, date or '', res)
                soup = BeautifulSoup(rss, 'html.parser')
                items = soup.find_all('item')
                if not items:
                    # global5 has been known to return a well-formed but
                    # entirely empty feed rather than an HTTP error when it's
                    # down, so this is the signal we use to switch over.
                    log.warning('global5 returned no results at all; falling back to v2 search API')
                    use_v2 = True
                else:
                    for item in items:
                        result = SearchResult(self)
                        urlpath = urllib.parse.urlparse(item.enclosure['url']).path
                        result.filename = urllib.parse.unquote(os.path.split(urlpath)[-1])
                        result.size = self._parse_hsize(item.enclosure['length'])
                        result.date = dateutils.from_rfc822(item.pubdate.contents[0])
                        result.subject = ''.join(item.title.contents)
                        result.url = item.enclosure['url']
                        # TODO: parse out newsgroup
                        results.append(result)

            if use_v2:
                # v2 has no per-batch code filtering, so a single query
                # covers every episode we're looking for in this show.
                log.debug('searching for %s via v2 search API', title)
                results.extend(await self._search_v2(title))
                break

        return {None: results}


    async def _search_v2(self, title):
        if not modconfig.username or not modconfig.password:
            raise SearcherError('Easynews credentials not configured')

        params = {
            'st': 'adv',
            'sb': '1',
            'fex': 'm4v,3gp,mov,divx,xvid,wmv,avi,mpg,mpeg,mp4,mkv,avc,flv,webm',
            'fty[]': 'VIDEO',
            'spamf': '1',
            'u': '1',
            'gx': '1',
            'pno': '1',
            'sS': '3',
            's1': 'dsize', 's1d': '-',
            's2': 'relevance', 's2d': '-',
            's3': 'dtime', 's3d': '-',
            'pby': '500',
            'safeO': '0',
            'gps': title,
        }
        url = Searcher.URL_V2 + '?' + urllib.parse.urlencode(params)
        global last_auth_ok
        status, data = await download(url, retry=modconfig.retries,
                                      auth=aiohttp.BasicAuth(modconfig.username, modconfig.password))
        last_auth_ok = status not in (401, 403)
        if status in (401, 403):
            from .. import web
            web.notify('alert', title='Easynews Authentication Failed',
                       text='Easynews rejected your credentials.  Check the username and '
                            'password under Configure &rarr; Settings &rarr; Easynews.',
                       type='error')
            raise SearcherError('Easynews authentication failed (HTTP %d): check username/password' % status)
        elif status != 200:
            raise SearcherError('v2 search API HTTP status not ok (%d)' % status)

        try:
            response = json.loads(data.decode('utf8') if isinstance(data, bytes) else data)
        except (ValueError, TypeError, AttributeError) as e:
            log.warning('v2 search API returned unparseable response: %s', e)
            return []

        down_url, dl_farm, dl_port = response.get('downURL'), response.get('dlFarm'), response.get('dlPort')
        if not (down_url and dl_farm and dl_port):
            log.warning('v2 search API response missing download URL fields')
            return []
        if down_url.startswith('//'):
            # downURL is protocol-relative in the raw API response; aiohttp
            # needs an actual scheme to fetch it.
            down_url = 'https:' + down_url

        results = []
        for f in response.get('data', []):
            if f.get('passwd') or f.get('virus') or str(f.get('type', '')).upper() != 'VIDEO':
                continue
            post_hash, post_title, ext = f.get('0'), f.get('10'), f.get('11')
            size = f.get('rawSize') or f.get('size')
            if not (post_hash and post_title and ext and size):
                continue

            result = SearchResult(self)
            result.filename = post_title + ext
            result.subject = result.filename
            result.size = int(size)
            ts = f.get('ts')
            result.date = datetime.fromtimestamp(ts) if ts else None
            result.url = '{}/{}/{}/{}{}/{}{}'.format(down_url, dl_farm, dl_port, post_hash, ext, post_title, ext)
            results.append(result)

        return results


    async def _get_retriever_data(self, search_result):
        return {
            'url': search_result.url,
            'username': modconfig.username,
            'password': modconfig.password,
            'retry': modconfig.retries
        }


    def _check_results_equal(self, a, b):
        try:
            # Easynews URLs contain hashes of the file, which is a convenient
            # value to compare, because it means that even different URLs can
            # end up being the same file.
            a_hash = re.search(r'/([0-9a-f]{32,})', a.url).group(1)
            b_hash = re.search(r'/([0-9a-f]{32,})', b.url).group(1)
            return a_hash == b_hash
        except AttributeError:
            # Wasn't able to find hash in URL, so compare the URLs directly.
            return a.url == b.url


def enable(manager):
    """
    Called by the web interface when the plugin is enabled where it was
    previously disabled.
    """
    # http retriever is always enabled, so no special action is needed
    # when the easynews searcher is enabled.
    pass
