# auto generated file

from stagehand.toolbox.config import Var, Group, Dict, List, Config

config = Config(desc='Home Assistant notifier', schema=[

  Var(name='url', desc='''
  Home Assistant webhook URL, e.g.
  http://homeassistant.local:8123/api/webhook/stagehand
  ''', default=''),

  ]
, module='stagehand.notifiers.config')
