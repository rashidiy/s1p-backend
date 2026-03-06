"""
Tasks management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import Optional
from uuid import UUID
from datetime import datetime

from db import get_session
from db.models.user import User
from db.models.task import Task
from db.models.contact import Contact
from db.models.enums import TaskStatusEnum, TaskPriorityEnum
from api.v1.schemas.crm import (
    TaskCreateRequest,
    TaskUpdateRequest,
    TaskResponse,
    PaginatedResponse
)
from utils.permissions import require_permissions, Permissions
from db.models.enums import RoleEnum

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.TASKS_WRITE)
async def create_task(
    data: TaskCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new task

    Tasks can be linked to contacts, leads, or deals for context.
    """
    # Validate assigned user if provided
    if data.assigned_to:
        assignee = await User.get_or_404(
            session=session,
            id=data.assigned_to,
            company_id=user.company_id
        )

    task = await Task.create(
        session=session,
        company_id=user.company_id,
        created_by=user.id,
        assigned_to=data.assigned_to or user.id,  # Default to creator
        **data.model_dump(exclude={'assigned_to'})
    )

    return task


@router.get("", response_model=PaginatedResponse)
@require_permissions(Permissions.TASKS_READ)
async def list_tasks(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[UUID] = None,
    overdue: bool = Query(False, description="Show only overdue tasks"),
    my_tasks: bool = Query(False, description="Show only my assigned tasks")
):
    """
    List all tasks with filters

    Operators see all tasks by default, but typically filter to show only their tasks.
    """
    query = select(Task).where(Task.company_id == user.company_id)

    # Operators only see their own tasks
    if user.role == RoleEnum.COMPANY_OPERATOR:
        query = query.where(Task.assigned_to == user.id)
    elif my_tasks:
        query = query.where(Task.assigned_to == user.id)

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Task.title.ilike(search_term),
                Task.description.ilike(search_term)
            )
        )

    # Filters
    if status_filter:
        try:
            status_enum = TaskStatusEnum(status_filter)
            query = query.where(Task.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {[s.value for s in TaskStatusEnum]}"
            )
    if priority:
        try:
            priority_enum = TaskPriorityEnum(priority)
            query = query.where(Task.priority == priority_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority. Must be one of: {[p.value for p in TaskPriorityEnum]}"
            )
    if assigned_to:
        query = query.where(Task.assigned_to == assigned_to)
    if overdue:
        query = query.where(
            and_(
                Task.due_date < datetime.now(),
                Task.status != TaskStatusEnum.COMPLETED
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Task.due_date.asc().nullslast(), Task.priority.desc())

    result = await session.execute(query)
    tasks = result.scalars().all()

    # Enhance with related info
    enhanced_tasks = []
    for task in tasks:
        # Get assigned to name
        assigned_to_name = None
        if task.assigned_to:
            assignee = await User.get(session=session, id=task.assigned_to)
            if assignee:
                assigned_to_name = assignee.full_name

        task_dict = {
            **{k: v for k, v in task.__dict__.items() if not k.startswith('_')},
            "assigned_to_name": assigned_to_name
        }
        enhanced_tasks.append(TaskResponse(**task_dict))

    return PaginatedResponse(
        items=enhanced_tasks,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/my-today", response_model=list)
@require_permissions(Permissions.TASKS_READ)
async def get_my_tasks_today(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get my tasks for today

    Returns pending tasks due today or overdue.
    """
    today_end = datetime.now().replace(hour=23, minute=59, second=59)

    query = select(Task).where(
        and_(
            Task.company_id == user.company_id,
            Task.assigned_to == user.id,
            Task.status != TaskStatusEnum.COMPLETED,
            or_(
                Task.due_date <= today_end,
                Task.due_date.is_(None)
            )
        )
    ).order_by(Task.priority.desc(), Task.due_date.asc().nullslast())

    result = await session.execute(query)
    tasks = result.scalars().all()

    return [
        {
            "id": str(task.id),
            "title": task.title,
            "priority": task.priority.value if task.priority else None,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "is_overdue": task.due_date < datetime.now() if task.due_date else False
        }
        for task in tasks
    ]


@router.get("/{task_id}", response_model=TaskResponse)
@require_permissions(Permissions.TASKS_READ)
async def get_task(
    task_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Get task details"""
    task = await Task.get_or_404(
        session=session,
        id=task_id,
        company_id=user.company_id
    )

    # Operators can only see their own tasks
    if user.role == RoleEnum.COMPANY_OPERATOR and task.assigned_to != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Get assigned to name
    assigned_to_name = None
    if task.assigned_to:
        assignee = await User.get(session=session, id=task.assigned_to)
        if assignee:
            assigned_to_name = assignee.full_name

    task_dict = {
        **{k: v for k, v in task.__dict__.items() if not k.startswith('_')},
        "assigned_to_name": assigned_to_name
    }

    return TaskResponse(**task_dict)


@router.put("/{task_id}", response_model=TaskResponse)
@require_permissions(Permissions.TASKS_WRITE)
async def update_task(
    task_id: UUID,
    data: TaskUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update task information

    Operators can update their own tasks. Admins can update all tasks.
    """
    task = await Task.get_or_404(
        session=session,
        id=task_id,
        company_id=user.company_id
    )

    # Check permissions: operators can only update their own tasks
    if user.role == RoleEnum.COMPANY_OPERATOR and task.assigned_to != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own tasks"
        )

    # Validate assigned user if changing
    if data.assigned_to:
        assignee = await User.get_or_404(
            session=session,
            id=data.assigned_to,
            company_id=user.company_id
        )

    # Validate custom fields against definitions
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    await task.update(session=session)

    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.TASKS_DELETE)
async def delete_task(
    task_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    hard: bool = Query(False)
):
    """Delete a task (Admins only)"""
    task = await Task.get_or_404(
        session=session,
        id=task_id,
        company_id=user.company_id
    )

    await task.delete(session=session, hard=hard)
    return None


@router.post("/{task_id}/complete", response_model=TaskResponse)
@require_permissions(Permissions.TASKS_WRITE)
async def complete_task(
    task_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Mark task as completed

    Any assigned user can complete their task.
    """
    task = await Task.get_or_404(
        session=session,
        id=task_id,
        company_id=user.company_id
    )

    # Check if user is assigned to this task or is admin
    if user.role == RoleEnum.COMPANY_OPERATOR and task.assigned_to != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only complete your own tasks"
        )

    task.status = TaskStatusEnum.COMPLETED
    task.completed_at = datetime.now()

    await task.update(session=session)

    return task
