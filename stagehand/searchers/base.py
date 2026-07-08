import os
import re
import asyncio
import logging
import unicodedata

from ..config import config
from ..utils import remove_stop_words


log = logging.getLogger('stagehand.searchers')


class SearcherError(Exception):
    pass

class SearcherBase:
    # Values must be supplied by subclasses.
    # The internal name of the plugin (lowercase, no spaces).
    NAME = None
    # The human-readable name for the plugin.
    PRINTABLE_NAME = None
    # The type of retriever plugin required to fetch search results of this
    # searcher.
    TYPE = None
    # False if the user may disable the plugin, or True if it is always active.
    ALWAYS_ENABLED = False


    # Constants for clean_title()
    CLEAN_APOSTROPHE_LEAVE = 0
    CLEAN_APOSTROPHE_REMOVE = 1
    CLEAN_APOSTROPHE_REGEXP = 2

    def __init__(self, loop=None):
        super().__init__()
        self._loop = loop or asyncio.get_event_loop()


    def _parse_hsize(self, size):
        if isinstance(size, int):
            return size

        parts = size.lower().split()
        if not parts:
            return 0
        sz = float(parts[0].replace(',', ''))
        if len(parts) == 2:
            mult = {
                'gib': 1024*1024*1024,
                'gb': 1000*1000*1000,
                'mib': 1024*1024,
                'mb': 1000*1000,
                'kib': 1024,
                'kb': 1000
            }.get(parts[1], 1)
            return int(sz * mult)
        return int(sz)


    # Result ranking tables.  Results are sorted by comparing score vectors
    # built in this priority order (see _score_result):
    #   1. filename match (vs. subject-only match)
    #   2. container extension
    #   3. resolution
    #   4. A/V format (codec preference is resolution-aware)
    #   5. size relative to the quality tier's ideal
    #   6. release modifiers (proper, repack, source group...)
    #   7. post date
    RESULT_EXTS = {'mkv': 3, 'mp4': 2, 'avi': 1}
    RESULT_BAD_EXTS = ('wmv', 'mpg', 'ts', 'rar', r'r\d\d')
    RESULT_RES = {'2160p': 3, '1080p': 2, '720p': 1}
    RESULT_MODS = {r'blu-?ray': 10, 'proper': 9, r're-?pack': 7, 'immerse': 6,
                   'dimension': 5, 'nlsubs': 4, 'web-?dl': 3}
    GOOD_AUDIO = r'(ac-?3|e-?ac-?3|ddp[\d.]*|truehd|dts|dd5\.?1)'

    def _score_result(self, ep, ideal_size, result):
        """
        Score a single search result.

        :returns: (key, labels) where key is a tuple that sorts higher for
                  better results, and labels is a list of human-readable
                  strings explaining the score.

        Sets result.disqualified/disqualify_reason for results that must not
        be used regardless of rank.
        """
        name = result.filename.lower()
        ext = os.path.splitext(name)[-1].lstrip('.')
        labels = []

        def find(pattern):
            return re.search(r'[-. ]%s[-. $]' % pattern, name)

        # 1. Filename match beats subject-only match.
        match = 1 if self._is_name_for_episode(result.filename, ep) else 0
        if not match:
            labels.append('subject match only')

        # 2. Container extension.
        ext_score = 0
        for pattern in self.RESULT_BAD_EXTS:
            if re.match(pattern + '$', ext):
                result.disqualified = True
                result.disqualify_reason = 'unwanted extension .%s' % ext
        for e, score in self.RESULT_EXTS.items():
            if re.match(e + '$', ext):
                ext_score = score
                labels.append(e)

        # 3. Resolution.
        res_score = 0
        res_label = None
        for r, score in self.RESULT_RES.items():
            if find(r):
                res_score, res_label = score, r
        labels.append(res_label or 'unknown resolution')

        # 4. A/V format.  Codec preference is resolution-aware: x265 preferred
        # for 2160p (HEVC is the 4K standard), x264 preferred otherwise
        # (better device compatibility).
        v265 = bool(find(r'[xh]\.?265'))
        v264 = bool(find(r'[xh]\.?264'))
        good_audio = bool(find(self.GOOD_AUDIO))
        aac = bool(find(r'aac\.?2?'))
        av_score = 0
        if aac:
            av_score = -1
            labels.append('AAC audio')
        elif v264 or v265:
            prefer265 = res_label == '2160p'
            preferred = v265 if prefer265 else v264
            av_score = (11 if preferred else 9) + (1 if good_audio else 0)
            labels.append(('x265' if v265 else 'x264') +
                          ('+surround audio' if good_audio else ''))
        elif good_audio:
            av_score = 8
            labels.append('surround audio')

        # 5. Size relative to ideal for the quality tier.  Results within
        # 0.6x-4x of ideal are acceptable and bigger is better; outside that
        # band, closer to ideal is better (and always ranks below in-band).
        if ideal_size and result.size:
            ratio = result.size / float(ideal_size)
            if 0.6 < ratio < 4:
                size_key = (1, result.size)
                labels.append('%.1fx ideal size' % ratio)
            else:
                size_key = (0, -abs(1 - ratio))
                labels.append('%.1fx ideal size (out of range)' % ratio)
        else:
            size_key = (0, 0)

        # 6. Release modifiers.
        mod_score = 0
        for pattern, score in self.RESULT_MODS.items():
            if find(pattern):
                mod_score = score
                labels.append(pattern.replace('-?', '-').replace('?', ''))

        # 7. Post date (newer preferred).
        ts = result.date.timestamp() if result.date else 0

        key = (match, ext_score, res_score, av_score, size_key, mod_score, ts)
        return key, labels


    def _get_episode_codes_regexp_list(self, episodes, codes=True, dates=True):
        parts = []
        for ep in episodes or ():
            if codes:
                # season_offset compensates for releases posted with a
                # different season number than the metadata provider uses.
                season = ep.season.number + int(ep.series.cfg.season_offset or 0)
                parts.append('s%02de%02d' % (season, ep.number))
                parts.append('{0}x{1:02}'.format(season, ep.number))
            if dates:
                dt = ep.airdatetime
                if dt:
                    parts.append(r'{0}-{1:02}-{2:02}'.format(dt.year, dt.month, dt.day))
                    parts.append(r'{0}.{1:02}.{2:02}'.format(dt.year, dt.month, dt.day))

        return parts


    def _get_episode_codes_regexp(self, episodes, codes=True, dates=True):
        parts = self._get_episode_codes_regexp_list(episodes, codes, dates)
        if not parts:
            return ''
        elif len(parts) == 1:
            return parts[0]
        else:
            return '(%s)' % '|'.join(parts)


    def _is_name_for_episode(self, name, ep):
        recode = re.compile(r'(\b|_){0}(\b|_)'.format(self._get_episode_codes_regexp([ep])), re.I)
        if recode.search(name):
            # Epcode matches, check for title.
            title = ep.series.cfg.search_string or ep.series.name
            title = self.clean_title(title, apostrophe=self.CLEAN_APOSTROPHE_REGEXP)
            # Ensure each word in the title matches, but don't require them to be in
            # the right order.
            for word in title.split():
                if not re.search(r'(\b|_)%s(\b|_)' % word, name, re.I):
                    break
            else:
                return True
        return False


    def clean_title(self, title, apostrophe=CLEAN_APOSTROPHE_LEAVE, parens=True):
        """
        Strips punctutation and (optionally) parentheticals from a title to
        improve searching.

        :param title: the string to massage
        :param apostrophe: one of the CLEAN_APOSTROPHE_* constants (below)
        :param parens: if True, remove anything inside round parens. Otherwise,
                       the parens will be stripped but the contents left.

        *apostrophe* can be:
            * CLEAN_APOSTROPHE_LEAVE: don't do anything: foo's -> foo's
            * CLEAN_APOSTROPHE_REMOVE: strip them: foo's -> foos
            * CLEAN_APOSTROPHE_REGEXP: convert to regexp: foo's -> (foos|foo's)
        """
        if parens:
            # Remove anything in parens from the title (e.g. "The Office (US)")
            title = re.sub(r'\s*\([^)]*\)', '', title)
        # Strip diacritics so accented titles (e.g. "Fiancé") match posted filenames
        title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
        # Substitute certain punctuation with spaces
        title = re.sub(r'[&()\[\]*+,-./:;<=>?@\\^_{|}"]', ' ', title)
        # And outright remove others
        title = re.sub(r'[!"#$%:;<=>`]', '', title)
        # Treat apostrophe separately
        if apostrophe == self.CLEAN_APOSTROPHE_REMOVE:
            title = title.replace("'", '')
        elif apostrophe == self.CLEAN_APOSTROPHE_REGEXP:
            # Replace "foo's" with "(foos|foo's)"
            def replace_apostrophe(match):
                return '(%s|%s)' % (match.group(1).replace("'", ''), match.group(1))
            title = re.sub(r"(\S+'\S*)", replace_apostrophe, title)

        title = remove_stop_words(title)
        # Clean up multiple and trailing spaces.
        return re.sub(r'\s+', ' ', title).strip()


    async def _search(self, title, episodes, date, min_size, quality):
        """
        Must return a dict of episode -> [list of SearchResult objects].  A
        special key of None means the SearchResult list is not yet mapped
        to an episode object, and it will be up to the caller (i.e. the main
        search() method) to determine that.

        Subclasses must override this method.
        """
        raise NotImplementedError


    async def search(self, series, episodes, date=None, min_size=None, ideal_size=None, quality='HD'):
        results = await self._search(series, episodes, date, min_size, quality)
        # Categorize SearchResults not assigned to episodes.
        if None in results:
            for result in results[None]:
                for ep in episodes:
                    if self._is_name_for_episode(result.filename, ep):
                        results.setdefault(ep, []).append(result)
                        break
                else:
                    # We couldn't match the filename for this result against any
                    # episode.  Try matching against subject.  FIXME: we need to
                    # be careful because subject may include other codes (e.g.
                    # "Some Show s01e01-s01e23" in the case of an archive
                    # bundle)
                    if result.subject:
                        for ep in episodes:
                            if self._is_name_for_episode(result.subject, ep):
                                results.setdefault(ep, []).append(result)
                                break
            del results[None]

        # Disqualify results that exceed the selected quality tier.
        quality_str = str(quality).upper()
        if quality_str == 'HD':
            over_res = re.compile(r'[-. ]2160p[-. $]', re.I)
            over_reason = '2160p exceeds HD quality setting'
        elif quality_str == 'SD':
            over_res = re.compile(r'[-. ](2160p|1080p|720p)[-. $]', re.I)
            over_reason = 'resolution exceeds SD quality setting'
        else:
            over_res = None
        if over_res:
            for l in results.values():
                for result in l:
                    if over_res.search(result.filename):
                        result.disqualified = True
                        result.disqualify_reason = over_reason

        # Score, sort, remove disqualified results, and set common result
        # attributes.
        for ep, l in list(results.items()):
            scored = []
            for result in l:
                key, labels = self._score_result(ep, ideal_size, result)
                result.rank_info = ', '.join(labels)
                scored.append((key, result))
            scored.sort(key=lambda kr: kr[0], reverse=True)
            l[:] = [result for key, result in scored]
            for result in l[:]:
                if result.disqualified or result.size < min_size:
                    reason = result.disqualify_reason or \
                             'size %dMB below tier minimum %dMB' % (result.size / 1048576, min_size / 1048576)
                    log.info('disqualifying result %s: %s', result, reason)
                    l.remove(result)
                else:
                    result.searcher = self.NAME
                    # We str(quality) because it may be a config Var object which can't
                    # be pickled, and we do need to be able to pickle SearchResult objects.
                    result.quality = str(quality)
            if not l:
                # We ended up disqualifying all the results.  So remove this episode
                # from the result set.
                del results[ep]
            else:
                for n, result in enumerate(l, 1):
                    log.info('result: %s. %s [%s]', n, result, result.rank_info)


        return results


    async def _get_retriever_data(self, search_result):
        """
        Returns type-specific retriever data for the given search result.

        See :meth:`SearchResult.get_retriever_data`
        """
        raise NotImplementedError


    def _check_results_equal(self, a, b):
        raise NotImplementedError


class SearchResult:
    # Type of search result.  Only retrievers that support results of this
    # type will be used.
    type = None
    # This is the name of the plugin that provided the result.
    searcher = None
    filename = None
    subject = None
    # Size is in bytes
    size = None
    date = None
    newsgroup = None
    # The quality level expected for this result (retrievers may verify).
    quality = None
    disqualified = False
    # Why this result was disqualified (if it was).
    disqualify_reason = None
    # Human-readable summary of the ranking score (set during search()).
    rank_info = None

    def __init__(self, searcher, **kwargs):
        self.type = searcher.TYPE
        self.searcher = searcher.NAME
        [setattr(self, k, v) for k, v in kwargs.items()]

        # The cached entity from get_retriever_data().  This must not be
        # pickled, since it could reference data that is not accessible between
        # invocations.  Just use NotImplemented as a sentinel to indicate it
        # has not been populated.
        self._rdata = NotImplemented

    def __repr__(self):
        return '<%s %s at 0x%x>' % (self.__class__.__name__, self.filename, id(self))


    def __getstate__(self):
        # Return all attributes except _rdata which mustn't be pickled.
        d = self.__dict__.copy()
        del d['_rdata']
        return d


    def __setstate__(self, state):
        self.__dict__.update(state)
        self._rdata = NotImplemented


    def _get_searcher(self):
        """
        Return a new instance of the searcher plugin that provided this search
        result.

        It's possible that the plugin that provided the search result is no
        longer available (because, e.g. the SearchResult object was pickled and
        unpickled between invocations of Stagehand where the searcher plugin
        has since failed to load).

        It might be tempting to have searcher plugins subclass SearchResult and
        implement the result-specific logic there rather than taking this
        approach.  But because the SearchResults are pickled and stored in the
        database, and because plugins can fail (and so must be considered
        transient), unpickling would fail.  So we must only ever pickle core
        SearchResult objects.
        """
        # We commit this cardinal sin of importing inside a function in order
        # to prevent an import loop, since __init__ imports us for SearcherError.
        # It's safe from the usual pitfalls (i.e. importing inside a thread) since
        # the module is guaranteed to already be loaded.
        from . import plugins
        if self.searcher not in plugins:
            raise SearcherError('search result for unknown searcher plugin %s' % self.searcher)
        return plugins[self.searcher].Searcher()


    def __eq__(self, other):
        if not isinstance(other, SearchResult) or self.type != other.type:
            return False
        return self._get_searcher()._check_results_equal(self, other)


    async def get_retriever_data(self, force=False):
        """
        Fetch whatever data is needed for a retriever to fetch this result.

        The actual return value is dependent on the searcher type, and no
        format is assumed or enforced here.  It is a contract between the
        searcher plugin and a retriever plugin.

        :param force: if False (default), the data is cached so that subsequent
                      invocations don't call out to the plugin.  If True,
                      it wil ask the plugin regardless of whether the value
                      was cached.
        :returns: a type-specific object from the searcher plugin, guaranteed
                  to be non-zero
        """
        if self._rdata is NotImplemented or force:
            # Fetch the data and cache it for subsequent calls.  We cache because
            # retrievers may call get_retriever_data() multiple times (for
            # multiple retriever plugins) but the actual operation could be
            # expensive (e.g. fetching a torrent or nzb file off the network).
            self._rdata = await self._get_searcher()._get_retriever_data(self)

        if not self._rdata:
            # This shouldn't happen.  It's a bug in the searcher, which should
            # have raised SearcherError instead.
            raise SearcherError('searcher plugin did not provide retriever data for this result')

        return self._rdata


def get_searcher_bind_address():
    if config.searchers.bind_address:
        if config.searchers.bind_address != '*':
            return config.searchers.bind_address
    elif config.misc.bind_address:
        return config.misc.bind_address

