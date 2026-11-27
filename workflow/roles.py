from __future__ import annotations

# Human personas used by the prototype. These are governance roles, not user
# accounts. A production deployment would map them to authenticated RBAC groups.
WAREHOUSE_OPERATOR = "Warehouse Operator"
WAREHOUSE_MANAGER = "Warehouse Manager"
STORE_SITE_MANAGER = "Store / Site Manager"
LOGISTICS_OPERATOR = "Logistics Operator"
LOGISTICS_MANAGER = "Logistics Manager"
QUALITY_FOOD_SAFETY_MANAGER = "Quality & Food Safety Manager"
PROCUREMENT_TEAM = "Procurement Team"
PROCUREMENT_MANAGER = "Procurement Manager"
COMMUNICATIONS_TEAM = "Customer Communications Team"
RECALL_INCIDENT_MANAGER = "Recall / Incident Manager"
SENIOR_RESPONSIBLE_MANAGER = "Senior Responsible Manager"

HUMAN_ROLES = [
    WAREHOUSE_OPERATOR,
    WAREHOUSE_MANAGER,
    STORE_SITE_MANAGER,
    LOGISTICS_OPERATOR,
    LOGISTICS_MANAGER,
    QUALITY_FOOD_SAFETY_MANAGER,
    PROCUREMENT_TEAM,
    PROCUREMENT_MANAGER,
    COMMUNICATIONS_TEAM,
    RECALL_INCIDENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
]

ROLE_DESCRIPTIONS = {
    WAREHOUSE_OPERATOR: "Physically verifies lots and quantities and records operational evidence.",
    WAREHOUSE_MANAGER: "Authorises warehouse containment, stock holds and warehouse-level movement restrictions.",
    STORE_SITE_MANAGER: "Authorises site or store-level stock withdrawal and containment actions.",
    LOGISTICS_OPERATOR: "Performs distribution and shipment trace work.",
    LOGISTICS_MANAGER: "Authorises shipment pauses and distribution restrictions.",
    QUALITY_FOOD_SAFETY_MANAGER: "Central food-safety authority for recall response, evidence review and communication quality.",
    PROCUREMENT_TEAM: "Prepares supplier traceability and communication material.",
    PROCUREMENT_MANAGER: "Authorises supplier-facing follow-up and supplier communication.",
    COMMUNICATIONS_TEAM: "Prepares downstream/customer-facing communication drafts.",
    RECALL_INCIDENT_MANAGER: "Coordinates the recall response and authorises major escalation and case closure.",
    SENIOR_RESPONSIBLE_MANAGER: "Provides final accountable management authority for exceptional or high-impact decisions.",
}

CASE_CLOSURE_ROLES = {
    RECALL_INCIDENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
}


INVESTIGATION_ROLES = {
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
}

DEMO_RESET_ROLES = {
    RECALL_INCIDENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
}


MANAGEMENT_OVERVIEW_ROLES = {
    QUALITY_FOOD_SAFETY_MANAGER,
    RECALL_INCIDENT_MANAGER,
    SENIOR_RESPONSIBLE_MANAGER,
}
