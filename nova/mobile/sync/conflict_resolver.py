"""ConflictResolver — Resolves sync conflicts using configurable policies."""

import logging
from typing import Optional, List
from nova.mobile.sync.models import SyncConflict, BLOCKED_SYNC_KEYS
from nova.mobile.sync.enums import ConflictPolicy, Platform

logger = logging.getLogger("nova.mobile.sync.conflict_resolver")


class ConflictResolver:
    def __init__(self, policy: ConflictPolicy = ConflictPolicy.NEWEST_WINS):
        self.policy = policy
        self._pending_user_confirmations: List[SyncConflict] = []

    def resolve(self, conflict: SyncConflict, local_platform: Platform) -> SyncConflict:
        # Block sensitive keys from ever being conflict-resolved
        if any(blocked in conflict.key.lower() for blocked in BLOCKED_SYNC_KEYS):
            logger.error(f"BLOCKED: Refusing to resolve sensitive key '{conflict.key}'")
            conflict.is_resolved = False
            return conflict

        if self.policy == ConflictPolicy.NEWEST_WINS:
            winner = conflict.remote_value if conflict.remote_timestamp >= conflict.local_timestamp \
                else conflict.local_value

        elif self.policy == ConflictPolicy.OLDEST_WINS:
            winner = conflict.local_value if conflict.local_timestamp <= conflict.remote_timestamp \
                else conflict.remote_value

        elif self.policy == ConflictPolicy.PHONE_WINS:
            winner = conflict.local_value if local_platform == Platform.ANDROID \
                else conflict.remote_value

        elif self.policy == ConflictPolicy.NOVA_CORE_WINS:
            winner = conflict.local_value if local_platform == Platform.NOVA_CORE \
                else conflict.remote_value

        elif self.policy == ConflictPolicy.USER_CONFIRM:
            self._pending_user_confirmations.append(conflict)
            logger.info(f"Conflict queued for user confirmation: {conflict.key}")
            conflict.is_resolved = False
            return conflict

        else:
            winner = conflict.local_value  # fallback

        conflict.resolved_value = winner
        conflict.is_resolved = True
        logger.info(f"Conflict resolved [{self.policy.value}]: '{conflict.key}' → '{winner}'")
        return conflict

    def resolve_by_user(self, conflict_id: str, chosen_value: str) -> Optional[SyncConflict]:
        for i, c in enumerate(self._pending_user_confirmations):
            if c.conflict_id == conflict_id:
                resolved = self._pending_user_confirmations.pop(i)
                resolved.resolved_value = chosen_value
                resolved.is_resolved = True
                logger.info(f"Conflict resolved by user: '{resolved.key}' → '{chosen_value}'")
                return resolved
        return None

    def get_pending(self) -> List[SyncConflict]:
        return list(self._pending_user_confirmations)

    def pending_count(self) -> int:
        return len(self._pending_user_confirmations)
