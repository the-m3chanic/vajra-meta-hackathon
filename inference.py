#!/usr/bin/env python3
"""
Inference script for Incident RCA OpenEnv.
Uses OpenAI Client for all LLM calls.
Emits structured stdout logs: [START], [STEP], [END]
"""

import os
import sys
import re
import json
import time
import httpx
from dotenv import load_dotenv

load_dotenv(".env")

# ═══════════════════════════════════════════════════════════════════════════════
# REQUIRED ENV VARS (with defaults as required by hackathon spec)
# ═══════════════════════════════════════════════════════════════════════════════

API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
ENV_URL = os.getenv("ENV_URL", "https://the-m3chanic-vajra-meta-hackathon.hf.space")

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")

# ═══════════════════════════════════════════════════════════════════════════════
# OPENAI CLIENT (mandatory per hackathon spec)
# ═══════════════════════════════════════════════════════════════════════════════

from openai import OpenAI

client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

def call_env(endpoint, method="GET", data=None):
    url = f"{ENV_URL}{endpoint}"
    with httpx.Client(timeout=60) as h:
        if method == "POST":
            r = h.post(url, json=data)
        else:
            r = h.get(url)
        r.raise_for_status()
        return r.json()

# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURED LOGGING — EXACT FORMAT REQUIRED BY HACKATHON
# ═══════════════════════════════════════════════════════════════════════════════

def log_start(task_name, env_name, model_name):
    print(f"[START] task={task_name} env={env_name} model={model_name}")
    sys.stdout.flush()

def log_step(step_num, action_str, reward, done, error=None):
    done_str = "true" if done else "false"
    error_str = str(error) if error else "null"
    print(f"[STEP] step={step_num} action={action_str} reward={reward:.2f} done={done_str} error={error_str}")
    sys.stdout.flush()

def log_end(success, steps, rewards_list):
    success_str = "true" if success else "false"
    rewards_str = ",".join(f"{r:.2f}" for r in rewards_list)
    print(f"[END] success={success_str} steps={steps} rewards={rewards_str}")
    sys.stdout.flush()

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM = """You are an expert SRE AI responding to a production incident.

WORKFLOW: TRIAGE → INVESTIGATE → DIAGNOSE → REMEDIATE

Respond with ONLY a valid JSON object: {"action_type": "...", "parameters": {...}}

AVAILABLE ACTIONS:

TRIAGE:
- assess_severity: {"assessed_severity": "sev1|sev2|sev3|sev4", "justification": "..."}

INVESTIGATION:
- query_logs: {"service": "name", "level_filter": "ERROR", "time_range_minutes": 30}
- query_metrics: {"service": "name", "metric_name": "cpu_percent|memory_percent|latency_p99_ms|error_rate", "time_range_minutes": 60}
- check_deployments: {"service": null, "time_range_hours": 24}
- check_config_changes: {"service": null, "time_range_hours": 24}
- run_diagnostic: {"service": "name", "check_type": "connectivity|health|resources|dependencies|dns|certificates"}

DIAGNOSIS:
- identify_root_cause: {"root_cause_category": "bad_deployment|config_change|resource_exhaustion|dependency_failure|database_issue|memory_leak|certificate_expiry|dns_failure", "root_cause_service": "name", "root_cause_description": "...", "evidence_summary": ["..."], "confidence": 0.8}

REMEDIATION:
- remediate_rollback: {"service": "name", "reason": "..."}
- remediate_scale: {"service": "name", "target_replicas": 5, "reason": "..."}
- remediate_restart: {"service": "name", "reason": "..."}
- remediate_config_fix: {"service": "name", "parameter": "p", "new_value": "v", "reason": "..."}
- remediate_hotfix: {"service": "name", "description": "...", "reason": "..."}
- escalate: {"target_team": "platform|database|network", "reason": "...", "summary": "..."}

RULES:
- Don't remediate before diagnosing (penalty)
- Don't repeat same action (penalty)
- Trace dependencies upstream
- Check topology for unhealthy services
- Check both deployments AND config changes"""

# ═══════════════════════════════════════════════════════════════════════════════
# OBSERVATION FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_obs(obs, info=None):
    p = [f"Phase: {obs['current_phase']} | Step: {obs['step_number']}/{obs['max_steps']}"]
    a = obs.get("alert", {})
    p.append(f"ALERT: {a.get('service')} | {a.get('condition')} | val={a.get('current_value')} thresh={a.get('threshold')}")
    topo = obs.get("system_topology", {})
    bad = [f"{k}({v.get('status')})" for k, v in topo.items() if v.get("status") != "healthy"]
    p.append(f"UNHEALTHY: {', '.join(bad) if bad else 'none'}")
    p.append(f"Affected: {obs.get('affected_services', [])}")
    for e in obs.get("queried_evidence", [])[-5:]:
        p.append(f"  EV: {e.get('summary', '')}")
    if obs.get("identified_root_cause"):
        rc = obs["identified_root_cause"]
        p.append(f"RC: {rc.get('root_cause_category')} on {rc.get('root_cause_service')}")
    if info:
        if "logs" in info:
            for l in info["logs"][-5:]:
                p.append(f"  LOG: [{l.get('level')}] {l.get('message', '')[:100]}")
        if "deployments" in info:
            for d in info["deployments"]:
                p.append(f"  DEPLOY: {d.get('service')} {d.get('version_from')}>{d.get('version_to')} \"{d.get('changelog', '')}\"")
        if "config_changes" in info:
            for c in info["config_changes"]:
                p.append(f"  CONFIG: {c.get('service')} {c.get('parameter')} \"{c.get('old_value')}\"->\"{c.get('new_value')}\"")
        if "metrics" in info:
            ms = info["metrics"]
            if ms:
                p.append(f"  METRICS: {ms[0].get('metric_name')} on {ms[0].get('service')}: {ms[-1].get('value')}{ms[-1].get('unit', '')}")
        if "result" in info and isinstance(info["result"], dict):
            p.append(f"  DIAG: {info['result'].get('check_name')} > {info['result'].get('status')}: {info['result'].get('message', '')}")
    return "\n".join(p)

# ═══════════════════════════════════════════════════════════════════════════════
# FIX COMMON LLM MISTAKES
# ═══════════════════════════════════════════════════════════════════════════════

def fix_action(ad):
    if not ad or not isinstance(ad, dict):
        return None
    params = ad.get("parameters", {})
    if not isinstance(params, dict):
        params = {}
    at = ad.get("action_type", "")
    if not at:
        return None

    if "service_name" in params and "service" not in params:
        params["service"] = params.pop("service_name")

    if at == "assess_severity":
        if "severity" in params and "assessed_severity" not in params:
            params["assessed_severity"] = params.pop("severity")
        if "assessed_severity" not in params:
            params["assessed_severity"] = "sev2"
        if "justification" not in params:
            params["justification"] = "based on alert"
        val = params["assessed_severity"]
        if val not in ("sev1", "sev2", "sev3", "sev4"):
            params["assessed_severity"] = "sev2"

    needs_service = ["query_logs", "query_metrics", "run_diagnostic",
                     "remediate_rollback", "remediate_restart", "remediate_scale",
                     "remediate_config_fix", "remediate_hotfix"]
    if at in needs_service and "service" not in params:
        return None

    if at == "query_metrics" and "metric_name" not in params:
        params["metric_name"] = "error_rate"
    if at == "run_diagnostic" and "check_type" not in params:
        params["check_type"] = "health"
    if at == "remediate_rollback" and "reason" not in params:
        params["reason"] = "rolling back"
    if at == "remediate_restart" and "reason" not in params:
        params["reason"] = "restarting"
    if at == "remediate_scale":
        if "reason" not in params: params["reason"] = "scaling"
        if "target_replicas" not in params: params["target_replicas"] = 5
    if at == "remediate_config_fix":
        if "parameter" not in params: params["parameter"] = "unknown"
        if "new_value" not in params: params["new_value"] = "previous"
        if "reason" not in params: params["reason"] = "reverting"
    if at == "remediate_hotfix":
        if "description" not in params: params["description"] = "fix"
        if "reason" not in params: params["reason"] = "fixing"
    if at == "escalate":
        if "target_team" not in params: params["target_team"] = "platform"
        if "reason" not in params: params["reason"] = "escalating"
        if "summary" not in params: params["summary"] = "needs escalation"
    if at == "identify_root_cause":
        if "root_cause_service" not in params: return None
        if "root_cause_category" not in params: params["root_cause_category"] = "bad_deployment"
        if "root_cause_description" not in params: params["root_cause_description"] = "identified"
        if "evidence_summary" not in params: params["evidence_summary"] = []
        if "confidence" not in params: params["confidence"] = 0.7
        valid_cats = ["bad_deployment", "config_change", "resource_exhaustion",
                      "dependency_failure", "database_issue", "memory_leak",
                      "certificate_expiry", "dns_failure", "network_issue", "traffic_spike"]
        if params["root_cause_category"] not in valid_cats:
            params["root_cause_category"] = "bad_deployment"

    return {"action_type": at, "parameters": params}

def parse_llm_json(content):
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    m = re.search(r'''```(?:json)?\s*(.*?)```''', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    m = re.search(r'\{[^{}]*"action_type"[^{}]*\}', content)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None

def get_fallback_action(obs):
    phase = obs.get("current_phase", "triage")
    alert = obs.get("alert", {})
    svc = alert.get("service", "api-gateway")
    if phase == "triage":
        return {"action_type": "assess_severity",
                "parameters": {"assessed_severity": alert.get("severity_hint", "sev2"),
                               "justification": "based on alert"}}
    elif phase == "investigation":
        return {"action_type": "query_logs",
                "parameters": {"service": svc, "level_filter": "ERROR", "time_range_minutes": 30}}
    elif phase == "diagnosis":
        return {"action_type": "identify_root_cause",
                "parameters": {"root_cause_category": "bad_deployment", "root_cause_service": svc,
                               "root_cause_description": "suspected issue", "evidence_summary": [],
                               "confidence": 0.5}}
    else:
        return {"action_type": "remediate_restart",
                "parameters": {"service": svc, "reason": "fallback remediation"}}

# ═══════════════════════════════════════════════════════════════════════════════
# RUN EPISODE
# ═══════════════════════════════════════════════════════════════════════════════

def run_episode(task_id, seed, max_steps=20):
    env_name = "incident-rca"
    rewards_list = []
    step_count = 0
    success = False
    last_error = None

    log_start(task_id, env_name, MODEL_NAME)

    try:
        obs = call_env("/reset", "POST", {"task_id": task_id, "seed": seed})["observation"]
    except Exception as e:
        log_step(1, "reset_error", 0.0, True, str(e)[:100])
        log_end(False, 0, [])
        return 0.0

    msgs = [{"role": "system", "content": SYSTEM}]
    last_info = None

    for step in range(max_steps):
        txt = fmt_obs(obs, last_info) + "\n\nNext action? JSON only."
        msgs.append({"role": "user", "content": txt})

        action_data = None
        last_error = None

        try:
            kwargs = {"model": MODEL_NAME, "messages": msgs, "temperature": 0.0, "max_tokens": 500}
            try:
                kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**kwargs)
            except Exception:
                if "response_format" in kwargs:
                    del kwargs["response_format"]
                response = client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content
            action_data = parse_llm_json(content)

            if action_data and "action_type" not in action_data:
                action_data = None
            if action_data and "parameters" not in action_data:
                action_data["parameters"] = {}

        except Exception as e:
            last_error = str(e)[:100]
            action_data = get_fallback_action(obs)

        if not action_data:
            action_data = get_fallback_action(obs)

        msgs.append({"role": "assistant", "content": json.dumps(action_data)})

        sr = None
        action_str = action_data.get("action_type", "unknown")

        try:
            sr = call_env("/step", "POST", action_data)
        except Exception as e:
            fixed = fix_action(action_data)
            if fixed:
                try:
                    sr = call_env("/step", "POST", fixed)
                    action_str = fixed.get("action_type", action_str)
                except Exception as e2:
                    last_error = str(e2)[:100]
            else:
                last_error = str(e)[:100]

        if not sr:
            step_count += 1
            rewards_list.append(0.0)
            log_step(step_count, action_str, 0.0, False, last_error)
            continue

        step_count += 1
        obs = sr["observation"]
        last_info = sr.get("info", {})
        reward = sr["reward"]["score"]
        done = sr["done"]
        rewards_list.append(reward)

        log_step(step_count, action_str, reward, done, last_error)

        if done:
            break

    try:
        grade = call_env("/grader")
        score = grade["score"]
        success = score > 0.3
    except Exception:
        score = 0.0
        success = False

    log_end(success, step_count, rewards_list)
    return score

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

TASK_SEEDS = {
    "easy_single_service_outage": [1001, 1002, 1003],
    "medium_cascading_failure": [2001, 2002, 2003],
    "hard_subtle_degradation": [3001, 3002, 3003],
}

def main():
    try:
        info = call_env("/")
    except Exception as e:
        print(f"[END] success=false steps=0 rewards=")
        sys.exit(1)

    try:
        test = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        llm_ok = True
    except Exception:
        llm_ok = False

    tasks = call_env("/tasks")["tasks"]

    for task in tasks:
        task_id = task["id"]
        seeds = TASK_SEEDS.get(task_id, [1001, 1002, 1003])
        max_steps = task["max_steps"]

        for seed in seeds:
            run_episode(task_id, seed, max_steps)

if __name__ == "__main__":
    main()
