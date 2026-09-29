"""Contact type predicates used by the reviewed runtime."""

from tcad_agent.adapters.devsim.payload import ContactPayload


def is_carrier_contact(contact: ContactPayload) -> bool:
    return contact.kind == "ohmic"


def is_electrostatic_contact(contact: ContactPayload) -> bool:
    return contact.kind in {"ideal_gate", "metal_work_function"}
