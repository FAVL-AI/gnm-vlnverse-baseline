"""VLN API router — voice/text/image instruction intake + status."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/vln", tags=["vln"])

# In-memory state (resets on server restart)
_state: Dict[str, Any] = {
    "latest_instruction": None,
    "parsed_instruction": None,
    "chosen_subgoal": None,
    "model": "gnm",
    "u_nom": [0.0, 0.0],
    "u_safe": [0.0, 0.0],
    "cbf_active": False,
    "qp_status": "not_available",
    "last_cert_safe": None,
    "latest_camera_timestamp": None,
    "trace_count": 0,
    "recent_traces": [],
}

# VLN grounder / router (lazy import so server starts without torch)
_grounder = None
_router_obj = None


def _ensure_vln_loaded() -> bool:
    global _grounder, _router_obj
    if _grounder is not None:
        return True
    try:
        _repo = Path(__file__).resolve().parents[4]
        if str(_repo) not in sys.path:
            sys.path.insert(0, str(_repo))
        from fleet_safe_vla.vln.grounding import InstructionGrounder
        from fleet_safe_vla.vln.backbone_router import BackboneRouter, BackboneChoice
        _grounder = InstructionGrounder()
        _router_obj = BackboneRouter(preferred=BackboneChoice.MOCK)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class InstructionRequest(BaseModel):
    text: str
    source: str = "text"
    image_path: Optional[str] = None
    preferred_backbone: Optional[str] = None


class InstructionResponse(BaseModel):
    instruction_id: str
    parsed_action: str
    label: str
    confidence: float
    u_nom: List[float]
    u_safe: List[float]
    cbf_active: bool
    qp_status: str
    clarification_needed: bool
    explanation: str
    latency_ms: float


class VLNStatus(BaseModel):
    latest_instruction: Optional[str]
    parsed_instruction: Optional[Dict[str, Any]]
    chosen_subgoal: Optional[Dict[str, Any]]
    model: str
    u_nom: List[float]
    u_safe: List[float]
    cbf_active: bool
    qp_status: str
    last_cert_safe: Optional[bool]
    trace_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/instruction", response_model=InstructionResponse)
async def post_instruction(req: InstructionRequest) -> InstructionResponse:
    """Parse and ground a natural-language instruction."""
    import time, math

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Instruction text is empty.")

    if not _ensure_vln_loaded():
        raise HTTPException(status_code=503, detail="VLN module not available.")

    from fleet_safe_vla.vln.instruction_schema import VLNInstruction, InstructionSource
    t0 = time.perf_counter()

    try:
        source = InstructionSource(req.source)
    except ValueError:
        source = InstructionSource.TEXT

    inst = VLNInstruction.from_text(req.text)
    inst.source = source.value
    if req.image_path:
        inst.image_path = req.image_path
    if req.preferred_backbone:
        inst.preferred_backbone = req.preferred_backbone

    goal = _grounder.ground(inst)
    action = _router_obj.run_nominal_policy(goal, instruction=inst)
    u_nom = action.as_list()

    # Simple CBF approximation for API response
    u_safe = u_nom if goal.nominal_vx <= 0.12 else [0.12, u_nom[1]]
    cbf_active = u_safe != u_nom
    latency_ms = (time.perf_counter() - t0) * 1000.0

    # Update state
    _state["latest_instruction"] = req.text
    _state["parsed_instruction"] = goal.to_dict()
    _state["chosen_subgoal"] = goal.to_dict()
    _state["model"] = action.backbone
    _state["u_nom"] = u_nom
    _state["u_safe"] = u_safe
    _state["cbf_active"] = cbf_active
    _state["qp_status"] = "optimal" if not goal.clarification_needed else "not_available"
    _state["trace_count"] += 1
    trace_entry = {
        "ts": time.time(),
        "instruction": req.text,
        "action": goal.action_type,
        "u_nom": u_nom,
        "u_safe": u_safe,
        "cbf": cbf_active,
    }
    _state["recent_traces"] = ([trace_entry] + _state["recent_traces"])[:50]

    return InstructionResponse(
        instruction_id=inst.instruction_id,
        parsed_action=goal.action_type,
        label=goal.label,
        confidence=goal.confidence,
        u_nom=u_nom,
        u_safe=u_safe,
        cbf_active=cbf_active,
        qp_status=_state["qp_status"],
        clarification_needed=goal.clarification_needed,
        explanation=action.explanation,
        latency_ms=latency_ms,
    )


@router.get("/status", response_model=VLNStatus)
async def get_status() -> VLNStatus:
    return VLNStatus(**{k: _state[k] for k in VLNStatus.model_fields})


@router.get("/trace/latest")
async def get_trace_latest(n: int = 20) -> Dict[str, Any]:
    return {
        "count": _state["trace_count"],
        "traces": _state["recent_traces"][:n],
    }


@router.post("/stop")
async def emergency_stop() -> Dict[str, str]:
    """Latch an emergency stop into the VLN state."""
    _state["u_nom"] = [0.0, 0.0]
    _state["u_safe"] = [0.0, 0.0]
    _state["latest_instruction"] = "STOP"
    _state["qp_status"] = "estop_fallback"
    _state["cbf_active"] = True
    return {"status": "stopped", "message": "Emergency stop latched."}
