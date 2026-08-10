# auto generated file

from stagehand.toolbox.config import Var, Group, Dict, List, Config

config = Config(desc='The Movie Database (TMDB) metadata provider', schema=[

  Var(name='apikey', desc='''
  Your TMDB API key (v3 auth). Free to request at
  https://www.themoviedb.org/settings/api -- Stagehand can't ship a
  shared key like it does for TheTVDB, since TMDB requires each
  application to register its own.
  ''', default=''),

  ]
, module='stagehand.providers.config')
