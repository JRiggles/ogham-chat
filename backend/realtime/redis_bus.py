from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Iterable
from typing import cast
from uuid import uuid4

from redis.asyncio import from_url
from redis.asyncio.client import Redis
from redis.exceptions import RedisError

from backend.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)


class RedisRealtimeCoordinator:
    """Coordinate cross-instance realtime events through Redis pub/sub."""

    EVENT_CHANNEL = 'ogham:realtime:events'
    ONLINE_USERS_KEY = 'ogham:presence:users'
    USER_INSTANCE_COUNTS_KEY = 'ogham:presence:user_instance_counts'

    def __init__(self, redis_url: str | None) -> None:
        self.redis_url = redis_url
        self.instance_id = uuid4().hex
        self._redis: Redis | None = None
        self._ws_manager: ConnectionManager | None = None
        self._subscriber_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def enabled(self) -> bool:
        """Return whether Redis-backed coordination is currently active."""
        return self._redis is not None

    async def start(self, ws_manager: ConnectionManager) -> None:
        """Initialize Redis connectivity and start the subscriber loop."""
        self._ws_manager = ws_manager
        self._stop_event.clear()

        if not self.redis_url:
            logger.info(
                'REDIS_URL not set; realtime relay stays single-instance.'
            )
            return

        try:
            redis_client = from_url(self.redis_url, decode_responses=True)
            await cast(Awaitable[bool], redis_client.ping())
        except RedisError as exc:
            logger.warning(
                'Redis unavailable; degrading to local-only relay: %s', exc
            )
            return

        self._redis = redis_client
        self._subscriber_task = asyncio.create_task(self._subscriber_loop())

    async def stop(self) -> None:
        """Stop background subscriber work and close the Redis client."""
        self._stop_event.set()

        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._subscriber_task
            self._subscriber_task = None

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def register_local_presence(
        self,
        user_id: str,
        *,
        is_first_local_connection: bool,
    ) -> None:
        """Register one user's presence when their first local socket connects."""
        if not is_first_local_connection or self._redis is None:
            return

        try:
            pipeline = self._redis.pipeline()
            pipeline.hincrby(self.USER_INSTANCE_COUNTS_KEY, user_id, 1)
            pipeline.sadd(self.ONLINE_USERS_KEY, user_id)
            await pipeline.execute()
            await self._publish_presence_changed(user_id)
        except RedisError as exc:
            logger.warning(
                'Failed to register Redis presence for %s: %s', user_id, exc
            )

    async def unregister_local_presence(
        self,
        user_id: str,
        *,
        lost_last_local_connection: bool,
    ) -> None:
        """Remove one user's presence when their last local socket disconnects."""
        if not lost_last_local_connection or self._redis is None:
            return

        try:
            remaining_instances = await cast(
                Awaitable[int],
                self._redis.hincrby(
                    self.USER_INSTANCE_COUNTS_KEY,
                    user_id,
                    -1,
                ),
            )
            if remaining_instances <= 0:
                pipeline = self._redis.pipeline()
                pipeline.hdel(self.USER_INSTANCE_COUNTS_KEY, user_id)
                pipeline.srem(self.ONLINE_USERS_KEY, user_id)
                await pipeline.execute()
            await self._publish_presence_changed(user_id)
        except RedisError as exc:
            logger.warning(
                'Failed to unregister Redis presence for %s: %s', user_id, exc
            )

    async def publish_direct_message(
        self,
        recipient: str,
        payload: dict,
    ) -> None:
        """Publish one direct-message packet for remote instances to deliver."""
        await self._publish_event(
            {
                'event': 'direct_message',
                'target_user': recipient,
                'payload': payload,
            }
        )

    async def publish_typing(
        self,
        recipient: str,
        payload: dict,
    ) -> None:
        """Publish one typing packet for remote instances to deliver."""
        await self._publish_event(
            {
                'event': 'typing',
                'target_user': recipient,
                'payload': payload,
            }
        )

    async def broadcast_presence_snapshot(self) -> None:
        """Send the merged online-user snapshot to all local sockets."""
        if self._ws_manager is None:
            return

        online_users = await self.get_online_users(
            fallback=self._ws_manager.connected_user_ids
        )
        await self._ws_manager.broadcast(
            {
                'type': 'user_list',
                'data': {'users': online_users},
            }
        )

    async def get_online_users(
        self,
        *,
        fallback: Iterable[str],
    ) -> list[str]:
        """Return the globally online users, or local users if Redis is down."""
        if self._redis is None:
            return sorted(set(fallback))

        try:
            users = await cast(
                Awaitable[set[str]],
                self._redis.smembers(self.ONLINE_USERS_KEY),
            )
        except RedisError as exc:
            logger.warning('Failed to fetch Redis presence snapshot: %s', exc)
            return sorted(set(fallback))

        return sorted(
            {user for user in users if isinstance(user, str) and user}
        )

    async def _publish_presence_changed(self, user_id: str) -> None:
        """Publish one presence-change notification to peer instances."""
        await self._publish_event(
            {
                'event': 'presence_changed',
                'user_id': user_id,
            }
        )

    async def _publish_event(self, event: dict) -> None:
        """Publish one realtime event when Redis is available."""
        if self._redis is None:
            return

        message = {
            **event,
            'source_instance': self.instance_id,
        }

        try:
            await self._redis.publish(self.EVENT_CHANNEL, json.dumps(message))
        except RedisError as exc:
            logger.warning(
                'Failed to publish realtime event %s: %s',
                event.get('event'),
                exc,
            )

    async def _subscriber_loop(self) -> None:
        """Listen for Redis events and dispatch them to local sockets."""
        while not self._stop_event.is_set():
            if self._redis is None:
                return

            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(self.EVENT_CHANNEL)
                while not self._stop_event.is_set():
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if not message:
                        continue

                    raw_data = message.get('data')
                    if not isinstance(raw_data, str):
                        continue

                    try:
                        event = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue

                    await self._handle_event(event)
            except asyncio.CancelledError:
                raise
            except RedisError as exc:
                logger.warning('Redis subscriber loop interrupted: %s', exc)
                await asyncio.sleep(1)
            finally:
                await pubsub.aclose()

    async def _handle_event(self, event: dict) -> None:
        """Route one Redis event to the local connection manager."""
        if event.get('source_instance') == self.instance_id:
            return

        if self._ws_manager is None:
            return

        event_type = event.get('event')
        if event_type == 'presence_changed':
            await self.broadcast_presence_snapshot()
            return

        target_user = event.get('target_user')
        payload = event.get('payload')
        if not isinstance(target_user, str) or not isinstance(payload, dict):
            return

        if not self._ws_manager.has_user(target_user):
            return

        if event_type in {'direct_message', 'typing'}:
            await self._ws_manager.send_to_user(target_user, payload)
