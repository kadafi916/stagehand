# auto generated file

from stagehand.toolbox.config import Var, Group, Dict, List, Config

config = Config(schema=[

  Group(name='misc', schema=[

    Var(name='tvdir', desc='Location of your TV series collection', defaults={'win32': '~\\TV Shows', '': '~/tv'}),

    Var(name='language', desc='''
    Preferred language (two letter ISO code).  When there is no
    choice (either because Stagehand doesn\'t support it or because
    the preferred language isn\'t found), English will be used.
    
    Currently the only place this is used is with TheTVDB metadata,
    but it will be used for other things in the future.
    ''', default='en'),

    Group(name='proxy', schema=[

      Var(name='use', default=False),

      Var(name='host', default=''),

      Var(name='port', default=''),

      Var(name='username', default=''),

      Var(name='password', default='', scramblekey='stagehand'),

      ]
    ),

    Var(name='bind_address', desc='''
    Source address for all outbound Internet communication.  If
    unspecified, the OS default will be used.
    
    Not used if a proxy is enabled.
    ''', default=''),

    Var(name='logdir', desc='Directory for logs; leave empty to disable logging to file', defaults={'win32': '%AppData%\\Stagehand\\Logs', '': '~/.cache/stagehand/logs'}),

    Var(name='loglevel', desc='''
    Level of logging detail.
    
    Warnings and errors are always logged. Debug is useful to help
    troubleshoot problems, and debug2 is <i>very</i> verbose.
    ''', default='info', type=('warn', 'info', 'debug', 'debug2')),

    ]
  ),

  Group(name='web', schema=[

    Var(name='bind_address', default=''),

    Var(name='port', default=8088),

    Var(name='username', default=''),

    Var(name='password', default='', scramblekey='stagehand'),

    Var(name='logging', default=False),

    Var(name='proxied_root', desc='''
    When the web server is in front of a reverse proxy (which is detected by
    the presence of the X-Forwarded-Host header, this specifies the root path
    for all URLs.  This allows you to put a reverse proxy in front of
    Stagehand (like Apache mod_proxy) and anchor it under a different path
    (e.g. /stagehand) without resorting to HTML rewriting mods.
    ''', default=''),

    ]
  ),

  Group(name='naming', schema=[

    Var(name='rename', default=True),

    Var(name='separator', defaults={'win32': ' ', '': '_'}),

    Var(name='season_dir_format', default='s{season}'),

    Var(name='code_style', default='s{season:02}e{episode:02}'),

    Var(name='date_style', default='%Y.%m.%d'),

    Var(name='episode_format', default='{show}-{code}-{title}'),

    ]
  ),

  Group(name='scoring', schema=[

    Dict(name='modifiers', desc='Keywords that modify the search result scoring.', schema=Var(desc='Value added to the score if the modifier is found.', default=0)),

    ]
  ),

  List(name='series', desc='The current TV series subscriptions.', schema=[

    Var(name='id', desc='''
    The id for this series, in the form "provider:id".  For example,
    thetvdb:75897 or tvrage:7926.
    ''', default=''),

    Var(name='provider', desc='''
    The preferred metadata provider for this series.  This provider will
    be used for episode codes and air dates, and will take precedence
    for episode summaries.
    ''', default='thetvdb'),

    Var(name='warn_conflicts', desc='''
    Notify when metadata providers disagree about series data.  You
    can set this to False when you\'re certain the preferred provider
    is correct for this series and you\'re not interested in conflicts.
    ''', default=True),

    Var(name='path', desc='''
    Name of the directory holding episodes for this series.
    Non-absolute paths will be relative to the global tv directory.
    
    If unspecified, will be auto-generated.
    ''', default=''),

    Var(name='flat', desc='''
    True if all episodes should be stored in the root of the
    series directory, or False if episods should be stored within
    separate season subdirectories.
    ''', default=False),

    Var(name='quality', desc='''
    The required resolution for downloaded episodes.
    
    UHD is 2160p, HD is 1080p or 720p, SD is anything less than HD, and Any
    will download whatever is available.  In all cases, if there are multiple
    options within the preferred resolution, Stagehand will try to choose the
    one with the best quality.
    ''', default='HD', type=('UHD', 'HD', 'SD', 'Any')),

    Var(name='upgrade', desc='''
    If True, periodically monitor existing episodes for better
    quality versions, and replace poorer quality versions when
    available.
    ''', default=False),

    Var(name='paused', desc='If True, new episodes will not be searched for or downloaded.', default=False),

    Var(name='identifier', desc='''
    The style of identier used in episode naming and searching.
    
    Episode code (e.g. s02e05) is almost always the identifier
    used in episode names, but some TV series, particularly
    news programs and talk shows, will use dates as identifiers.
    ''', default='epcode', type=('epcode', 'date')),

    Var(name='search_string', desc='''
    A custom search string for this series.
    
    Normally the search string is derived from the show name, but
    it can be overridden if episodes are regularly posted under a
    different or abbreviated name.
    
    For example, "The Daily Show with Jon Stewart" is often posted
    as just "The Daily Show".
    
    If unspecified, the series title will be used as the search
    string.
    ''', default=''),

    Var(name='language', desc='Preferred audio language for this series (overrides global default).', default=''),

    Var(name='season_offset', desc='''
    Offset applied to the metadata provider\'s season number when
    searching for episodes.

    Useful when releases are posted with a different season number
    than the provider uses.  For example, if the provider calls it
    season 2 but releases are posted as s03, set this to 1.
    ''', default=0),

    ]
  ),

  Group(name='searchers', desc='Methods of searching for TV series', schema=[

    Var(name='hours', desc='''
    Comma-separated list of hours when needed episodes are
    searched.  (Minutes are randomized and can\'t be configured.)
    ''', default='4, 11, 16, 21'),

    Var(name='bind_address', desc='''
    Source address for outbound Internet communication used specifically for
    searching, not for downloading.
    
    If specified, overrides the global bind address.  A special
    value of \'*\' will override the global bind address by disabling
    it, causing communication to use the OS default route.
    ''', default=''),

    List(name='enabled', desc='List of enabled searcher plugins and their order of preference.', schema=Var(default=''), defaults=['easynews']),

    ]
  ),

  Group(name='retrievers', schema=[

    Var(name='parallel', desc='Maximum number of episodes to download simultaneously.', default=1),

    List(name='enabled', desc='List of enabled retriever plugins and their order of preference.', schema=Var(default='')),

    ]
  ),

  Group(name='notifiers', schema=[

    List(name='enabled', desc='List of enabled notifier plugins and their order of preference.', schema=Var(default='')),

    ]
  ),

  ]
, module='stagehand.config')

# Force plugins to load and attach their config objects.
from . import searchers
from . import retrievers
from . import notifiers

