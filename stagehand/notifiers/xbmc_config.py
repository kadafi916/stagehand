# auto generated file

from stagehand.toolbox.config import Var, Group, Dict, List, Config

config = Config(desc='Kodi notifier', schema=[

  Var(name='hostname', default='localhost'),

  Var(name='http_port', desc='''
  Port of Kodi\'s web server (Settings -> Services -> Control ->
  "Allow remote control via HTTP").
  ''', default=8080),

  Var(name='username', desc='Username for Kodi\'s web server, if required.', default=''),

  Var(name='password', desc='Password for Kodi\'s web server, if required.', default='', scramblekey='stagehand'),

  Var(name='notify', default=True),

  Var(name='individual', desc='''
  If True, update the media library for individual series
  directories.  If False, do a full library update.
  ''', default=True),

  Var(name='tvdir', desc='''
  The Kodi host\'s local path to the TV directory.  If defined,
  Stagehand will remap the path to the series directory when poking
  Kodi to update.  If not defined, no translation is done.

  This is useful if Stagehand\'s view of the filesystem is different
  than Kodi\'s.  Only relevant if individual is True.
  ''', default=''),

  ]
, module='stagehand.notifiers.config')
