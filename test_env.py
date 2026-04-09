import pytest
from server.environment.core import IncidentRCAEnv
from server.environment.models import *
from server.environment.tasks import TASKS, list_tasks

@pytest.fixture
def env():
    return IncidentRCAEnv()

class TestReset:
    def test_easy(self, env):
        obs = env.reset("easy_single_service_outage", seed=1001)
        assert obs.current_phase == IncidentPhase.TRIAGE
        assert obs.step_number == 0
        assert len(obs.system_topology) > 5

    def test_medium(self, env):
        obs = env.reset("medium_cascading_failure", seed=2001)
        assert obs.task_id == "medium_cascading_failure"

    def test_hard(self, env):
        obs = env.reset("hard_subtle_degradation", seed=3001)
        assert obs.task_id == "hard_subtle_degradation"

    def test_clean(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        env.step(Action(action_type=ActionType.ASSESS_SEVERITY, parameters=ActionParameters(assess_severity=AssessSeverityParams(assessed_severity=SeverityLevel.SEV2, justification="t"))))
        obs = env.reset("easy_single_service_outage", seed=1002)
        assert obs.step_number == 0 and obs.severity_level is None

    def test_invalid(self, env):
        with pytest.raises(ValueError): env.reset("bad")

class TestStep:
    def test_severity(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        r = env.step(Action(action_type=ActionType.ASSESS_SEVERITY, parameters=ActionParameters(assess_severity=AssessSeverityParams(assessed_severity=SeverityLevel.SEV2, justification="t"))))
        assert r.observation.current_phase == IncidentPhase.INVESTIGATION

    def test_logs(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        r = env.step(Action(action_type=ActionType.QUERY_LOGS, parameters=ActionParameters(query_logs=QueryLogsParams(service="order-service", time_range_minutes=30))))
        assert "logs" in r.info

    def test_rollback_ends(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        r = env.step(Action(action_type=ActionType.REMEDIATE_ROLLBACK, parameters=ActionParameters(remediate_rollback=RemediateRollbackParams(service="order-service", reason="t"))))
        assert r.done

    def test_max_steps(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        for _ in range(env.max_steps):
            if env.done: break
            env.step(Action(action_type=ActionType.QUERY_LOGS, parameters=ActionParameters(query_logs=QueryLogsParams(service="order-service", time_range_minutes=30))))
        assert env.done

class TestReward:
    def test_range(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        r = env.step(Action(action_type=ActionType.ASSESS_SEVERITY, parameters=ActionParameters(assess_severity=AssessSeverityParams(assessed_severity=SeverityLevel.SEV2, justification="t"))))
        assert -1.0 <= r.reward.score <= 1.0

    def test_repeat_penalty(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        a = Action(action_type=ActionType.QUERY_LOGS, parameters=ActionParameters(query_logs=QueryLogsParams(service="order-service", time_range_minutes=30)))
        r1 = env.step(a)
        r2 = env.step(a)
        assert r2.reward.score < r1.reward.score

class TestGrader:
    def test_range(self, env):
        for tid in TASKS:
            for seed in TASKS[tid].seeds[:2]:
                env.reset(tid, seed=seed)
                env.step(Action(action_type=ActionType.REMEDIATE_RESTART, parameters=ActionParameters(remediate_restart=RemediateRestartParams(service="order-service", reason="t"))))
                assert 0.0 <= env.grade() <= 1.0

    def test_deterministic(self, env):
        env.reset("easy_single_service_outage", seed=1001)
        env.step(Action(action_type=ActionType.REMEDIATE_ROLLBACK, parameters=ActionParameters(remediate_rollback=RemediateRollbackParams(service="order-service", reason="t"))))
        assert env.grade() == env.grade()

    def test_varying(self, env):
        scores = set()
        for tid in TASKS:
            for seed in TASKS[tid].seeds[:2]:
                env.reset(tid, seed=seed)
                env.step(Action(action_type=ActionType.REMEDIATE_RESTART, parameters=ActionParameters(remediate_restart=RemediateRestartParams(service="order-service", reason="t"))))
                scores.add(env.grade())
        assert len(scores) > 1

class TestTasks:
    def test_three(self):
        assert len(TASKS) >= 3
    def test_difficulties(self):
        d = {t["difficulty"] for t in list_tasks()}
        assert d >= {"easy", "medium", "hard"}