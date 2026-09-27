from langgraph.types import interrupt

from agents.state import InvestigationState
from agents.tools.actions_tool import apply_action


def remediation_node(state: InvestigationState) -> dict:
    """Pause for human approval before ever calling apply_action.

    interrupt() halts graph execution here and surfaces the payload to the
    caller (cli.py). The graph only resumes once the caller sends back
    Command(resume={"approved": bool}) -- apply_action is never reached
    otherwise, satisfying the "production actions require human approval"
    enterprise requirement.
    """
    rca = state["rca"]
    decision = interrupt(
        {
            "action": rca.recommended_action,
            "target_service": state["affected_service"],
            "rationale": rca.root_cause,
        }
    )

    approved = bool(decision.get("approved")) if isinstance(decision, dict) else False
    if not approved:
        return {"errors": state["errors"] + ["remediation action was not approved by a human operator"]}

    result = apply_action(
        action_type="remediate",
        target_service=state["affected_service"],
        params={"recommended_action": rca.recommended_action},
    )
    return {"errors": state["errors"] + [f"remediation result: {result}"]}
