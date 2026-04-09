"""Simulated microservices infrastructure."""

from __future__ import annotations
import random
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from server.environment.models import ServiceNode, ServiceStatus


BASE_TOPOLOGY = {
    "api-gateway": {
        "service_type": "gateway",
        "dependencies": ["user-service", "order-service", "product-service"],
        "base_cpu": 25.0, "base_memory": 40.0, "base_latency": 50.0,
        "base_error_rate": 0.001, "replicas": 4,
    },
    "user-service": {
        "service_type": "api",
        "dependencies": ["user-db", "cache-redis", "auth-service"],
        "base_cpu": 30.0, "base_memory": 45.0, "base_latency": 30.0,
        "base_error_rate": 0.002, "replicas": 3,
    },
    "order-service": {
        "service_type": "api",
        "dependencies": ["order-db", "payment-service", "notification-service", "product-service"],
        "base_cpu": 35.0, "base_memory": 50.0, "base_latency": 80.0,
        "base_error_rate": 0.003, "replicas": 3,
    },
    "product-service": {
        "service_type": "api",
        "dependencies": ["product-db", "cache-redis", "search-service"],
        "base_cpu": 20.0, "base_memory": 35.0, "base_latency": 25.0,
        "base_error_rate": 0.001, "replicas": 3,
    },
    "payment-service": {
        "service_type": "api",
        "dependencies": ["payment-db", "payment-gateway-ext"],
        "base_cpu": 15.0, "base_memory": 30.0, "base_latency": 200.0,
        "base_error_rate": 0.005, "replicas": 2,
    },
    "notification-service": {
        "service_type": "worker",
        "dependencies": ["queue-rabbitmq", "email-provider-ext"],
        "base_cpu": 10.0, "base_memory": 25.0, "base_latency": 15.0,
        "base_error_rate": 0.002, "replicas": 2,
    },
    "auth-service": {
        "service_type": "api",
        "dependencies": ["user-db", "cache-redis"],
        "base_cpu": 12.0, "base_memory": 20.0, "base_latency": 20.0,
        "base_error_rate": 0.001, "replicas": 2,
    },
    "search-service": {
        "service_type": "api",
        "dependencies": ["elasticsearch"],
        "base_cpu": 40.0, "base_memory": 60.0, "base_latency": 45.0,
        "base_error_rate": 0.002, "replicas": 2,
    },
    "user-db": {
        "service_type": "database",
        "dependencies": [],
        "base_cpu": 20.0, "base_memory": 65.0, "base_latency": 5.0,
        "base_error_rate": 0.0001, "replicas": 1,
    },
    "order-db": {
        "service_type": "database",
        "dependencies": [],
        "base_cpu": 25.0, "base_memory": 70.0, "base_latency": 8.0,
        "base_error_rate": 0.0001, "replicas": 1,
    },
    "product-db": {
        "service_type": "database",
        "dependencies": [],
        "base_cpu": 18.0, "base_memory": 55.0, "base_latency": 4.0,
        "base_error_rate": 0.0001, "replicas": 1,
    },
    "payment-db": {
        "service_type": "database",
        "dependencies": [],
        "base_cpu": 15.0, "base_memory": 50.0, "base_latency": 3.0,
        "base_error_rate": 0.0001, "replicas": 1,
    },
    "cache-redis": {
        "service_type": "cache",
        "dependencies": [],
        "base_cpu": 8.0, "base_memory": 75.0, "base_latency": 1.0,
        "base_error_rate": 0.0001, "replicas": 1,
    },
    "queue-rabbitmq": {
        "service_type": "queue",
        "dependencies": [],
        "base_cpu": 12.0, "base_memory": 40.0, "base_latency": 2.0,
        "base_error_rate": 0.0001, "replicas": 1,
    },
    "elasticsearch": {
        "service_type": "database",
        "dependencies": [],
        "base_cpu": 45.0, "base_memory": 70.0, "base_latency": 15.0,
        "base_error_rate": 0.001, "replicas": 1,
    },
    "payment-gateway-ext": {
        "service_type": "external",
        "dependencies": [],
        "base_cpu": 0.0, "base_memory": 0.0, "base_latency": 300.0,
        "base_error_rate": 0.01, "replicas": 1,
    },
    "email-provider-ext": {
        "service_type": "external",
        "dependencies": [],
        "base_cpu": 0.0, "base_memory": 0.0, "base_latency": 500.0,
        "base_error_rate": 0.02, "replicas": 1,
    },
}

DEPLOYMENT_CHANGELOGS = [
    "Updated request validation logic",
    "Added new API endpoint for bulk operations",
    "Refactored database connection pooling",
    "Updated dependency versions (security patches)",
    "Added retry logic for external calls",
    "Optimized query performance with new indexes",
    "Added new caching layer for hot paths",
    "Migrated to async request handling",
    "Updated TLS certificates",
    "Added rate limiting middleware",
    "Fixed memory leak in session handler",
    "Updated regex patterns for input validation",
    "Changed connection timeout from 30s to 5s",
    "Added circuit breaker for downstream calls",
    "Refactored logging to structured format",
]

ERROR_MESSAGES = {
    "bad_deployment": [
        "NullPointerException in RequestHandler.process()",
        "TypeError: Cannot read property 'id' of undefined",
        "FATAL: unhandled exception in worker thread",
        "panic: runtime error: index out of range [5] with length 3",
        "Error: ECONNREFUSED - connection refused to downstream service",
    ],
    "config_change": [
        "Connection pool exhausted: max_connections=5 reached",
        "Timeout waiting for available connection from pool (5000ms)",
        "WARN: connection timeout reduced, seeing elevated timeouts",
        "Rate limit exceeded: max_requests_per_second=10",
        "ERROR: invalid configuration value for max_retries: -1",
    ],
    "resource_exhaustion": [
        "OOMKilled: container exceeded memory limit (2Gi)",
        "WARN: JVM heap usage at 95%, GC thrashing detected",
        "ERROR: disk space below 5% threshold on /data volume",
        "CPU throttling detected: 89% of CPU quota consumed",
        "WARN: file descriptor limit approaching (95% of 65536)",
    ],
    "dependency_failure": [
        "Connection refused: downstream service {} not responding",
        "Circuit breaker OPEN for service {}: 10 consecutive failures",
        "Timeout after 5000ms waiting for response from {}",
        "DNS resolution failed for {}.internal.svc.cluster.local",
        "TLS handshake failed: certificate expired for {}",
    ],
    "database_issue": [
        "FATAL: too many connections for role 'app_user'",
        "ERROR: deadlock detected in transaction",
        "WARN: slow query detected (>5000ms): SELECT * FROM orders WHERE...",
        "ERROR: replication lag exceeded 30 seconds",
        "FATAL: database disk full, cannot write WAL",
    ],
    "memory_leak": [
        "WARN: heap usage growing steadily: 60% -> 75% -> 88% over 2h",
        "GC pause exceeded 500ms, old gen at 92%",
        "WARN: resident memory 1.8Gi and climbing (limit: 2Gi)",
        "Possible memory leak: object count growing 500/min",
        "WARN: connection objects not being released, count: 4523",
    ],
}

NORMAL_LOG_MESSAGES = [
    "Request processed successfully in {}ms",
    "Health check passed",
    "Cache hit for key: user:{}",
    "Cache miss for key: product:{}",
    "Database query completed in {}ms",
    "Scheduled job completed: cleanup_expired_sessions",
    "New connection established from {}",
    "Request rate: {} req/s (within limits)",
    "Deployment health check passed (attempt 1/3)",
    "Configuration reload completed",
]


class InfrastructureSimulator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.base_time = datetime(2024, 1, 15, 14, 30, 0)
        self.services: dict[str, ServiceNode] = {}
        self._build_topology()

    def _build_topology(self):
        for name, config in BASE_TOPOLOGY.items():
            dependents = []
            for other_name, other_config in BASE_TOPOLOGY.items():
                if name in other_config["dependencies"]:
                    dependents.append(other_name)
            self.services[name] = ServiceNode(
                name=name,
                service_type=config["service_type"],
                status=ServiceStatus.HEALTHY,
                dependencies=config["dependencies"],
                dependents=dependents,
                current_cpu_percent=config["base_cpu"] + self.rng.gauss(0, 3),
                current_memory_percent=config["base_memory"] + self.rng.gauss(0, 2),
                current_error_rate=config["base_error_rate"],
                current_latency_p99_ms=config["base_latency"] + self.rng.gauss(0, 5),
                replica_count=config["replicas"],
            )

    def get_topology_dict(self) -> dict:
        result = {}
        for name, svc in self.services.items():
            result[name] = {
                "name": svc.name,
                "service_type": svc.service_type,
                "status": svc.status.value,
                "dependencies": svc.dependencies,
                "dependents": svc.dependents,
                "replica_count": svc.replica_count,
            }
        return result

    def apply_incident_effects(self, root_cause_service: str, root_cause_category: str,
                                affected_services: list[str], severity: str):
        mult = {"sev1": 4.0, "sev2": 2.5, "sev3": 1.5, "sev4": 1.1}.get(severity, 1.5)
        if root_cause_service in self.services:
            svc = self.services[root_cause_service]
            svc.status = ServiceStatus.DOWN if severity in ("sev1", "sev2") else ServiceStatus.DEGRADED
            base = BASE_TOPOLOGY.get(root_cause_service, {})
            if root_cause_category in ("bad_deployment", "memory_leak"):
                svc.current_cpu_percent = min(98, base.get("base_cpu", 30) * mult)
                svc.current_memory_percent = min(97, base.get("base_memory", 50) * 1.8)
                svc.current_error_rate = min(0.5, base.get("base_error_rate", 0.01) * mult * 20)
            elif root_cause_category == "config_change":
                svc.current_latency_p99_ms = base.get("base_latency", 50) * mult * 3
                svc.current_error_rate = min(0.3, base.get("base_error_rate", 0.01) * mult * 10)
            elif root_cause_category == "resource_exhaustion":
                svc.current_cpu_percent = min(99, 92 + self.rng.gauss(0, 2))
                svc.current_memory_percent = min(99, 95 + self.rng.gauss(0, 1))
            elif root_cause_category == "database_issue":
                svc.current_latency_p99_ms = base.get("base_latency", 50) * mult * 5
                svc.current_cpu_percent = min(95, base.get("base_cpu", 30) * 2.5)
            else:
                svc.current_error_rate = min(0.4, base.get("base_error_rate", 0.01) * mult * 15)
                svc.current_latency_p99_ms = base.get("base_latency", 50) * mult * 2

        for aff_name in affected_services:
            if aff_name in self.services and aff_name != root_cause_service:
                aff = self.services[aff_name]
                aff.status = ServiceStatus.DEGRADED
                base_aff = BASE_TOPOLOGY.get(aff_name, {})
                cf = mult * 0.6
                aff.current_latency_p99_ms = base_aff.get("base_latency", 50) * cf * 2
                aff.current_error_rate = min(0.2, base_aff.get("base_error_rate", 0.01) * cf * 8)
                aff.current_cpu_percent = min(85, base_aff.get("base_cpu", 30) * cf * 0.8)

    def generate_logs(self, service: str, root_cause_service: str, root_cause_category: str,
                      level_filter: Optional[str] = None, time_range_minutes: int = 30,
                      search_pattern: Optional[str] = None, is_affected: bool = False) -> list[dict]:
        logs = []
        now = self.base_time
        start = now - timedelta(minutes=time_range_minutes)
        num_entries = self.rng.randint(8, 20)

        for i in range(num_entries):
            ts = start + timedelta(minutes=self.rng.uniform(0, time_range_minutes))
            ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{self.rng.randint(0,999):03d}Z"
            trace_id = hashlib.md5(f"{service}-{i}-{self.rng.random()}".encode()).hexdigest()[:16]

            if service == root_cause_service:
                if i < 3:
                    msg = self.rng.choice(NORMAL_LOG_MESSAGES).format(self.rng.randint(5, 50))
                    level = "INFO"
                else:
                    error_msgs = ERROR_MESSAGES.get(root_cause_category, ERROR_MESSAGES["bad_deployment"])
                    if self.rng.random() < 0.6:
                        msg = self.rng.choice(error_msgs)
                        if "{}" in msg:
                            deps = BASE_TOPOLOGY.get(service, {}).get("dependencies", ["unknown"])
                            msg = msg.format(self.rng.choice(deps) if deps else "unknown")
                        level = self.rng.choice(["ERROR", "FATAL", "ERROR"])
                    else:
                        msg = self.rng.choice(NORMAL_LOG_MESSAGES).format(self.rng.randint(100, 5000))
                        level = "WARN"
            elif is_affected:
                if i > num_entries // 2:
                    dep_msgs = ERROR_MESSAGES.get("dependency_failure", [])
                    msg = self.rng.choice(dep_msgs).format(root_cause_service)
                    level = "ERROR" if self.rng.random() < 0.5 else "WARN"
                else:
                    msg = self.rng.choice(NORMAL_LOG_MESSAGES).format(self.rng.randint(5, 200))
                    level = "INFO"
            else:
                msg = self.rng.choice(NORMAL_LOG_MESSAGES).format(self.rng.randint(5, 100))
                level = self.rng.choice(["INFO", "INFO", "INFO", "DEBUG"])

            if level_filter and level != level_filter:
                continue
            if search_pattern and search_pattern.lower() not in msg.lower():
                continue

            logs.append({"timestamp": ts_str, "service": service, "level": level,
                        "message": msg, "trace_id": trace_id})

        logs.sort(key=lambda x: x["timestamp"])
        return logs

    def generate_metrics(self, service: str, metric_name: str, root_cause_service: str,
                         incident_start_offset_min: int, time_range_minutes: int = 60) -> list[dict]:
        points = []
        now = self.base_time
        interval_min = max(1, time_range_minutes // 20)
        svc = self.services.get(service)
        base = BASE_TOPOLOGY.get(service, {})
        base_values = {
            "cpu_percent": base.get("base_cpu", 30.0),
            "memory_percent": base.get("base_memory", 50.0),
            "latency_p99_ms": base.get("base_latency", 50.0),
            "error_rate": base.get("base_error_rate", 0.01),
            "request_rate": 500.0 + self.rng.gauss(0, 50),
        }
        base_val = base_values.get(metric_name, 50.0)
        current_val = getattr(svc, f"current_{metric_name}", base_val) if svc else base_val
        units = {"cpu_percent": "%", "memory_percent": "%", "latency_p99_ms": "ms",
                 "error_rate": "ratio", "request_rate": "req/s"}

        for i in range(0, time_range_minutes, interval_min):
            ts = now - timedelta(minutes=time_range_minutes - i)
            ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            minutes_before = time_range_minutes - i - incident_start_offset_min
            if minutes_before > 0:
                value = base_val + self.rng.gauss(0, base_val * 0.05)
            else:
                progress = min(0.999, abs(minutes_before) / 10.0)
                value = base_val + (current_val - base_val) * progress
                value += self.rng.gauss(0, abs(current_val - base_val) * 0.1)
            value = max(0, value)
            if metric_name in ("cpu_percent", "memory_percent"):
                value = min(100, value)
            points.append({"timestamp": ts_str, "service": service, "metric_name": metric_name,
                          "value": round(value, 2), "unit": units.get(metric_name, "")})
        return points

    def generate_deployments(self, service: Optional[str], root_cause_service: str,
                              root_cause_category: str, bad_deployment_changelog: str,
                              time_range_hours: int = 24) -> list[dict]:
        records = []
        now = self.base_time
        services_to_check = [service] if service else list(self.services.keys())

        for svc_name in services_to_check:
            if svc_name.endswith("-ext"):
                continue
            svc_type = BASE_TOPOLOGY.get(svc_name, {}).get("service_type", "api")
            if svc_type in ("database", "cache", "queue", "external"):
                continue

            if (svc_name == root_cause_service and root_cause_category == "bad_deployment"
                    and bad_deployment_changelog):
                t = now - timedelta(minutes=self.rng.randint(30, 120))
                records.append({
                    "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "service": svc_name,
                    "version_from": f"v2.{self.rng.randint(10,20)}.{self.rng.randint(0,9)}",
                    "version_to": f"v2.{self.rng.randint(21,30)}.0",
                    "deployer": self.rng.choice(["alice@co.com", "bob@co.com", "deploy-bot"]),
                    "changelog": bad_deployment_changelog,
                    "status": "completed",
                })

            num = self.rng.randint(0, 2)
            for _ in range(num):
                t = now - timedelta(hours=self.rng.uniform(2, time_range_hours))
                records.append({
                    "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "service": svc_name,
                    "version_from": f"v2.{self.rng.randint(1,10)}.{self.rng.randint(0,9)}",
                    "version_to": f"v2.{self.rng.randint(1,10)}.{self.rng.randint(0,9)}",
                    "deployer": self.rng.choice(["alice@co.com", "carol@co.com", "deploy-bot"]),
                    "changelog": self.rng.choice(DEPLOYMENT_CHANGELOGS),
                    "status": "completed",
                })

        records.sort(key=lambda x: x["timestamp"], reverse=True)
        return records

    def generate_config_changes(self, service: Optional[str], root_cause_service: str,
                                 root_cause_category: str, bad_config: Optional[dict],
                                 time_range_hours: int = 24) -> list[dict]:
        records = []
        now = self.base_time
        services_to_check = [service] if service else list(self.services.keys())

        for svc_name in services_to_check:
            if svc_name.endswith("-ext"):
                continue
            if (svc_name == root_cause_service and root_cause_category == "config_change"
                    and bad_config):
                t = now - timedelta(minutes=self.rng.randint(20, 90))
                records.append({
                    "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "service": svc_name,
                    "parameter": bad_config["parameter"],
                    "old_value": bad_config["old_value"],
                    "new_value": bad_config["new_value"],
                    "changed_by": self.rng.choice(["ops-team", "platform-bot", "dave@co.com"]),
                    "reason": bad_config.get("reason", "performance tuning"),
                })

            if self.rng.random() < 0.3:
                cfgs = [
                    {"param": "log_level", "old": "INFO", "new": "DEBUG"},
                    {"param": "feature_flag.new_ui", "old": "false", "new": "true"},
                    {"param": "metrics.sample_rate", "old": "0.1", "new": "0.5"},
                ]
                cfg = self.rng.choice(cfgs)
                t = now - timedelta(hours=self.rng.uniform(1, time_range_hours))
                records.append({
                    "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "service": svc_name,
                    "parameter": cfg["param"], "old_value": cfg["old"],
                    "new_value": cfg["new"], "changed_by": "config-bot",
                    "reason": "scheduled change",
                })

        records.sort(key=lambda x: x["timestamp"], reverse=True)
        return records

    def run_diagnostic(self, service: str, check_type: str, root_cause_service: str,
                       root_cause_category: str) -> dict:
        svc = self.services.get(service)
        if not svc:
            return {"check_name": check_type, "service": service, "status": "fail",
                    "message": f"Service '{service}' not found", "details": {}}

        is_root = (service == root_cause_service)

        if check_type == "connectivity":
            if is_root and root_cause_category in ("dependency_failure", "network_issue"):
                return {"check_name": "connectivity", "service": service, "status": "fail",
                        "message": f"Cannot reach {self.rng.choice(svc.dependencies) if svc.dependencies else 'downstream'}",
                        "details": {"unreachable_deps": svc.dependencies[:2]}}
            return {"check_name": "connectivity", "service": service, "status": "pass",
                    "message": "All connections healthy", "details": {"connected_deps": svc.dependencies}}

        elif check_type == "health":
            if svc.status in (ServiceStatus.DOWN, ServiceStatus.DEGRADED):
                return {"check_name": "health", "service": service,
                        "status": "fail" if svc.status == ServiceStatus.DOWN else "warn",
                        "message": f"Service {svc.status.value}. Error rate: {svc.current_error_rate:.3f}",
                        "details": {"status": svc.status.value, "error_rate": svc.current_error_rate,
                                   "latency_p99": svc.current_latency_p99_ms}}
            return {"check_name": "health", "service": service, "status": "pass",
                    "message": "Healthy", "details": {"status": svc.status.value}}

        elif check_type == "resources":
            if is_root and root_cause_category in ("resource_exhaustion", "memory_leak"):
                return {"check_name": "resources", "service": service, "status": "fail",
                        "message": f"CPU: {svc.current_cpu_percent:.1f}%, Memory: {svc.current_memory_percent:.1f}%",
                        "details": {"cpu_percent": svc.current_cpu_percent,
                                   "memory_percent": svc.current_memory_percent,
                                   "cpu_critical": svc.current_cpu_percent > 90,
                                   "memory_critical": svc.current_memory_percent > 90}}
            return {"check_name": "resources", "service": service, "status": "pass",
                    "message": f"CPU: {svc.current_cpu_percent:.1f}%, Memory: {svc.current_memory_percent:.1f}%",
                    "details": {"cpu_percent": round(svc.current_cpu_percent, 1),
                               "memory_percent": round(svc.current_memory_percent, 1)}}

        elif check_type == "dependencies":
            failed = [d for d in svc.dependencies
                     if self.services.get(d, ServiceNode(name=d, service_type="")).status != ServiceStatus.HEALTHY]
            if failed:
                return {"check_name": "dependencies", "service": service, "status": "fail",
                        "message": f"Unhealthy: {', '.join(failed)}",
                        "details": {"failed_deps": failed, "all_deps": svc.dependencies}}
            return {"check_name": "dependencies", "service": service, "status": "pass",
                    "message": "All deps healthy", "details": {"all_deps": svc.dependencies}}

        elif check_type == "dns":
            if is_root and root_cause_category == "dns_failure":
                return {"check_name": "dns", "service": service, "status": "fail",
                        "message": f"DNS failing for {service}.internal.svc.cluster.local",
                        "details": {"resolution_time_ms": "timeout"}}
            return {"check_name": "dns", "service": service, "status": "pass",
                    "message": "DNS healthy", "details": {"resolution_time_ms": self.rng.randint(1, 5)}}

        elif check_type == "certificates":
            if is_root and root_cause_category == "certificate_expiry":
                return {"check_name": "certificates", "service": service, "status": "fail",
                        "message": "TLS certificate expired 2 hours ago",
                        "details": {"expiry": "2024-01-15T12:30:00Z"}}
            return {"check_name": "certificates", "service": service, "status": "pass",
                    "message": "Certs valid", "details": {"days_remaining": 182}}

        return {"check_name": check_type, "service": service, "status": "warn",
                "message": f"Unknown check: {check_type}", "details": {}}