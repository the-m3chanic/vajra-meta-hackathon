"""FastAPI server for Incident RCA OpenEnv."""

from __future__ import annotations
import os, traceback
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from server.environment.core import IncidentRCAEnv
from server.environment.models import (
    Action, ActionType, ActionParameters, SeverityLevel, RootCauseCategory,
    AssessSeverityParams, QueryLogsParams, QueryMetricsParams,
    CheckDeploymentsParams, CheckConfigChangesParams, RunDiagnosticParams,
    FormHypothesisParams, TestHypothesisParams, IdentifyRootCauseParams,
    RemediateRollbackParams, RemediateScaleParams, RemediateRestartParams,
    RemediateConfigFixParams, RemediateHotfixParams, EscalateParams,
    UpdateStatusPageParams,
)
import uvicorn

from server.environment.tasks import list_tasks, TASKS

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.env = IncidentRCAEnv()
    yield

app = FastAPI(title="Incident RCA OpenEnv", version="1.0.0", lifespan=lifespan)

class ResetRequest(BaseModel):
    task_id: str = "easy_single_service_outage"
    seed: Optional[int] = None

class StepRequest(BaseModel):
    action_type: str
    parameters: dict = Field(default_factory=dict)

@app.get("/")
async def root():
    return {"name": "Incident RCA OpenEnv", "version": "1.0.0", "status": "running",
            "endpoints": ["/reset", "/step", "/state", "/tasks", "/grader", "/baseline"]}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/reset")
async def reset_get(task_id: str = "easy_single_service_outage", seed: int = None):
    try:
        obs = app.state.env.reset(task_id=task_id, seed=seed)
        return {"observation": obs.model_dump()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(400, str(e))
    
@app.post("/reset")
async def reset(req: ResetRequest=ResetRequest()):
    try:
        obs = app.state.env.reset(task_id=req.task_id, seed=req.seed)
        return {"observation": obs.model_dump()}
    except Exception as e:
        raise HTTPException(400, str(e))

def safe_score(score):
    """Ensure score is STRICTLY between 0 and 1."""
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 0.5
    if score != score:
        return 0.5
    if score <= 0.0:
        return 0.02
    if score >= 1.0:
        return 0.98
    return '{:.2f}'.format(round(score, 2)) if score < 0.98 else 0.98

@app.post("/step")
async def step(req: StepRequest = StepRequest(action_type="query_logs", parameters={})):
    try:
        env = app.state.env
        if not env.episode_id:
            env.reset(task_id="easy_single_service_outage", seed=1001)
        action = parse_action(req.action_type, req.parameters)
        r = env.step(action)
        reward_dict = r.reward.model_dump()
        raw_reward = reward_dict["score"]
        reward_dict["score"] = safe_score(reward_dict["score"])
        print(f"STEP: action={req.action_type} raw_reward={raw_reward} safe_reward={reward_dict['score']} done={r.done}", flush=True)
        return {"observation": r.observation.model_dump(), "reward": reward_dict,
                "done": r.done, "info": r.info}
    except HTTPException: raise
    except Exception as e:
        traceback.print_exc()
        print(f"STEP ERROR: {e}", flush=True)
        return {
            "observation": {},
            "reward": {"score": 0.5, "breakdown": {}, "message": str(e)[:100]},
            "done": True,
            "info": {"error": str(e)[:200]}
        }

@app.get("/state")
async def state():
    env = app.state.env
    if not env.episode_id:
        return {"error": "No episode."}
    return env.state().model_dump()

@app.get("/tasks")
async def tasks():
    return {"tasks": list_tasks()}

@app.get("/grader")
async def grader():
    env = app.state.env
    if not env.episode_id:
        print(f"GRADER: no episode, returning 0.5", flush=True)
        return {"task_id": "", "episode_id": "", "score": 0.5,
                "done": False, "steps_taken": 0, "phase": "triage",
                "cumulative_reward": 0.02, "details": {}}
    raw = env.grade()
    score = safe_score(raw)
    print(f"GRADER: task={env.task_id} raw_score={raw} safe_score={score} steps={env.step_number} done={env.done}", flush=True)
    ed = env.get_episode_data()
    return {"task_id": env.task_id, "episode_id": env.episode_id, "score": score,
            "done": env.done, "steps_taken": env.step_number,
            "phase": env.current_phase.value, "cumulative_reward": round(env.cumulative_reward, 4),
            "details": {"assessed_severity": ed.get("assessed_severity"),
                        "correct_severity": ed.get("correct_severity"),
                        "identified_root_cause": ed.get("identified_root_cause"),
                        "correct_service": ed.get("root_cause_service"),
                        "correct_category": ed.get("root_cause_category"),
                        "remediation": ed.get("remediation_applied"),
                        "correct_remediation": ed.get("correct_remediation"),
                        "evidence_count": len(ed.get("evidence_collected", []))}}

@app.get("/baseline")
async def baseline():
    try:
        return {"baseline_scores": run_server_baseline()}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))

def parse_action(at_str: str, params: dict) -> Action:
    at = ActionType(at_str)
    ap = ActionParameters()
    if at == ActionType.ASSESS_SEVERITY:
        ap.assess_severity = AssessSeverityParams(assessed_severity=SeverityLevel(params.get("assessed_severity", "sev3")), justification=params.get("justification", ""))
    elif at == ActionType.QUERY_LOGS:
        ap.query_logs = QueryLogsParams(service=params["service"], level_filter=params.get("level_filter"), time_range_minutes=params.get("time_range_minutes", 30), search_pattern=params.get("search_pattern"))
    elif at == ActionType.QUERY_METRICS:
        ap.query_metrics = QueryMetricsParams(service=params["service"], metric_name=params.get("metric_name", "error_rate"), time_range_minutes=params.get("time_range_minutes", 60))
    elif at == ActionType.CHECK_DEPLOYMENTS:
        ap.check_deployments = CheckDeploymentsParams(service=params.get("service"), time_range_hours=params.get("time_range_hours", 24))
    elif at == ActionType.CHECK_CONFIG_CHANGES:
        ap.check_config_changes = CheckConfigChangesParams(service=params.get("service"), time_range_hours=params.get("time_range_hours", 24))
    elif at == ActionType.RUN_DIAGNOSTIC:
        ap.run_diagnostic = RunDiagnosticParams(service=params["service"], check_type=params.get("check_type", "health"))
    elif at == ActionType.FORM_HYPOTHESIS:
        ap.form_hypothesis = FormHypothesisParams(hypothesis=params.get("hypothesis", ""), root_cause_category=RootCauseCategory(params.get("root_cause_category", "bad_deployment")), suspected_service=params.get("suspected_service", ""), confidence=params.get("confidence", 0.5), supporting_evidence=params.get("supporting_evidence", []))
    elif at == ActionType.TEST_HYPOTHESIS:
        ap.test_hypothesis = TestHypothesisParams(hypothesis_index=params.get("hypothesis_index", 0), test_action=params.get("test_action", ""))
    elif at == ActionType.IDENTIFY_ROOT_CAUSE:
        ap.identify_root_cause = IdentifyRootCauseParams(root_cause_category=RootCauseCategory(params.get("root_cause_category", "bad_deployment")), root_cause_service=params.get("root_cause_service", ""), root_cause_description=params.get("root_cause_description", ""), evidence_summary=params.get("evidence_summary", []), confidence=params.get("confidence", 0.8))
    elif at == ActionType.REMEDIATE_ROLLBACK:
        ap.remediate_rollback = RemediateRollbackParams(service=params["service"], target_version=params.get("target_version"), reason=params.get("reason", ""))
    elif at == ActionType.REMEDIATE_SCALE:
        ap.remediate_scale = RemediateScaleParams(service=params["service"], target_replicas=params.get("target_replicas", 5), reason=params.get("reason", ""))
    elif at == ActionType.REMEDIATE_RESTART:
        ap.remediate_restart = RemediateRestartParams(service=params["service"], reason=params.get("reason", ""))
    elif at == ActionType.REMEDIATE_CONFIG_FIX:
        ap.remediate_config_fix = RemediateConfigFixParams(service=params["service"], parameter=params.get("parameter", ""), new_value=params.get("new_value", ""), reason=params.get("reason", ""))
    elif at == ActionType.REMEDIATE_HOTFIX:
        ap.remediate_hotfix = RemediateHotfixParams(service=params["service"], description=params.get("description", ""), reason=params.get("reason", ""))
    elif at == ActionType.ESCALATE:
        ap.escalate = EscalateParams(target_team=params.get("target_team", "platform"), reason=params.get("reason", ""), summary=params.get("summary", ""))
    elif at == ActionType.UPDATE_STATUS_PAGE:
        ap.update_status_page = UpdateStatusPageParams(status=params.get("status", "investigating"), message=params.get("message", ""))
    return Action(action_type=at, parameters=ap)

def run_server_baseline() -> dict:
    env = IncidentRCAEnv()
    results = {}
    for task_id, task in TASKS.items():
        scores = []
        for seed in task.seeds:
            obs = env.reset(task_id=task_id, seed=seed)
            alert = obs.alert
            topo = obs.system_topology
            asvc = alert.get("service", "")
            env.step(parse_action("assess_severity", {"assessed_severity": alert.get("severity_hint", "sev3"), "justification": "hint"}))
            if env.done: scores.append(round(max(0.02, min(0.98, env.grade())), 4)); continue
            env.step(parse_action("query_logs", {"service": asvc, "level_filter": "ERROR", "time_range_minutes": 30}))
            if env.done: scores.append(round(max(0.02, min(0.98, env.grade())), 4)); continue
            target = asvc
            for dep in topo.get(asvc, {}).get("dependencies", []):
                if topo.get(dep, {}).get("status") in ("degraded", "down"):
                    target = dep; break
            if target != asvc:
                env.step(parse_action("query_logs", {"service": target, "level_filter": "ERROR", "time_range_minutes": 30}))
                if env.done: scores.append(round(max(0.02, min(0.98, env.grade())), 4)); continue
            r = env.step(parse_action("check_deployments", {"service": None, "time_range_hours": 24}))
            deploys = r.info.get("deployments", [])
            if env.done: scores.append(round(max(0.02, min(0.98, env.grade())), 4)); continue
            r = env.step(parse_action("check_config_changes", {"service": None, "time_range_hours": 24}))
            configs = r.info.get("config_changes", [])
            if env.done: scores.append(round(max(0.02, min(0.98, env.grade())), 4)); continue
            cat, rem = "resource_exhaustion", "restart"
            if any(d.get("service") == target for d in deploys): cat, rem = "bad_deployment", "rollback"
            elif any(c.get("service") == target for c in configs): cat, rem = "config_change", "config_fix"
            env.step(parse_action("identify_root_cause", {"root_cause_category": cat, "root_cause_service": target, "root_cause_description": f"{cat} on {target}", "evidence_summary": [f"Alert on {asvc}"], "confidence": 0.6}))
            if env.done: scores.append(round(max(0.02, min(0.98, env.grade())), 4)); continue
            if rem == "rollback":
                env.step(parse_action("remediate_rollback", {"service": target, "reason": "rollback"}))
            elif rem == "config_fix":
                param, old = "unknown", "prev"
                for c in configs:
                    if c.get("service") == target: param, old = c.get("parameter", "unknown"), c.get("old_value", "prev"); break
                env.step(parse_action("remediate_config_fix", {"service": target, "parameter": param, "new_value": old, "reason": "revert"}))
            else:
                env.step(parse_action("remediate_restart", {"service": target, "reason": "restart"}))
            scores.append(round(max(0.02, min(0.98, env.grade())), 4))
        avg = round(max(0.02, min(0.98, sum(scores) / len(scores))), 4) if scores else 0.5
        results[task_id] = {"average_score": avg, "episode_scores": scores, "num_episodes": len(scores), "difficulty": task.difficulty}
    return results

def main():
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
    
if __name__ == "__main__":
    main()
