"""
Database enums for the SIPtools CRM platform
"""

import enum


class CallStatusEnum(str, enum.Enum):
    """Call status enumeration"""
    ANSWER = "ANSWER"
    BUSY = "BUSY"
    NOANSWER = "NOANSWER"
    CANCEL = "CANCEL"
    CONGESTION = "CONGESTION"
    CHANUNAVAIL = "CHANUNAVAIL"


class ProviderEnum(str, enum.Enum):
    """Telephony provider enumeration"""
    SIPUNI = "sipuni"
    BINOTEL = "binotel"


class RoleEnum(str, enum.Enum):
    """User role enumeration"""
    OWNER = "owner"
    COMPANY_ADMIN = "company_admin"
    COMPANY_MANAGER = "company_manager"
    COMPANY_OPERATOR = "company_operator"


class LeadStatusEnum(str, enum.Enum):
    """Lead status enumeration"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class PipelineStageEnum(str, enum.Enum):
    """Lead pipeline stage enumeration"""
    NEW = "new"
    CONTACT_MADE = "contact_made"
    MEETING_SCHEDULED = "meeting_scheduled"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class DealStageEnum(str, enum.Enum):
    """Deal stage enumeration"""
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class TaskStatusEnum(str, enum.Enum):
    """Task status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriorityEnum(str, enum.Enum):
    """Task priority enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CallDirectionEnum(str, enum.Enum):
    """Call direction enumeration"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class CallOutcomeEnum(str, enum.Enum):
    """Call outcome/disposition enumeration"""
    # Positive outcomes
    INTERESTED = "interested"
    APPOINTMENT_SCHEDULED = "appointment_scheduled"
    FOLLOW_UP = "follow_up"
    SALE_MADE = "sale_made"

    # Neutral outcomes
    NO_ANSWER = "no_answer"
    LEFT_VOICEMAIL = "left_voicemail"
    BUSY = "busy"
    CALLBACK_REQUESTED = "callback_requested"
    INFORMATION_PROVIDED = "information_provided"

    # Negative outcomes
    NOT_INTERESTED = "not_interested"
    WRONG_NUMBER = "wrong_number"
    DO_NOT_CALL = "do_not_call"
    CUSTOMER_COMPLAINT = "customer_complaint"

    # Other
    OTHER = "other"
