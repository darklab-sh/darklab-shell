# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read the serving worker's captured configuration through disclosure policy."""

from config import get_loaded_config_snapshot
from config_inspection import inspection_payload
from services.audit.models import AuditEventType
from services.audit.recorder import record_event


def loaded_settings(context, request_fields):
    snapshot = get_loaded_config_snapshot()
    payload = inspection_payload(snapshot["values"], snapshot["provenance"], snapshot["warnings"], observation={
        "kind": "serving web worker's loaded configuration", "loaded_at": snapshot["loaded_at"],
        "process_id": snapshot["process_id"], "load_pid": snapshot["load_pid"], "app_version": snapshot["app_version"],
    })
    record_event(
        AuditEventType.INSTANCE_OPERATOR_VIEW, target_id=context.principal_id,
        actor_principal_id=context.principal_id, actor_credential_id=context.credential_id,
        details={"result": "served", "setting_count": len(payload["settings"])},
        request_id=request_fields.get("request_id", ""), client_ip=request_fields.get("client_ip", ""),
    )
    return payload
