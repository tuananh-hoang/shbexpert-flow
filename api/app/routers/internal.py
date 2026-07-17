"""Internal-only endpoints — called by mcp-state (the only client allowed
to invoke state-changing tools; ai-architecture.md §6.1), never by `web`.

No RBAC/auth middleware exists yet — that's explicitly Phase 6 scope
(overview.md nguyên tắc 8, field-level RBAC). In a hardened deploy these
routes would sit behind a separate internal-only listener, not the public
`/api` surface `web` talks to. Noted here rather than silently assumed.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.db import get_session
from shared.schemas import Actor
from shared.state import InvalidTransitionError

router = APIRouter(prefix="/internal", tags=["internal"])


class TransitionRequest(BaseModel):
    new_state: str
    reason: str | None = None
    actor_type: str = "AGENT"
    actor_id: str = "orchestrator"


@router.post("/cases/{case_id}/transition")
def transition_case(case_id: str, body: TransitionRequest) -> dict:
    from shared.state import transition_state

    with get_session() as session:
        try:
            case = transition_state(
                session,
                case_id=case_id,
                new_state=body.new_state,
                actor=Actor(type=body.actor_type, id=body.actor_id),
                reason=body.reason,
            )
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"case_id": case.case_id, "state": case.state, "version": case.version}
