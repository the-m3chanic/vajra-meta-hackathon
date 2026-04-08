"""Typed Pydantic models for the Incident RCA OpenEnv."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────

class IncidentPhase(str, Enum):
    TRIAGE = "triage"
    INVESTIGATION = "investigation"
    DIAGNOSIS = "diagnosis"
    REMEDIATION = "remediation"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class SeverityLevel(str, Enum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class ActionType(str, Enum):
    ASSESS_SEVERITY = "assess_severity"
    QUERY_LOGS = "query_logs"
    QUERY_METRICS = "query_metrics"
    CHECK_DEPLOYMENTS = "check_deployments"
    CHECK_CONFIG_CHANGES = "check_config_changes"
    RUN_DIAGNOSTIC = "run_diagnostic"
    FORM_HYPOTHESIS = "form_hypothesis"
    TEST_HYPOTHESIS = "test_hypothesis"
    IDENTIFY_ROOT_CAUSE = "identify_root_cause"
    REMEDIATE_ROLLBACK = "remediate_rollback"
    REMEDIATE_SCALE = "remediate_scale"
    REMEDIATE_RESTART = "remediate_restart"
    REMEDIATE_CONFIG_FIX = "remediate_config_fix"
    REMEDIATE_HOTFIX = "remediate_hotfix"
    ESCALATE = "escalate"
    UPDATE_STATUS_PAGE = "update_status_page"


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class RootCauseCategory(str, Enum):
    BAD_DEPLOYMENT = "bad_deployment"
    CONFIG_CHANGE = "config_change"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    NETWORK_ISSUE = "network_issue"
    DATABASE_ISSUE = "database_issue"
    TRAFFIC_SPIKE = "traffic_spike"
    MEMORY_LEAK = "memory_leak"
    CERTIFICATE_EXPIRY = "certificate_expiry"
    DNS_FAILURE = "dns_failure"


class RemediationType(str, Enum):
    ROLLBACK = "rollback"
    SCALE_UP = "scale_up"
    RESTART = "restart"
    CONFIG_FIX = "config_fix"
    HOTFIX = "hotfix"
    ESCALATE = "escalate"


# ── Infrastructure Models ────────────────────────────────────────────────────

class ServiceNode(BaseModel):
    name: str
    service_type: str
    status: ServiceStatus = ServiceStatus.HEALTHY
    dependencies: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)
    current_cpu_percent: float = 0.0
    current_memory_percent: float = 0.0
    current_error_rate: float = 0.0
    current_latency_p99_ms: float = 0.0
    replica_count: int = 3
    last_deployment: Optional[str] = None
    last_config_change: Optional[str] = None


class MetricDataPoint(BaseModel):
    timestamp: str
    service: str
    metric_name: str
    value: float
    unit: str = ""


class LogEntry(BaseModel):
    timestamp: str
    service: str
    level: str
    message: str
    trace_id: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class DeploymentRecord(BaseModel):
    timestamp: str
    service: str
    version_from: str
    version_to: str
    deployer: str
    changelog: str
    status: str = "completed"


class ConfigChange(BaseModel):
    timestamp: str
    service: str
    parameter: str
    old_value: str
    new_value: str
    changed_by: str
    reason: str = ""


class DiagnosticResult(BaseModel):
    check_name: str
    service: str
    status: str
    message: str
    details: dict = Field(default_factory=dict)


# ── Alert Model ──────────────────────────────────────────────────────────────

class Alert(BaseModel):
    alert_id: str
    timestamp: str
    service: str
    metric: str
    condition: str
    current_value: str
    threshold: str
    severity_hint: str = "unknown"
    description: str = ""


# ── Action Parameter Models ──────────────────────────────────────────────────

class AssessSeverityParams(BaseModel):
    assessed_severity: SeverityLevel
    justification: str


class QueryLogsParams(BaseModel):
    service: str
    level_filter: Optional[str] = None
    time_range_minutes: int = Field(default=30, ge=1, le=180)
    search_pattern: Optional[str] = None


class QueryMetricsParams(BaseModel):
    service: str
    metric_name: str
    time_range_minutes: int = Field(default=60, ge=1, le=360)


class CheckDeploymentsParams(BaseModel):
    service: Optional[str] = None
    time_range_hours: int = Field(default=24, ge=1, le=168)


class CheckConfigChangesParams(BaseModel):
    service: Optional[str] = None
    time_range_hours: int = Field(default=24, ge=1, le=168)


class RunDiagnosticParams(BaseModel):
    service: str
    check_type: str


class FormHypothesisParams(BaseModel):
    hypothesis: str
    root_cause_category: RootCauseCategory
    suspected_service: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    supporting_evidence: list[str] = Field(default_factory=list)


class TestHypothesisParams(BaseModel):
    hypothesis_index: int
    test_action: str


class IdentifyRootCauseParams(BaseModel):
    root_cause_category: RootCauseCategory
    root_cause_service: str
    root_cause_description: str
    evidence_summary: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class RemediateRollbackParams(BaseModel):
    service: str
    target_version: Optional[str] = None
    reason: str


class RemediateScaleParams(BaseModel):
    service: str
    target_replicas: int = Field(ge=1, le=50)
    reason: str


class RemediateRestartParams(BaseModel):
    service: str
    reason: str


class RemediateConfigFixParams(BaseModel):
    service: str
    parameter: str
    new_value: str
    reason: str


class RemediateHotfixParams(BaseModel):
    service: str
    description: str
    reason: str


class EscalateParams(BaseModel):
    target_team: str
    reason: str
    summary: str


class UpdateStatusPageParams(BaseModel):
    status: str
    message: str


# ── Action Parameters Container ──────────────────────────────────────────────

class ActionParameters(BaseModel):
    assess_severity: Optional[AssessSeverityParams] = None
    query_logs: Optional[QueryLogsParams] = None
    query_metrics: Optional[QueryMetricsParams] = None
    check_deployments: Optional[CheckDeploymentsParams] = None
    check_config_changes: Optional[CheckConfigChangesParams] = None
    run_diagnostic: Optional[RunDiagnosticParams] = None
    form_hypothesis: Optional[FormHypothesisParams] = None
    test_hypothesis: Optional[TestHypothesisParams] = None
    identify_root_cause: Optional[IdentifyRootCauseParams] = None
    remediate_rollback: Optional[RemediateRollbackParams] = None
    remediate_scale: Optional[RemediateScaleParams] = None
    remediate_restart: Optional[RemediateRestartParams] = None
    remediate_config_fix: Optional[RemediateConfigFixParams] = None
    remediate_hotfix: Optional[RemediateHotfixParams] = None
    escalate: Optional[EscalateParams] = None
    update_status_page: Optional[UpdateStatusPageParams] = None


# ── Top-Level Action ─────────────────────────────────────────────────────────

class Action(BaseModel):
    action_type: ActionType
    parameters: ActionParameters = Field(default_factory=ActionParameters)


# ── Observation Model ────────────────────────────────────────────────────────

class TimelineEntry(BaseModel):
    step: int
    timestamp: str
    action_type: str
    summary: str
    reward: float


class HypothesisRecord(BaseModel):
    index: int
    hypothesis: str
    root_cause_category: str
    suspected_service: str
    confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)
    status: str = "active"


class Observation(BaseModel):
    alert: dict
    system_topology: dict
    queried_evidence: list[dict] = Field(default_factory=list)
    active_hypotheses: list[dict] = Field(default_factory=list)
    incident_timeline: list[dict] = Field(default_factory=list)
    current_phase: IncidentPhase
    affected_services: list[str] = Field(default_factory=list)
    severity_level: Optional[str] = None
    identified_root_cause: Optional[dict] = None
    remediation_applied: Optional[dict] = None
    step_number: int
    max_steps: int
    task_id: str
    task_description: str


# ── Reward Model ─────────────────────────────────────────────────────────────

class RewardBreakdown(BaseModel):
    triage_accuracy: float = 0.0
    investigation_quality: float = 0.0
    diagnosis_correctness: float = 0.0
    remediation_appropriateness: float = 0.0
    efficiency: float = 0.0
    penalty: float = 0.0


class Reward(BaseModel):
    score: float = Field(ge=-1.0, le=1.0)
    breakdown: RewardBreakdown = Field(default_factory=RewardBreakdown)
    message: str = ""


# ── State Model ──────────────────────────────────────────────────────────────

class EnvironmentState(BaseModel):
    task_id: str
    episode_id: str
    step_number: int
    max_steps: int
    current_phase: IncidentPhase
    severity_level: Optional[str] = None
    ground_truth_root_cause: dict
    ground_truth_severity: str
    ground_truth_remediation: str
    ground_truth_root_service: str
    identified_root_cause: Optional[dict] = None
    remediation_applied: Optional[dict] = None
    hypotheses: list[dict] = Field(default_factory=list)
    evidence_collected: list[dict] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    cumulative_reward: float = 0.0
    done: bool = False
    incident_timeline: list[dict] = Field(default_factory=list)


# ── Step Response ────────────────────────────────────────────────────────────

class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: dict = Field(default_factory=dict)