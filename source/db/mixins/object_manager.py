from copy import copy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, and_, exists, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette import status


class ObjectManagerMixin:
    excluded_fields = ['session']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def validate_fields(cls, fields):
        for field in copy(fields):
            if field in cls.excluded_fields:
                continue
            if not hasattr(cls, field):
                fields.pop(field)
        print(fields)
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
    def build_filter_conditions(cls, filters: dict) -> list:
        conditions = []
        for key, value in filters.items():
            if '__' in key:
                field, operator = key.split('__', 1)
                column = getattr(cls, field)
                if operator == 'gt':
                    conditions.append(column > value)
                elif operator == 'gte':
                    conditions.append(column >= value)
                elif operator == 'lt':
                    conditions.append(column <= value)
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
            **filters
    ):
        if fields is None:
            query = select(cls)
        else:
            query = select(*fields)

        if filters:
            conditions = cls.build_filter_conditions(filters)
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
    async def get(cls, *, session, relationships: tuple[Any] = None, fields: tuple[Any] = None, **filters):
        if fields is None:
            query = select(cls)
        else:
            query = select(*fields)

        if filters:
            conditions = cls.build_filter_conditions(filters)
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
    async def exists(cls, *, session: AsyncSession, **filters):
        query = select(exists(cls.id))

        if filters:
            conditions = cls.build_filter_conditions(filters)
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
    async def update_by(cls, *, session: AsyncSession, values: dict, commit: bool = True, **filters) -> int:
        stmt = update(cls).values(**values)

        if filters:
            conditions = cls.build_filter_conditions(filters)
            stmt = stmt.where(and_(*conditions))

        result = await session.execute(stmt)
        if commit:
            await session.commit()
        else:
            await session.flush()

        return result.rowcount

    async def delete(obj: Any, *, session: AsyncSession, commit: bool = True) -> None:  # noqa
        await session.delete(obj)
        if commit:
            await session.commit()
        else:
            await session.flush()

    @classmethod
    async def delete_by(cls, *, session: AsyncSession, commit: bool = True, **filters):
        query = delete(cls)
        if filters:
            conditions = cls.build_filter_conditions(filters)
            query = query.where(and_(*conditions))

        result = await session.execute(query)
        if commit:
            await session.commit()
        else:
            await session.flush()

        return result.rowcount
