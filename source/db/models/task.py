"""
Task model - Tasks and reminders
"""

from sqlalchemy import (
    Column, DateTime, String, Text, ForeignKey, Index, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin
from db.models.enums import TaskStatusEnum, TaskPriorityEnum


class Task(Base, ObjectManagerMixin):
    """
    Task model - Tasks, todos, and reminders

    Can be linked to any entity (lead, contact, deal, etc.)
    Supports due dates and assignment to users.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index('idx_tasks_company_id', 'company_id'),
        Index('idx_tasks_company_active', 'company_id', 'deleted_at'),
        Index('idx_tasks_assigned_to', 'assigned_to'),
        Index('idx_tasks_created_by', 'created_by'),
        Index('idx_tasks_status', 'status'),
        Index('idx_tasks_due_date', 'due_date'),
        Index('idx_tasks_entity', 'entity_type', 'entity_id'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    # Company relationship
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Task info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(
        SQLEnum(TaskStatusEnum, name="task_status_enum", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=TaskStatusEnum.PENDING
    )
    priority = Column(
        SQLEnum(TaskPriorityEnum, name="task_priority_enum", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=TaskPriorityEnum.MEDIUM
    )

    # Dates
    due_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Assignment
    assigned_to = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Linked entity (polymorphic)
    entity_type = Column(String(50))  # 'lead', 'contact', 'deal'
    entity_id = Column(UUID(as_uuid=True))

    # Custom fields
    custom_fields = Column(JSONB, server_default=text("'{}'::jsonb"))

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assigned_to], back_populates="assigned_tasks")
    creator = relationship("User", foreign_keys=[created_by], back_populates="created_tasks")

    def __repr__(self):
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"

    @property
    def is_overdue(self):
        """Check if task is overdue"""
        if not self.due_date or self.status == TaskStatusEnum.COMPLETED:
            return False
        return self.due_date < func.now()

    def complete(self):
        """Mark task as completed"""
        self.status = TaskStatusEnum.COMPLETED
        self.completed_at = func.now()
