Stagehand bundles this third party module for ease of installation:

* [kaa.metadata](https://github.com/freevo/kaa-metadata), released under the GPL,
  *partially* ported to Python 3.  Used for optional verification of downloaded
  video files (resolution, codecs, audio language).  There is no pip-installable
  Python 3 release, hence the bundled copy.

Historical note: asyncio (Tulip), aiohttp, and BeautifulSoup were once bundled
here as well.  asyncio has been part of the Python standard library since 3.4,
and aiohttp and beautifulsoup4 are now regular pip dependencies (see
install_requires in setup.py and the Dockerfile).
