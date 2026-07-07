import os
import logging

from . import server as web
from . import api
from .utils import SessionPlugin, CachePlugin, shview, static_file_from_zip, abspath_to_zippath
from ..coffee import cscompile_with_cache

log = logging.getLogger('stagehand.web.app')

web.install(SessionPlugin())
web.install(CachePlugin())


@web.get('/static/:filename#.*#')
def static(filename):
    manager = web.request['stagehand.manager']
    root = os.path.join(manager.paths.data, 'web')
    ziproot = abspath_to_zippath(root)
    response = None

    if ziproot:
        try:
            target = filename + '.compiled' if filename.endswith('.coffee') else filename
            response = static_file_from_zip(ziproot, target)
        except AttributeError:
            pass

    if not response:
        # Load static file from filesystem.
        if filename.endswith('.coffee'):
            # This is CoffeeScript, so we need to return the compiled JavaScript
            # instead.  Ok, not exactly static, strictly speaking. Close enough.
            src = os.path.abspath(os.path.join(root, filename))
            if not src.startswith(root):
                raise web.HTTPError(403, 'Access denied.')
            elif not os.path.exists(src):
                # Before we give up, is there a pre-compiled version?  If not,
                # static_file() will return a 404.
                response = web.static_file(filename + '.compiled', root=root)
            else:
                cached, data = cscompile_with_cache(src, web.request['coffee.cachedir'])
                web.response.logextra = '(CS %s)' % 'cached' if cached else 'compiled on demand'
                web.response.content_type = 'application/javascript'
                web.response['Cache-Control'] = 'max-age=3600'
                return data
        else:
            response = web.static_file(filename, root=root)

    if filename.endswith('.gz') and not isinstance(response, web.HTTPError):
        # static_file() does the right thing with respect to Content-Type
        # and Content-Encoding for gz files.  But if the client doesn't have
        # gzip in Accept-Encoding, we need to decompress it on the fly.
        if 'gzip' not in web.request.headers.get('Accept-Encoding', ''):
            import gzip
            response.body = gzip.GzipFile(fileobj=response.body)
    #elif filename.endswith('.coffee'):
    #    response['X-SourceMap'] = '/static/' + filename + '.map'
    return response


@web.get('/')
@shview('new/ui.tmpl')
def home():
    return {}
