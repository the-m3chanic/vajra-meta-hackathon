"""Programmatic graders. Deterministic 0.0–1.0 scoring."""

from __future__ import annotations
from server.environment.rewards import RewardCalculator


class TaskGrader:
    def __init__(self):
        self.rc = RewardCalculator()

    def grade_episode(self, d: dict) -> float:
        tid = d.get("task_id", "")
        if tid == "easy_single_service_outage":
            return self._easy(d)
        elif tid == "medium_cascading_failure":
            return self._medium(d)
        elif tid == "hard_subtle_degradation":
            return self._hard(d)
        r = self.rc.calculate_episode_reward(d)
        return round(max(0.0, min(1.0, (r.score + 1) / 2)), 4)

    def _sev_score(self, d):
        if d.get("assessed_severity") == d.get("correct_severity"):
            return 1.0
        if d.get("assessed_severity"):
            o = ["sev4", "sev3", "sev2", "sev1"]
            try:
                return max(0, 1.0 - abs(o.index(d["assessed_severity"]) - o.index(d["correct_severity"])) * 0.35)
            except ValueError:
                pass
        return 0.0

    def _inv_score(self, d):
        root = d.get("root_cause_service", "")
        cat = d.get("root_cause_category", "")
        aff = set(d.get("affected_services", []))
        ev = d.get("evidence_collected", [])
        svcs = {e.get("service") for e in ev}
        types = {e.get("type") for e in ev}
        found = root in svcs
        cov = len(svcs & aff) / max(len(aff), 1)
        s = (0.5 + cov * 0.3) if found else cov * 0.3
        if cat == "bad_deployment" and "deployment" in types:
            s += 0.15
        elif cat == "config_change" and "config" in types:
            s += 0.15
        elif cat in ("resource_exhaustion", "memory_leak") and "metrics" in types:
            s += 0.1
        elif cat in ("certificate_expiry", "dns_failure") and "diagnostic" in types:
            s += 0.15
        return min(1.0, s)

    def _diag_score(self, d):
        rc = d.get("identified_root_cause")
        if not rc:
            return 0.0
        cat_ok = rc.get("root_cause_category") == d.get("root_cause_category")
        svc_ok = rc.get("root_cause_service") == d.get("root_cause_service")
        if cat_ok and svc_ok:
            return 1.0
        if cat_ok:
            return 0.35
        if svc_ok:
            return 0.25
        return 0.0

    def _rem_score(self, d):
        rem = d.get("remediation_applied")
        if not rem:
            return 0.0
        t_ok = rem.get("type") == d.get("correct_remediation")
        s_ok = rem.get("service") == d.get("root_cause_service")
        if t_ok and s_ok:
            return 1.0
        if t_ok:
            return 0.45
        if s_ok:
            return 0.25
        return 0.1

    def _easy(self, d):
        t = (self._sev_score(d) * 0.15 + self._inv_score(d) * 0.25 +
             self._diag_score(d) * 0.30 + self._rem_score(d) * 0.30)
        return round(max(0.0, min(1.0, t)), 4)

    def _medium(self, d):
        t = (self._sev_score(d) * 0.10 + self._inv_score(d) * 0.25 +
             self._diag_score(d) * 0.35 + self._rem_score(d) * 0.30)
        return round(max(0.0, min(1.0, t)), 4)

    def _hard(self, d):
        eff = 0.0
        if d.get("done") and d.get("steps_taken", 0) > 0:
            eff = max(0, 1.0 - d["steps_taken"] / d.get("max_steps", 25))
        eff = max(0, eff - d.get("repeated_actions", 0) * 0.05)
        t = (self._sev_score(d) * 0.05 + self._inv_score(d) * 0.25 +
             self._diag_score(d) * 0.40 + self._rem_score(d) * 0.25 + eff * 0.05)
        return round(max(0.0, min(1.0, t)), 4)