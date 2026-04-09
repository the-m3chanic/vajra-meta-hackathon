"""Reward function with partial progress signals."""

from __future__ import annotations
from server.environment.models import Action, ActionType, IncidentPhase, Reward, RewardBreakdown


class RewardCalculator:
    TRIAGE_W = 0.15
    INVESTIGATION_W = 0.25
    DIAGNOSIS_W = 0.30
    REMEDIATION_W = 0.20
    EFFICIENCY_W = 0.10

    INVESTIGATION_ACTIONS = {
        ActionType.QUERY_LOGS, ActionType.QUERY_METRICS,
        ActionType.CHECK_DEPLOYMENTS, ActionType.CHECK_CONFIG_CHANGES,
        ActionType.RUN_DIAGNOSTIC,
    }

    def calculate_step_reward(self, action: Action, phase_before: IncidentPhase,
                               phase_after: IncidentPhase, ctx: dict) -> Reward:
        bd = RewardBreakdown()
        score = 0.001
        msg = ""
        gt = ctx.get("ground_truth", {})
        root_svc = gt.get("root_cause_service", "")
        root_cat = gt.get("root_cause_category", "")
        correct_sev = gt.get("severity", "")
        affected = gt.get("affected_services", [])

        if action.action_type == ActionType.ASSESS_SEVERITY:
            p = action.parameters.assess_severity
            if p:
                if p.assessed_severity.value == correct_sev:
                    bd.triage_accuracy = 0.999
                    score += 0.12
                    msg = f"Correct severity: {p.assessed_severity.value}"
                else:
                    order = ["sev4", "sev3", "sev2", "sev1"]
                    try:
                        diff = abs(order.index(p.assessed_severity.value) - order.index(correct_sev))
                        partial = max(0, 0.999 - diff * 0.35)
                        bd.triage_accuracy = partial
                        score += partial * 0.08
                        msg = f"Severity {p.assessed_severity.value} (expected {correct_sev})"
                    except ValueError:
                        score -= 0.05
                        msg = "Invalid severity"

        elif action.action_type in self.INVESTIGATION_ACTIONS:
            qs = ctx.get("queried_service", "")
            iv = 0.001
            if qs == root_svc:
                iv = 0.08
                msg = f"Investigated root service: {qs}"
            elif qs in affected:
                iv = 0.04
                msg = f"Investigated affected: {qs}"
            else:
                iv = 0.01
                msg = f"Investigated {qs} (not directly related)"

            if action.action_type == ActionType.CHECK_DEPLOYMENTS and root_cat == "bad_deployment":
                iv += 0.04
                msg += " [relevant]"
            elif action.action_type == ActionType.CHECK_CONFIG_CHANGES and root_cat == "config_change":
                iv += 0.04
                msg += " [relevant]"
            elif action.action_type == ActionType.QUERY_METRICS and root_cat == "resource_exhaustion":
                iv += 0.03
                msg += " [relevant]"
            elif action.action_type == ActionType.QUERY_LOGS:
                iv += 0.02
            elif action.action_type == ActionType.RUN_DIAGNOSTIC:
                iv += 0.02

            bd.investigation_quality = min(0.999, iv / 0.12)
            score += iv

        elif action.action_type == ActionType.FORM_HYPOTHESIS:
            p = action.parameters.form_hypothesis
            if p:
                if p.root_cause_category.value == root_cat and p.suspected_service == root_svc:
                    score += 0.10
                    msg = "Hypothesis matches root cause!"
                elif p.root_cause_category.value == root_cat:
                    score += 0.05
                    msg = "Correct category, wrong service"
                elif p.suspected_service == root_svc:
                    score += 0.04
                    msg = "Correct service, wrong category"
                else:
                    score += 0.01
                    msg = "Hypothesis formed"

        elif action.action_type == ActionType.TEST_HYPOTHESIS:
            score += 0.02
            msg = "Hypothesis tested"

        elif action.action_type == ActionType.IDENTIFY_ROOT_CAUSE:
            p = action.parameters.identify_root_cause
            if p:
                cat_ok = p.root_cause_category.value == root_cat
                svc_ok = p.root_cause_service == root_svc
                if cat_ok and svc_ok:
                    bd.diagnosis_correctness = 0.999
                    score += 0.25
                    msg = "ROOT CAUSE CORRECTLY IDENTIFIED!"
                elif cat_ok:
                    bd.diagnosis_correctness = 0.4
                    score += 0.10
                    msg = f"Correct category, wrong service"
                elif svc_ok:
                    bd.diagnosis_correctness = 0.3
                    score += 0.08
                    msg = f"Correct service, wrong category"
                else:
                    bd.diagnosis_correctness = 0.001
                    score -= 0.05
                    msg = "Wrong root cause"

        elif action.action_type in (
            ActionType.REMEDIATE_ROLLBACK, ActionType.REMEDIATE_SCALE,
            ActionType.REMEDIATE_RESTART, ActionType.REMEDIATE_CONFIG_FIX,
            ActionType.REMEDIATE_HOTFIX, ActionType.ESCALATE,
        ):
            correct_rem = gt.get("correct_remediation", "")
            rem_map = {
                ActionType.REMEDIATE_ROLLBACK: "rollback", ActionType.REMEDIATE_SCALE: "scale_up",
                ActionType.REMEDIATE_RESTART: "restart", ActionType.REMEDIATE_CONFIG_FIX: "config_fix",
                ActionType.REMEDIATE_HOTFIX: "hotfix", ActionType.ESCALATE: "escalate",
            }
            agent_rem = rem_map.get(action.action_type, "unknown")
            rem_svc = ctx.get("remediation_service", "")
            targets_root = rem_svc == root_svc

            if agent_rem == correct_rem and targets_root:
                bd.remediation_appropriateness = 0.999
                score += 0.20
                msg = f"CORRECT: {agent_rem} on {rem_svc}"
            elif agent_rem == correct_rem:
                bd.remediation_appropriateness = 0.5
                score += 0.10
                msg = f"Right action, wrong target"
            elif targets_root:
                bd.remediation_appropriateness = 0.3
                score += 0.06
                msg = f"Right target, wrong action"
            else:
                partial = {"rollback": 0.1, "restart": 0.05, "escalate": 0.08,
                          "scale_up": 0.03, "config_fix": 0.05, "hotfix": 0.05}.get(agent_rem, 0)
                bd.remediation_appropriateness = partial
                score += partial
                msg = f"{agent_rem} (expected {correct_rem} on {root_svc})"

        elif action.action_type == ActionType.UPDATE_STATUS_PAGE:
            score += 0.02
            msg = "Status page updated"

        if ctx.get("is_repeated_action"):
            score -= 0.06
            bd.penalty -= 0.06
            msg += " [REPEAT PENALTY]"
        if ctx.get("invalid_action"):
            score -= 0.08
            bd.penalty -= 0.08
            msg += " [INVALID PENALTY]"
        if (action.action_type in (ActionType.REMEDIATE_ROLLBACK, ActionType.REMEDIATE_SCALE,
            ActionType.REMEDIATE_RESTART, ActionType.REMEDIATE_CONFIG_FIX, ActionType.REMEDIATE_HOTFIX)
            and not ctx.get("has_identified_root_cause")):
            score -= 0.10
            bd.penalty -= 0.10
            msg += " [NO DIAGNOSIS PENALTY]"

        score = max(-0.999, min(0.999, round(score, 4)))
        if score == 0.0:
            score = 0.001
        bd.penalty = max(-0.999, round(bd.penalty, 4))
        return Reward(score=score, breakdown=bd, message=msg)

    def calculate_episode_reward(self, data: dict) -> Reward:
        bd = RewardBreakdown()
        correct_sev = data.get("correct_severity", "")
        assessed = data.get("assessed_severity")
        if assessed:
            if assessed == correct_sev:
                bd.triage_accuracy = 0.999
            else:
                order = ["sev4", "sev3", "sev2", "sev1"]
                try:
                    diff = abs(order.index(assessed) - order.index(correct_sev))
                    bd.triage_accuracy = max(0, 0.999 - diff * 0.35)
                except ValueError:
                    bd.triage_accuracy = 0.001

        evidence = data.get("evidence_collected", [])
        root_svc = data.get("root_cause_service", "")
        root_cat = data.get("root_cause_category", "")
        found_root = any(e.get("service") == root_svc for e in evidence)
        inv_rel = sum(1 for e in evidence if e.get("service") in data.get("affected_services", []))
        if found_root:
            bd.investigation_quality = min(0.999, 0.5 + inv_rel * 0.1)
        elif evidence:
            bd.investigation_quality = min(0.4, len(evidence) * 0.08)
        ev_types = {e.get("type") for e in evidence}
        if root_cat == "bad_deployment" and "deployment" in ev_types:
            bd.investigation_quality = min(0.999, bd.investigation_quality + 0.2)
        elif root_cat == "config_change" and "config" in ev_types:
            bd.investigation_quality = min(0.999, bd.investigation_quality + 0.2)

        rc = data.get("identified_root_cause")
        if rc:
            cat_ok = rc.get("root_cause_category") == root_cat
            svc_ok = rc.get("root_cause_service") == root_svc
            if cat_ok and svc_ok:
                bd.diagnosis_correctness = 0.999
            elif cat_ok:
                bd.diagnosis_correctness = 0.4
            elif svc_ok:
                bd.diagnosis_correctness = 0.3

        rem = data.get("remediation_applied")
        correct_rem = data.get("correct_remediation", "")
        if rem:
            type_ok = rem.get("type") == correct_rem
            svc_ok = rem.get("service") == root_svc
            if type_ok and svc_ok:
                bd.remediation_appropriateness = 0.999
            elif type_ok:
                bd.remediation_appropriateness = 0.5
            elif svc_ok:
                bd.remediation_appropriateness = 0.3
            else:
                bd.remediation_appropriateness = 0.1

        steps = data.get("steps_taken", 0)
        mx = data.get("max_steps", 25)
        if data.get("done") and steps > 0:
            bd.efficiency = max(0, 0.999 - steps / mx)
        bd.efficiency = max(0, bd.efficiency - data.get("repeated_actions", 0) * 0.05)

        total = (bd.triage_accuracy * self.TRIAGE_W + bd.investigation_quality * self.INVESTIGATION_W +
                 bd.diagnosis_correctness * self.DIAGNOSIS_W +
                 bd.remediation_appropriateness * self.REMEDIATION_W + bd.efficiency * self.EFFICIENCY_W)
        total = max(-0.999, min(0.999, round(total, 4)))
        if total == 0.0:
            total = 0.001
        return Reward(score=total, breakdown=bd,
                      message=f"T:{bd.triage_accuracy:.2f} I:{bd.investigation_quality:.2f} "
                              f"D:{bd.diagnosis_correctness:.2f} R:{bd.remediation_appropriateness:.2f} "
                              f"E:{bd.efficiency:.2f}")