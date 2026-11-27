from datetime import datetime, timezone
import uuid

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def add_event(case, action, actor="SYSTEM", details=None):
    evt = {
        "event_id":"EVT-"+uuid.uuid4().hex[:8].upper(),
        "time":now_iso(),
        "actor":actor,
        "action":action,
        "details":details or {}
    }
    case.setdefault("audit_timeline",[]).append(evt)
    return evt
