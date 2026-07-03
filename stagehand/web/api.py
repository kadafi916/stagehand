import os
import time
import mimetypes
import time
import logging
import asyncio
from datetime import datetime, timedelta

from . import server as web
from .asyncweb import asyncweb, webcoroutine
from ..utils import episode_status_icon_info
from ..tvdb import Episode, Series
from ..toolbox.config import get_type

log = logging.getLogger('stagehand.web.app')

def get_series_from_request(id):
    series = web.request['stagehand.manager'].tvdb.get_series_by_id(id)
    if not series:
        raise web.HTTPError(404, 'Invalid show.')
    return series


@web.put('/api/shows/<id>')
@webcoroutine()
async def show_add(job, id):
    manager = web.request['stagehand.manager']
    job.notify('alert', title='Adding series', text='Retrieving episode information for this series ...')
    try:
        series = await manager.add_series(id)
    except Exception as e:
        log.exception('failed to add series')
        job.notify_after('alert', title='Failed to add series', text=str(e), timeout=2)
    else:
        job.notify_after('alert', title='Series added', text='Added series %s to database.' % series.name, timeout=2)
    return {}


@web.delete('/api/shows/<id>')
@webcoroutine()
async def show_delete(job, id):
    manager = web.request['stagehand.manager']
    name = get_series_from_request(id).name
    manager.delete_series(id)
    # Notify the session about the removal, but do it via a timer so that
    # the notification happens on the next page load rather than in response
    # to the API call.
    job.notify_after('alert', title='Series Deleted', text='Series <b>%s</b> was removed from the database' % name)
    return {}


@web.get('/api/shows/<id>/banner', cache=3600*24*7)
def show_banner(id):
    # TODO: support cache check
    series = get_series_from_request(id)
    if not series.banner_data:
        raise web.HTTPError(404, 'Invalid show, or no banner for this show.')

    web.response['Content-Length'] = len(series.banner_data)
    mimetype, encoding = mimetypes.guess_type(series.banner)
    if mimetype:
        web.response.content_type = mimetype
    return series.banner_data


@web.post('/api/shows/<id>/provider')
@webcoroutine()
async def show_provider(job, id):
    series = get_series_from_request(id)
    provider = web.request.forms.get('provider')
    if provider:
        try:
            await series.change_provider(provider)
        except Exception as e:
            job.notify_after('alert', title='Series Provider', text='Failed to change provider: %s' % e.args[0])
            raise web.HTTPError(404, 'Invalid provider.')
        else:
            series.cfg.provider = provider
            from ..config import config
            manager = web.request['stagehand.manager']
            config.save(manager.paths.config)


@web.post('/api/shows/<id>/refresh')
@webcoroutine()
async def show_refresh(job, id):
    series = get_series_from_request(id)
    await series.refresh()


@web.post('/api/shows/<id>/settings')
def show_settings(id):
    series = get_series_from_request(id)
    settings = web.request.forms
    series.cfg.quality = settings.quality
    series.cfg.search_string = settings.search_string
    series.cfg.language = settings.language
    series.cfg.paused = True if settings['paused'] == 'true' else False
    series.cfg.flat = True if settings['flat'] == 'true' else False
    series.cfg.identifier = settings.identifier
    if settings.get('no_subdir') == 'true':
        series.cfg.path = '.'
    else:
        series.cfg.path = settings.path

    from ..config import config
    manager = web.request['stagehand.manager']
    config.save(manager.paths.config)

    # TODO: if pausing a series that has queued episodes, remove them and
    # notify user.


@web.get('/api/shows/<id>/overview')
def show_overview(id):
    series = get_series_from_request(id)
    return {'overview': series.overview}


@web.get('/api/shows/<id>/<code>/overview')
def show_episode_overview(id, code):
    series = get_series_from_request(id)
    ep = series.get_episode_by_code(code)
    return {'overview': ep.overview if ep else 'Episode not found'}


@web.get('/api/shows/search')
@webcoroutine(interval=500)
async def show_search(job):
    q = web.request.query
    manager = web.request['stagehand.manager']

    t0 = time.time()
    results = await manager.tvdb.search(q.name)
    job.notify('alert', title='Search results', text='Search took %.3fs' % (time.time() - t0))
    # JSONify the SearchResult objects
    dictlist = []
    for r in results:
        dictlist.append({
            'id': r.id,
            'name': r.name,
            'overview': r.overview,
            'year': r.year,
            'imdb': r.imdb,
            'provider': r.provider.NAME,
            'started': r.started
        })
    return {'results': dictlist}


@web.get('/api/shows/check')
@webcoroutine(interval=500)
async def show_check(job):
    manager = web.request['stagehand.manager']
    if web.request.query.id:
        only = [get_series_from_request(web.request.query.id)]
    else:
        only = []

    need, found = await manager.check_new_episodes(only=only)
    return {'need': sum(len(eps) for eps in need.values()), 'found': len(found)}


@web.post('/api/shows/<id>/episodes/<epcode>/status')
@webcoroutine()
async def show_episodes_status(job, id, epcode):
    manager = web.request['stagehand.manager']
    series = get_series_from_request(id)
    eps = [series.get_episode_by_code(code) for code in epcode.split(',')]
    if None in eps:
        raise web.HTTPError(404, 'Unknown episode for this show.')

    action = web.request.query.value
    status_map = {
        'need': Episode.STATUS_NEED_FORCED,
        'ignore': Episode.STATUS_IGNORE,
        'delete': Episode.STATUS_IGNORE
    }
    try:
        status_val = status_map[action]
    except KeyError:
        raise web.HTTPError(404, 'Invalid status code.')

    statuses = {}
    do_check_new_episodes = False
    for ep in eps:
        if ep.status == Episode.STATUS_HAVE and action != 'delete':
            # Asked to ignore or retrieve an episode we already have.  Do nothing.
            pass
        else:
            ep.status = status_val
            # Clear any stored search result
            ep.search_result = None

        if ep.status == Episode.STATUS_IGNORE:
            manager.cancel_episode_retrieval(ep)
        elif ep.status == Episode.STATUS_NEED_FORCED:
            # User explicitly requested this episode — search immediately.
            do_check_new_episodes = True
        if action == 'delete' and ep.filename and os.path.isfile(ep.path):
            try:
                os.unlink(ep.path)
            except OSError as e:
                job.notify('alert', title='Delete Episode', text='Failed to delete %s: %s' % (ep.path, e), type='error')
            else:
                job.notify('alert', title='Delete Episode', text='%s deleted' % ep.filename)
                ep.filename = None

        statuses[ep.code] = episode_status_icon_info(ep)

    if do_check_new_episodes:
        asyncio.ensure_future(manager.check_new_episodes())
    return {'statuses': statuses}


@web.get('/api/settings/general')
def get_general_settings():
    from ..config import config
    enabled = [str(s) for s in config.searchers.enabled]
    return {
        'tvdir':              str(config.misc.tvdir),
        'language':           str(config.misc.language),
        'loglevel':           str(config.misc.loglevel),
        'parallel':           int(config.retrievers.parallel),
        'rename':             bool(config.naming.rename),
        'separator':          str(config.naming.separator),
        'season_dir_format':  str(config.naming.season_dir_format),
        'code_style':         str(config.naming.code_style),
        'episode_format':     str(config.naming.episode_format),
        'web_username':       str(config.web.username),
        'web_password':       str(config.web.password),
        'easynews_username':  str(config.searchers.easynews.username),
        'easynews_password':  str(config.searchers.easynews.password),
        'easynews_enabled':   'easynews' in enabled,
    }

@web.post('/api/settings/general')
def set_general_settings():
    import logging as _logging
    from ..config import config
    from .settings import rename_example
    d = web.request.json or {}

    def _set(attr, val, cast=str):
        if val is not None:
            parts = attr.split('.')
            obj = config
            for p in parts[:-1]:
                obj = getattr(obj, p)
            setattr(obj, parts[-1], cast(val))

    _set('misc.tvdir',              d.get('tvdir'))
    _set('misc.language',           d.get('language'))
    _set('misc.loglevel',           d.get('loglevel'))
    _set('retrievers.parallel',     d.get('parallel'), int)
    _set('naming.rename',            d.get('rename'), lambda v: v if isinstance(v, bool) else str(v).lower() not in ('false', '0', 'no'))
    _set('naming.separator',        d.get('separator'))
    _set('naming.season_dir_format',d.get('season_dir_format'))
    _set('naming.code_style',       d.get('code_style'))
    _set('naming.episode_format',   d.get('episode_format'))
    _set('web.username',            d.get('web_username'))
    _set('web.password',            d.get('web_password'))

    # Easynews credentials
    en_user = d.get('easynews_username')
    en_pass = d.get('easynews_password')
    if en_user is not None or en_pass is not None:
        if en_user is not None:
            config.searchers.easynews.username = str(en_user)
        if en_pass is not None:
            config.searchers.easynews.password = str(en_pass)
        # Auto-enable easynews searcher if credentials provided
        if en_user or en_pass:
            enabled = [str(s) for s in config.searchers.enabled]
            if 'easynews' not in enabled:
                config.searchers.enabled.append('easynews')

    # Apply loglevel immediately without restart
    if d.get('loglevel'):
        lvl = str(d['loglevel']).lower()
        level_map = {'warn': _logging.WARNING, 'info': _logging.INFO,
                     'debug': _logging.DEBUG, 'debug2': 5}
        new_level = level_map.get(lvl, _logging.INFO)
        _logging.getLogger('stagehand').setLevel(new_level)

    config.save()

    example = rename_example(
        str(config.misc.tvdir), str(config.naming.separator),
        str(config.naming.season_dir_format), str(config.naming.code_style),
        str(config.naming.episode_format)
    )
    return {'ok': True, 'example': example}

@web.get('/api/settings/check-hours')
def get_check_hours():
    from ..config import config
    hours = sorted(int(h.strip()) for h in str(config.searchers.hours).split(',') if h.strip().isdigit())
    return {'hours': hours}

@web.post('/api/settings/check-hours')
def set_check_hours():
    from ..config import config
    from ..toolbox.config import get_default
    manager = web.request['stagehand.manager']
    hours = web.request.json.get('hours', [])
    hours = sorted(set(int(h) for h in hours if 0 <= int(h) <= 23))
    if not hours:
        default = get_default(config.searchers.hours)
        hours = sorted(int(h.strip()) for h in default.split(',') if h.strip().isdigit())
    config.searchers.hours = ', '.join(str(h) for h in hours)
    config.save()
    manager._schedule_next_episode_check()
    return {'hours': hours}

@web.get('/api/restart')
def restart():
    web.restart()


@web.get('/api/shutdown')
def shutdown():
    asyncio.get_event_loop().stop()

@web.get('/api/pid')
def pid():
    return {'pid': os.getpid()}


@web.get('/api/log')
def log_entries():
    from ..logger import memory_handler
    since = web.request.query.since
    since = int(since) if since.isdigit() else 0
    web.response.loglevel = logging.DEBUG
    return {'records': memory_handler.get_records(since), 'seq': memory_handler.seq}


@web.get('/api/shows')
def shows_list():
    manager = web.request['stagehand.manager']
    shows = []
    for series in sorted(manager.tvdb.series, key=lambda s: s.name.lower()):
        needed = sum(1 for ep in series.episodes if ep.ready)
        if series.cfg.paused:
            run_status = 'paused'
        elif series.status == Series.STATUS_RUNNING:
            run_status = 'running'
        elif series.status == Series.STATUS_ENDED:
            run_status = 'ended'
        elif series.status == Series.STATUS_SUSPENDED:
            run_status = 'suspended'
        else:
            run_status = 'unknown'
        shows.append({
            'id': series.id,
            'name': series.name,
            'status': run_status,
            'paused': series.cfg.paused,
            'needed': needed,
        })
    return {'shows': shows}


@web.get('/api/shows/<id>/detail')
def show_detail(id):
    manager = web.request['stagehand.manager']
    series = get_series_from_request(id)
    seasons = []
    for season in sorted(series.seasons, key=lambda s: -s.number):
        eps = []
        for ep in season.episodes:
            icon, title = episode_status_icon_info(ep)
            eps.append({
                'code': ep.code,
                'number': ep.number,
                'name': ep.name or '',
                'airdate': ep.airdate.strftime('%Y-%m-%d') if ep.airdate else None,
                'status': icon,
                'status_title': title,
            })
        seasons.append({'number': season.number, 'episodes': eps})

    if series.cfg.paused:
        run_status = 'paused'
    elif series.status == Series.STATUS_RUNNING:
        run_status = 'running'
    elif series.status == Series.STATUS_ENDED:
        run_status = 'ended'
    elif series.status == Series.STATUS_SUSPENDED:
        run_status = 'suspended'
    else:
        run_status = 'unknown'

    providers = [
        {'name': p.NAME, 'label': p.NAME_PRINTABLE}
        for p in sorted(manager.tvdb.providers.values(), key=lambda p: p.NAME)
    ]
    return {
        'id': series.id,
        'name': series.name,
        'run_status': run_status,
        'paused': series.cfg.paused,
        'overview': series.overview or '',
        'quality': series.cfg.quality,
        'flat': series.cfg.flat,
        'no_subdir': str(series.cfg.path) == '.',
        'identifier': series.cfg.identifier,
        'path': series.cfg.path or '' if str(series.cfg.path) != '.' else '',
        'search_string': series.cfg.search_string or '',
        'language': series.cfg.language or '',
        'provider': series.cfg.provider or '',
        'providers': providers,
        'quality_options': list(get_type(series.cfg.quality)),
        'identifier_options': list(get_type(series.cfg.identifier)),
        'seasons': seasons,
    }


@web.get('/api/downloads')
def downloads_list():
    manager = web.request['stagehand.manager']
    weeks_param = web.request.query.weeks
    status_param = web.request.query.status or 'have'
    weeks = int(weeks_param) if weeks_param.isdigit() else 1

    queue = []
    for ep, results in manager.retrieve_queue:
        task = manager.get_episode_retrieve_task(ep)
        if task and hasattr(task, 'progress') and task.progress:
            progress = {
                'percentage': task.progress.percentage,
                'current_mb': round(task.progress.pos / 1024 / 1024, 1),
                'total_mb': round(task.progress.max / 1024 / 1024, 1),
                'speed_kb': int(task.progress.speed / 1024),
            }
        else:
            progress = None
        queue.append({
            'show_id': ep.series.id,
            'show_name': ep.series.name,
            'code': ep.code,
            'season': ep.season.number,
            'number': ep.number,
            'name': ep.name or '',
            'airdate': ep.airdate.strftime('%Y-%m-%d') if ep.airdate else None,
            'progress': progress,
        })

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = today if today.weekday() == 6 else today - timedelta(days=today.weekday() + 1)
    episodes = []
    for s in manager.tvdb.series:
        for ep in s.episodes:
            if ep.status != ep.STATUS_NEED_FORCED and (not ep.aired or manager.is_episode_queued_for_retrieval(ep)):
                continue
            if s.cfg.paused:
                continue
            icon, title = episode_status_icon_info(ep)
            if ep.airdate:
                week = (max(0, (sunday - ep.airdate).days) + 6) // 7
                if (icon in ('ignore', 'have') and week >= weeks) or (icon == 'ignore' and status_param == 'have'):
                    continue
            else:
                week = None
            episodes.append({
                'show_id': s.id,
                'show_name': s.name,
                'code': ep.code,
                'season': ep.season.number,
                'number': ep.number,
                'name': ep.name or '',
                'airdate': ep.airdate.strftime('%Y-%m-%d') if ep.airdate else None,
                'status': icon,
                'status_title': title,
                'week': week,
            })

    episodes.sort(key=lambda i: (i.get('airdate') or '1900-01-01', i['name']), reverse=True)
    return {'queue': queue, 'episodes': episodes, 'weeks': weeks, 'status': status_param}