from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.domain import User, APIKey, DetectionLog

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str):
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def create(self, user: User):
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

class APIKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_hash(self, key_hash: str):
        result = await self.db.execute(select(APIKey).where(APIKey.key_hash == key_hash))
        return result.scalars().first()

    async def get_by_user_id(self, user_id: int):
        result = await self.db.execute(select(APIKey).where(APIKey.user_id == user_id))
        return result.scalars().all()

    async def get_by_id_and_user_id(self, key_id: int, user_id: int):
        result = await self.db.execute(select(APIKey).where(APIKey.key_id == key_id, APIKey.user_id == user_id))
        return result.scalars().first()

    async def get_demo_key_by_user_id(self, user_id: int):
        result = await self.db.execute(
            select(APIKey).where(APIKey.user_id == user_id, APIKey.key_name == "__demo__")
        )
        return result.scalars().first()

    async def delete(self, api_key: APIKey):
        await self.db.delete(api_key)
        await self.db.commit()

    async def create(self, api_key: APIKey):
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        return api_key

class LogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, log: DetectionLog):
        self.db.add(log)
        await self.db.commit()
        return log

    async def get_by_user_id(self, user_id: int, limit: int = 50, offset: int = 0):
        from sqlalchemy.future import select
        from app.models.domain import APIKey
        stmt = select(DetectionLog).join(APIKey).where(
            APIKey.user_id == user_id
        ).order_by(DetectionLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_key_id(self, key_id: int, limit: int = 50, offset: int = 0):
        from sqlalchemy.future import select
        stmt = select(DetectionLog).where(
            DetectionLog.key_id == key_id
        ).order_by(DetectionLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return result.scalars().all()
