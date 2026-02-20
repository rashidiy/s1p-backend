from copy import copy
from typing import Any
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, and_, exists, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status


class ObjectManagerMixin:
    excluded_fields = ['session']

    @classmethod
    def _has_soft_delete(cls) -> bool:
        """Check if model has soft delete support (deleted_at column)"""
        return hasattr(cls, 'deleted_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def validate_fields(cls, fields):
        """Validate and filter fields before database operations"""
        for field in copy(fields):
            if field in cls.excluded_fields:
                continue
            if not hasattr(cls, field):
                fields.pop(field)
        return fields

    @classmethod
    async def create(cls, *, session: AsyncSession, commit=True, **fields):
        obj = cls(**cls.validate_fields(fields))
        session.add(obj)

        if commit is True:
            await session.commit()
        else:
            await session.flush()

        await session.refresh(obj)
        return obj

    @classmethod
    async def get_or_create(cls, *, session: AsyncSession, commit=True, defaults: dict, **fields):
        created = False
        obj = await cls.get(**defaults, session=session)
        if not obj:
            obj = await cls.create(**fields, **defaults, session=session, commit=commit)
            created = True
        return obj, created

    @classmethod
    def build_filter_conditions(cls, filters: dict, include_deleted: bool = False) -> list:
        """
        Build filter conditions from filters dict

        Args:
            filters: Dictionary of field filters
            include_deleted: If False (default), exclude soft-deleted records

        Returns:
            List of SQLAlchemy filter conditions
        """
        conditions = []

        # Automatically filter out soft-deleted records
        if cls._has_soft_delete() and not include_deleted:
            # Only include records where deleted_at IS NULL
            conditions.append(cls.deleted_at.is_(None))

        for key, value in filters.items():
            if '__' in key:
                field, operator = key.split('__', 1)
                column = getattr(cls, field)
                if operator == 'gt':
                    conditions.append(column > value)
                elif operator == 'gte':
                    conditions.append(column >= value)
                elif operator == 'lt':
                    conditions.append(column < value)
                elif operator == 'lte':
                    conditions.append(column <= value)
                elif operator == 'ne':
                    conditions.append(column != value)
                elif operator == 'in':
                    conditions.append(column.in_(value))
                elif operator == 'contains':
                    conditions.append(column.contains(value))
                else:
                    conditions.append(column == value)
            else:
                conditions.append(getattr(cls, key) == value)
        return conditions

    @classmethod
    async def get_all(
            cls,
            *,
            session: AsyncSession,
            relationships: tuple[Any] = None,
            limit: int = None,
            offset: int = None,
            order_by: tuple[Any] = None,
            annotate: dict = None,
            fields: list = None,
            include_deleted: bool = False,
            **filters
    ):
        """
        Get all records matching filters

        Args:
            session: Database session
            relationships: Relationships to eagerly load
            limit: Maximum number of records
            offset: Number of records to skip
            order_by: Ordering clauses
            annotate: Additional columns to add
            fields: Specific fields to select
            include_deleted: If True, include soft-deleted records
            **filters: Field filters

        Returns:
            List of matching records
        """
        if fields is None:
            query = select(cls)
        else:
            query = select(*fields)

        # Build conditions with soft delete filtering
        conditions = cls.build_filter_conditions(filters, include_deleted=include_deleted)
        if conditions:
            query = query.where(and_(*conditions))

        if relationships:
            query = query.options(*[selectinload(rel) for rel in relationships])
        if annotate:
            for alias, expr in annotate.items():
                query = query.add_columns(expr.label(alias))
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)
        if order_by is not None:
            query = query.order_by(*order_by)

        result = await session.execute(query)

        if fields:
            if len(fields) == 1:
                objs = result.scalars().all()
            else:
                objs = result.fetchall()
        elif annotate:
            objs = result.all()
        else:
            objs = result.scalars().all()

        return objs

    @classmethod
    async def get(cls, *, session, relationships: tuple[Any] = None, fields: tuple[Any] = None, include_deleted: bool = False, **filters):
        """
        Get a single record matching filters

        Args:
            session: Database session
            relationships: Relationships to eagerly load
            fields: Specific fields to select
            include_deleted: If True, include soft-deleted records
            **filters: Field filters

        Returns:
            Matching record or None
        """
        if fields is None:
            query = select(cls)
        else:
            query = select(*fields)

        # Build conditions with soft delete filtering
        conditions = cls.build_filter_conditions(filters, include_deleted=include_deleted)
        if conditions:
            query = query.where(and_(*conditions))

        if relationships:
            query = query.options(*[selectinload(rel) for rel in relationships])

        result = await session.execute(query)

        if fields:
            if len(fields) == 1:
                objs = result.scalars().one()
            else:
                objs = result.fetchone()
        else:
            objs = result.scalar_one_or_none()
        return objs

    @classmethod
    async def get_or_404(cls, *, session, relationships: tuple[Any] = None, fields: tuple[Any] = None, **filters):
        obj = await cls.get(session=session, relationships=relationships, fields=fields, **filters)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "%s not found" % cls.__name__)
        return obj

    @classmethod
    async def exists(cls, *, session: AsyncSession, include_deleted: bool = False, **filters):
        """
        Check if a record exists

        Args:
            session: Database session
            include_deleted: If True, include soft-deleted records
            **filters: Field filters

        Returns:
            True if record exists, False otherwise
        """
        query = select(exists(cls.id))

        conditions = cls.build_filter_conditions(filters, include_deleted=include_deleted)
        if conditions:
            query = query.where(and_(*conditions))

        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def update(obj: Any, *, session: AsyncSession, commit: bool = True):  # noqa
        if commit is True:
            await session.commit()
        else:
            await session.flush()

        await session.refresh(obj)
        return obj

    @classmethod
    async def update_by(cls, *, session: AsyncSession, values: dict, commit: bool = True, include_deleted: bool = False, **filters) -> int:
        """
        Update records by filters

        Args:
            session: Database session
            values: Dictionary of field values to update
            commit: Whether to commit the transaction
            include_deleted: If True, update soft-deleted records too
            **filters: Field filters

        Returns:
            Number of records updated
        """
        stmt = update(cls).values(**values)

        conditions = cls.build_filter_conditions(filters, include_deleted=include_deleted)
        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await session.execute(stmt)
        if commit:
            await session.commit()
        else:
            await session.flush()

        return result.rowcount

    async def delete(obj: Any, *, session: AsyncSession, commit: bool = True, hard: bool = False) -> None:  # noqa
        """
        Delete a record (soft delete by default)

        Args:
            obj: The object to delete
            session: Database session
            commit: Whether to commit the transaction
            hard: If True, perform hard delete (permanent). Otherwise, soft delete.
        """
        if hasattr(obj, 'deleted_at') and not hard:
            # Soft delete: set deleted_at timestamp
            obj.deleted_at = datetime.now(timezone.utc)
            if commit:
                await session.commit()
            else:
                await session.flush()
            await session.refresh(obj)
        else:
            # Hard delete: remove from database
            await session.delete(obj)
            if commit:
                await session.commit()
            else:
                await session.flush()

    @classmethod
    async def delete_by(cls, *, session: AsyncSession, commit: bool = True, hard: bool = False, **filters):
        """
        Delete records by filters (soft delete by default)

        Args:
            session: Database session
            commit: Whether to commit the transaction
            hard: If True, perform hard delete. Otherwise, soft delete.
            **filters: Field filters

        Returns:
            Number of records deleted
        """
        if cls._has_soft_delete() and not hard:
            # Soft delete: update deleted_at
            conditions = cls.build_filter_conditions(filters, include_deleted=False)
            stmt = update(cls).values(deleted_at=datetime.now(timezone.utc))
            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await session.execute(stmt)
            if commit:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
        else:
            # Hard delete: remove from database
            query = delete(cls)
            conditions = cls.build_filter_conditions(filters, include_deleted=True)
            if conditions:
                query = query.where(and_(*conditions))

            result = await session.execute(query)
            if commit:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
