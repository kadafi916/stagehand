import asyncio

from .base import NotifierBase, NotifierError
from .. import web

__all__ = ['Notifier']

class Notifier(NotifierBase):
    async def _notify(self, episodes):
        # Per-episode completion toasts are issued by the manager as each
        # download finishes; this batch notifier just summarizes.
        if len(episodes) > 1:
            web.notify('alert', title='Downloads Complete',
                       text='Downloaded %d episodes.' % len(episodes))