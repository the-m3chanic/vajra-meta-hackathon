"""Core environment: step() / reset() / state()"""

from __future__ import annotations
import uuid
from typing import Optional
from server.environment.models import (
    Action, ActionType, Observation, Reward, EnvironmentState,
    IncidentPhase, StepResponse, RewardBreakdown
)
from server.environment.rewards import RewardCalculator
from server.environment.graders import TaskGrader
from server.environment.tasks import get_task, Task
from server.environment.scenario_generator import generate_scenario
from server.environment.infrastructure import InfrastructureSimulator


class IncidentRCAEnv:
    def __init__(self):
        self.reward_calc = RewardCalculator()
        self.grader = TaskGrader()
        self._reset_internal()

    def _reset_internal(self):
        self.episode_id = ""
        self.task: Optional[Task] = None
        self.task_id = ""
        self.scenario: dict = {}
        self.infra: Optional[InfrastructureSimulator] = None
        self.step_number = 0
        self.max_steps = 25
        self.current_phase = IncidentPhase.TRIAGE
        self.done = False
        self.assessed_severity: Optional[str] = None
        self.evidence_collected: list[dict] = []
        self.hypotheses: list[dict] = []
        self.identified_root_cause: Optional[dict] = None
        self.remediation_applied: Optional[dict] = None
        self.affected_services_known: list[str] = []
        self.incident_timeline: list[dict] = []
        self.cumulative_reward = 0.0
        self.repeated_action_count = 0
        self._last_action_key: Optional[str] = None

    def reset(self, task_id: str = "easy_single_service_outage", seed: int = None) -> Observation:
        self._reset_internal()
        self.task = get_task(task_id)
        self.task_id = task_id
        self.max_steps = self.task.max_steps
        self.episode_id = str(uuid.uuid4())
        effective_seed = seed if seed is not None else self.task.seeds[0]
        self.scenario = generate_scenario(task_id, effective_seed)
        self.infra = self.scenario["infrastructure"]
        self.affected_services_known = [self.scenario["alert"].service]
        return self._make_observation()

    def step(self, action: Action) -> StepResponse:
        if self.done:
            return StepResponse(observation=self._make_observation(),
                           reward=Reward(score=0.02, message="Episode done."),
                           done=True, info={"error": "Episode done. Call reset()."})
        self.step_number += 1
        ak = self._action_key(action)
        is_rep = ak == self._last_action_key
        if is_rep:
            self.repeated_action_count += 1
        self._last_action_key = ak

        gt = self.scenario["ground_truth"]
        phase_before = self.current_phase
        ctx = {"ground_truth": gt, "is_repeated_action": is_rep, "invalid_action": False,
               "queried_service": None, "remediation_service": None,
               "has_identified_root_cause": self.identified_root_cause is not None}

        handler = self._handlers().get(action.action_type)
        info = handler(action, ctx) if handler else {"error": f"Unknown: {action.action_type}"}

        reward = self.reward_calc.calculate_step_reward(action, phase_before, self.current_phase, ctx)
        self.cumulative_reward += reward.score
        self.incident_timeline.append({"step": self.step_number, "timestamp": f"T+{self.step_number}min",
                                        "action_type": action.action_type.value,
                                        "summary": reward.message, "reward": reward.score})
        if self.step_number >= self.max_steps:
            self.done = True
            info["reason"] = "max_steps_reached"

        return StepResponse(observation=self._make_observation(), reward=reward, done=self.done, info=info)

    def state(self) -> EnvironmentState:
        gt = self.scenario.get("ground_truth", {})
        return EnvironmentState(
            task_id=self.task_id, episode_id=self.episode_id,
            step_number=self.step_number, max_steps=self.max_steps,
            current_phase=self.current_phase, severity_level=self.assessed_severity,
            ground_truth_root_cause=gt, ground_truth_severity=gt.get("severity", ""),
            ground_truth_remediation=gt.get("correct_remediation", ""),
            ground_truth_root_service=gt.get("root_cause_service", ""),
            identified_root_cause=self.identified_root_cause,
            remediation_applied=self.remediation_applied,
            hypotheses=self.hypotheses, evidence_collected=self.evidence_collected,
            affected_services=self.affected_services_known,
            cumulative_reward=round(self.cumulative_reward, 4),
            done=self.done, incident_timeline=self.incident_timeline)

    def get_episode_data(self) -> dict:
        gt = self.scenario.get("ground_truth", {})
        return {"task_id": self.task_id, "root_cause_service": gt.get("root_cause_service", ""),
                "root_cause_category": gt.get("root_cause_category", ""),
                "correct_severity": gt.get("severity", ""),
                "correct_remediation": gt.get("correct_remediation", ""),
                "affected_services": gt.get("affected_services", []),
                "assessed_severity": self.assessed_severity,
                "evidence_collected": self.evidence_collected,
                "identified_root_cause": self.identified_root_cause,
                "remediation_applied": self.remediation_applied,
                "steps_taken": self.step_number, "max_steps": self.max_steps,
                "done": self.done, "repeated_actions": self.repeated_action_count}

    def grade(self) -> float:
        score = self.grader.grade_episode(self.get_episode_data())
        return round(max(0.02, min(0.98, score)), 4)

    def _handlers(self):
        return {
            ActionType.ASSESS_SEVERITY: self._h_severity,
            ActionType.QUERY_LOGS: self._h_logs,
            ActionType.QUERY_METRICS: self._h_metrics,
            ActionType.CHECK_DEPLOYMENTS: self._h_deploys,
            ActionType.CHECK_CONFIG_CHANGES: self._h_configs,
            ActionType.RUN_DIAGNOSTIC: self._h_diag,
            ActionType.FORM_HYPOTHESIS: self._h_hypothesis,
            ActionType.TEST_HYPOTHESIS: self._h_test_hyp,
            ActionType.IDENTIFY_ROOT_CAUSE: self._h_identify,
            ActionType.REMEDIATE_ROLLBACK: self._h_rollback,
            ActionType.REMEDIATE_SCALE: self._h_scale,
            ActionType.REMEDIATE_RESTART: self._h_restart,
            ActionType.REMEDIATE_CONFIG_FIX: self._h_config_fix,
            ActionType.REMEDIATE_HOTFIX: self._h_hotfix,
            ActionType.ESCALATE: self._h_escalate,
            ActionType.UPDATE_STATUS_PAGE: self._h_status,
        }

    def _h_severity(self, a, ctx):
        p = a.parameters.assess_severity
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        self.assessed_severity = p.assessed_severity.value
        if self.current_phase == IncidentPhase.TRIAGE:
            self.current_phase = IncidentPhase.INVESTIGATION
        return {"status": "assessed", "severity": self.assessed_severity}

    def _h_logs(self, a, ctx):
        p = a.parameters.query_logs
        if not p: ctx["invalid_action"] = True; return {"error": "need service"}
        gt = ctx["ground_truth"]
        ctx["queried_service"] = p.service
        is_aff = p.service in gt.get("affected_services", [])
        logs = self.infra.generate_logs(p.service, gt["root_cause_service"], gt["root_cause_category"],
                                         p.level_filter, p.time_range_minutes, p.search_pattern, is_aff)
        self.evidence_collected.append({"type": "logs", "service": p.service, "count": len(logs),
                                         "summary": f"{len(logs)} logs from {p.service}"})
        if p.service not in self.affected_services_known and is_aff:
            self.affected_services_known.append(p.service)
        if self.current_phase == IncidentPhase.TRIAGE:
            self.current_phase = IncidentPhase.INVESTIGATION
        return {"status": "ok", "logs": logs}

    def _h_metrics(self, a, ctx):
        p = a.parameters.query_metrics
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        gt = ctx["ground_truth"]
        ctx["queried_service"] = p.service
        metrics = self.infra.generate_metrics(p.service, p.metric_name, gt["root_cause_service"], 20, p.time_range_minutes)
        self.evidence_collected.append({"type": "metrics", "service": p.service, "metric": p.metric_name,
                                         "summary": f"{len(metrics)} points for {p.metric_name} on {p.service}"})
        if self.current_phase == IncidentPhase.TRIAGE:
            self.current_phase = IncidentPhase.INVESTIGATION
        return {"status": "ok", "metrics": metrics}

    def _h_deploys(self, a, ctx):
        p = a.parameters.check_deployments
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        gt = ctx["ground_truth"]
        ctx["queried_service"] = p.service or "all"
        deploys = self.infra.generate_deployments(p.service, gt["root_cause_service"],
                                                    gt["root_cause_category"],
                                                    self.scenario.get("bad_deployment_changelog", ""),
                                                    p.time_range_hours)
        self.evidence_collected.append({"type": "deployment", "service": p.service or "all",
                                         "count": len(deploys), "summary": f"{len(deploys)} deployments"})
        if self.current_phase == IncidentPhase.TRIAGE:
            self.current_phase = IncidentPhase.INVESTIGATION
        return {"status": "ok", "deployments": deploys}

    def _h_configs(self, a, ctx):
        p = a.parameters.check_config_changes
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        gt = ctx["ground_truth"]
        ctx["queried_service"] = p.service or "all"
        changes = self.infra.generate_config_changes(p.service, gt["root_cause_service"],
                                                      gt["root_cause_category"],
                                                      self.scenario.get("bad_config"),
                                                      p.time_range_hours)
        self.evidence_collected.append({"type": "config", "service": p.service or "all",
                                         "count": len(changes), "summary": f"{len(changes)} config changes"})
        if self.current_phase == IncidentPhase.TRIAGE:
            self.current_phase = IncidentPhase.INVESTIGATION
        return {"status": "ok", "config_changes": changes}

    def _h_diag(self, a, ctx):
        p = a.parameters.run_diagnostic
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        gt = ctx["ground_truth"]
        ctx["queried_service"] = p.service
        result = self.infra.run_diagnostic(p.service, p.check_type, gt["root_cause_service"], gt["root_cause_category"])
        self.evidence_collected.append({"type": "diagnostic", "service": p.service, "check": p.check_type,
                                         "result": result["status"], "summary": result["message"]})
        if self.current_phase == IncidentPhase.TRIAGE:
            self.current_phase = IncidentPhase.INVESTIGATION
        return {"status": "ok", "result": result}

    def _h_hypothesis(self, a, ctx):
        p = a.parameters.form_hypothesis
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        h = {"index": len(self.hypotheses), "hypothesis": p.hypothesis,
             "root_cause_category": p.root_cause_category.value,
             "suspected_service": p.suspected_service, "confidence": p.confidence,
             "supporting_evidence": p.supporting_evidence, "status": "active"}
        self.hypotheses.append(h)
        if self.current_phase == IncidentPhase.INVESTIGATION:
            self.current_phase = IncidentPhase.DIAGNOSIS
        return {"status": "ok", "hypothesis": h}

    def _h_test_hyp(self, a, ctx):
        p = a.parameters.test_hypothesis
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        if 0 <= p.hypothesis_index < len(self.hypotheses):
            h = self.hypotheses[p.hypothesis_index]
            gt = ctx["ground_truth"]
            match = h["root_cause_category"] == gt["root_cause_category"] and h["suspected_service"] == gt["root_cause_service"]
            if match:
                h["status"] = "supported"; h["confidence"] = min(0.98, h["confidence"] + 0.2)
                return {"status": "ok", "result": "Evidence supports hypothesis", "hypothesis": h}
            h["status"] = "weakened"; h["confidence"] = max(0.02, h["confidence"] - 0.2)
            return {"status": "ok", "result": "Evidence does not support", "hypothesis": h}
        ctx["invalid_action"] = True
        return {"error": f"Bad index: {p.hypothesis_index}"}

    def _h_identify(self, a, ctx):
        p = a.parameters.identify_root_cause
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        self.identified_root_cause = {"root_cause_category": p.root_cause_category.value,
                                       "root_cause_service": p.root_cause_service,
                                       "root_cause_description": p.root_cause_description,
                                       "evidence_summary": p.evidence_summary, "confidence": p.confidence}
        self.current_phase = IncidentPhase.REMEDIATION
        return {"status": "ok", "root_cause": self.identified_root_cause}

    def _h_rollback(self, a, ctx):
        p = a.parameters.remediate_rollback
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        ctx["remediation_service"] = p.service
        self.remediation_applied = {"type": "rollback", "service": p.service, "reason": p.reason}
        self.current_phase = IncidentPhase.RESOLVED; self.done = True
        return {"status": "ok"}

    def _h_scale(self, a, ctx):
        p = a.parameters.remediate_scale
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        ctx["remediation_service"] = p.service
        self.remediation_applied = {"type": "scale_up", "service": p.service, "replicas": p.target_replicas, "reason": p.reason}
        self.current_phase = IncidentPhase.RESOLVED; self.done = True
        return {"status": "ok"}

    def _h_restart(self, a, ctx):
        p = a.parameters.remediate_restart
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        ctx["remediation_service"] = p.service
        self.remediation_applied = {"type": "restart", "service": p.service, "reason": p.reason}
        self.current_phase = IncidentPhase.RESOLVED; self.done = True
        return {"status": "ok"}

    def _h_config_fix(self, a, ctx):
        p = a.parameters.remediate_config_fix
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        ctx["remediation_service"] = p.service
        self.remediation_applied = {"type": "config_fix", "service": p.service,
                                     "parameter": p.parameter, "new_value": p.new_value, "reason": p.reason}
        self.current_phase = IncidentPhase.RESOLVED; self.done = True
        return {"status": "ok"}

    def _h_hotfix(self, a, ctx):
        p = a.parameters.remediate_hotfix
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        ctx["remediation_service"] = p.service
        self.remediation_applied = {"type": "hotfix", "service": p.service, "description": p.description, "reason": p.reason}
        self.current_phase = IncidentPhase.RESOLVED; self.done = True
        return {"status": "ok"}

    def _h_escalate(self, a, ctx):
        p = a.parameters.escalate
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        gt = ctx["ground_truth"]
        ctx["remediation_service"] = gt.get("root_cause_service", "")
        self.remediation_applied = {"type": "escalate", "service": gt.get("root_cause_service", ""),
                                     "target_team": p.target_team, "reason": p.reason}
        self.current_phase = IncidentPhase.ESCALATED; self.done = True
        return {"status": "ok"}

    def _h_status(self, a, ctx):
        p = a.parameters.update_status_page
        if not p: ctx["invalid_action"] = True; return {"error": "need params"}
        return {"status": "ok", "page_status": p.status}

    def _action_key(self, a: Action) -> str:
        k = a.action_type.value
        if a.parameters.query_logs: k += f":{a.parameters.query_logs.service}"
        elif a.parameters.query_metrics: k += f":{a.parameters.query_metrics.service}:{a.parameters.query_metrics.metric_name}"
        elif a.parameters.check_deployments: k += f":{a.parameters.check_deployments.service}"
        elif a.parameters.check_config_changes: k += f":{a.parameters.check_config_changes.service}"
        elif a.parameters.run_diagnostic: k += f":{a.parameters.run_diagnostic.service}:{a.parameters.run_diagnostic.check_type}"
        return k

    def _make_observation(self) -> Observation:
        alert = self.scenario.get("alert")
        
        # Add workflow hints based on phase
        description = self.task.description if self.task else ""
        if self.current_phase == IncidentPhase.TRIAGE:
            description += " | HINT: Start by assessing severity."
        elif self.current_phase == IncidentPhase.INVESTIGATION:
            description += " | HINT: Check logs, metrics, deployments, and configs on affected services."
        elif self.current_phase == IncidentPhase.DIAGNOSIS:
            description += " | HINT: Identify the root cause based on evidence collected."
        elif self.current_phase == IncidentPhase.REMEDIATION:
            description += " | HINT: Apply the appropriate fix for the identified root cause."

        return Observation(
            alert=alert.model_dump() if alert else {},
            system_topology=self.infra.get_topology_dict() if self.infra else {},
            queried_evidence=self.evidence_collected,
            active_hypotheses=self.hypotheses,
            incident_timeline=self.incident_timeline,
            current_phase=self.current_phase,
            affected_services=self.affected_services_known,
            severity_level=self.assessed_severity,
            identified_root_cause=self.identified_root_cause,
            remediation_applied=self.remediation_applied,
            step_number=self.step_number, max_steps=self.max_steps,
            task_id=self.task_id,
            task_description=description)