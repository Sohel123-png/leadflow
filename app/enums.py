from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    AGENT = "agent"


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    WON = "won"
    LOST = "lost"


# Allowed pipeline moves. WON and LOST are final states.
ALLOWED_TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.NEW: {LeadStatus.CONTACTED, LeadStatus.LOST},
    LeadStatus.CONTACTED: {LeadStatus.WON, LeadStatus.LOST},
    LeadStatus.WON: set(),
    LeadStatus.LOST: set(),
}
