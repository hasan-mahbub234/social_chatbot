"""Database utility functions."""
from typing import TypeVar, Generic, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)


class CRUDBase(Generic[T]):
    """Base CRUD operations."""
    
    def __init__(self, model: type[T]):
        self.model = model
    
    async def create(self, session: AsyncSession, obj_in: dict) -> T:
        """Create a new object."""
        db_obj = self.model(**obj_in)
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj
    
    async def get(self, session: AsyncSession, id: int) -> Optional[T]:
        """Get object by id."""
        return await session.get(self.model, id)
    
    async def get_all(self, session: AsyncSession, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all objects with pagination."""
        result = await session.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()
    
    async def update(self, session: AsyncSession, id: int, obj_in: dict) -> Optional[T]:
        """Update an object."""
        db_obj = await self.get(session, id)
        if db_obj:
            for key, value in obj_in.items():
                setattr(db_obj, key, value)
            await session.flush()
            await session.refresh(db_obj)
        return db_obj
    
    async def delete(self, session: AsyncSession, id: int) -> bool:
        """Delete an object."""
        db_obj = await self.get(session, id)
        if db_obj:
            await session.delete(db_obj)
            await session.flush()
            return True
        return False
    
    async def count(self, session: AsyncSession) -> int:
        """Count objects."""
        result = await session.execute(select(func.count()).select_from(self.model))
        return result.scalar()
