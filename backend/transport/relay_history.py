from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from backend.core.config import ChatConfig
from backend.core.message import ChatMessage


class RelayHistoryClient:
    available = True

    def __init__(
        self,
        config: ChatConfig,
        on_status: Callable[[str], None],
    ) -> None:
        self.config = config
        self.on_status = on_status

    async def fetch_incoming_after(
        self, after: datetime | None = None
    ) -> list[ChatMessage]:
        query_params = {'user_id': self.config.username}
        if after is not None:
            query_params['after'] = after.isoformat()
        return await self._fetch_messages('messages/sync', query_params)

    async def fetch_conversation(
        self,
        peer_id: str,
        after: datetime | None = None,
    ) -> list[ChatMessage]:
        query_params = {
            'user_id': self.config.username,
            'peer_id': peer_id,
        }
        if after is not None:
            query_params['after'] = after.isoformat()
        return await self._fetch_messages(
            'messages/conversation',
            query_params,
        )

    async def _fetch_messages(
        self,
        route_path: str,
        query_params: dict[str, str],
    ) -> list[ChatMessage]:
        return await asyncio.to_thread(
            self._fetch_messages_sync,
            route_path,
            query_params,
        )

    def _fetch_messages_sync(
        self,
        route_path: str,
        query_params: dict[str, str],
    ) -> list[ChatMessage]:
        api_base_url = self._api_base_url()
        request_url = f'{api_base_url}/{route_path}?{urlencode(query_params)}'
        request = Request(
            request_url,
            headers={
                'Accept': 'application/json',
                'User-Agent': 'ogham-chat/0.1',
            },
        )

        try:
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except HTTPError as exc:
            # Some edge providers occasionally return transient 403s.
            # Retry once with a small backoff before surfacing status.
            if exc.code == 403:
                try:
                    with urlopen(request, timeout=10) as response:
                        payload = json.load(response)
                except HTTPError, URLError, TimeoutError:
                    return []
            else:
                self.on_status(f'History sync unavailable: {exc}')
                return []
        except (URLError, TimeoutError) as exc:
            self.on_status(f'History sync unavailable: {exc}')
            return []

        if not isinstance(payload, list):
            return []

        messages: list[ChatMessage] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            messages.append(ChatMessage.model_validate(item))
        return messages

    def _api_base_url(self) -> str:
        relay_url = self.config.relay_url or ''
        parts = urlsplit(relay_url)

        if parts.scheme == 'wss':
            scheme = 'https'
        elif parts.scheme == 'ws':
            scheme = 'http'
        else:
            scheme = parts.scheme

        path = parts.path.rstrip('/')
        if '/ws/' in path:
            path = path.rsplit('/ws/', 1)[0]
        elif path.endswith('/ws'):
            path = path[:-3]

        return urlunsplit((scheme, parts.netloc, path or '/', '', '')).rstrip(
            '/'
        )
