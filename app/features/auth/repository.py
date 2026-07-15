from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        token_hash: str,
        csrf_hash: str,
        username: str,
        session_mode: str,
        created_at: datetime,
        idle_expires_at: datetime,
        absolute_expires_at: datetime,
        renew_after: datetime,
    ) -> AuthSession:
        record = AuthSession(
            token_hash=token_hash,
            csrf_hash=csrf_hash,
            username=username,
            session_mode=session_mode,
            created_at=created_at,
            last_seen_at=created_at,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
            renew_after=renew_after,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        result = await self.session.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def touch(
        self, record: AuthSession, *, last_seen_at: datetime, idle_expires_at: datetime
    ) -> AuthSession:
        record.last_seen_at = last_seen_at
        record.idle_expires_at = idle_expires_at
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def revoke(self, record: AuthSession, revoked_at: datetime) -> None:
        record.revoked_at = revoked_at
        await self.session.commit()
