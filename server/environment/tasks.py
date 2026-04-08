"""Task definitions with seeds for reproducibility."""

from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Task:
    id: str
    name: str
    description: str
    difficulty: str
    max_steps: int
    num_episodes: int
    seeds: list[int] = field(default_factory=list)

TASKS = {
    "easy_single_service_outage": Task(
        id="easy_single_service_outage",
        name="Single Service Outage",
        description="Single service failure with clear error in logs. Find it, diagnose it, fix it.",
        difficulty="easy", max_steps=15, num_episodes=5,
        seeds=[1001, 1002, 1003, 1004, 1005, 1006, 1007],
    ),
    "medium_cascading_failure": Task(
        id="medium_cascading_failure",
        name="Cascading Service Failure",
        description="Failure cascades across 2-4 services. Trace dependency chain to origin. Red herrings present.",
        difficulty="medium", max_steps=20, num_episodes=5,
        seeds=[2001, 2002, 2003, 2004, 2005, 2006, 2007],
    ),
    "hard_subtle_degradation": Task(
        id="hard_subtle_degradation",
        name="Subtle Performance Degradation",
        description="Misleading symptoms: CPU from regex, memory from connection leaks, DNS failures looking like app bugs. Multiple red herrings.",
        difficulty="hard", max_steps=25, num_episodes=5,
        seeds=[3001, 3002, 3003, 3004, 3005, 3006, 3007],
    ),
    "mixed_dynamic_incidents": Task(
        id="mixed_dynamic_incidents",
        name="Mixed Dynamic Incidents",
        description="Random mix of easy, medium, and hard incidents. Tests generalization across different root cause types and severity levels.",
        difficulty="mixed",
        max_steps=20,
        num_episodes=5,
        seeds=[4001, 4002, 4003, 4004, 4005],
    ),
}

def get_task(task_id: str) -> Task:
    if task_id not in TASKS:
        raise ValueError(f"Unknown task: {task_id}. Available: {list(TASKS.keys())}")
    return TASKS[task_id]

def list_tasks() -> list[dict]:
    return [{
        "id": t.id, "name": t.name, "description": t.description,
        "difficulty": t.difficulty, "max_steps": t.max_steps,
        "num_episodes": t.num_episodes,
        "action_schema": {
            "action_type": {
                "type": "string",
                "enum": [
                    "assess_severity", "query_logs", "query_metrics",
                    "check_deployments", "check_config_changes", "run_diagnostic",
                    "form_hypothesis", "test_hypothesis", "identify_root_cause",
                    "remediate_rollback", "remediate_scale", "remediate_restart",
                    "remediate_config_fix", "remediate_hotfix", "escalate",
                    "update_status_page",
                ],
            },
            "parameters": {"type": "object", "description": "Action-specific params"},
        },
    } for t in TASKS.values()]