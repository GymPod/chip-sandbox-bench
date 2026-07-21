#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def mm1_metrics(arrival_rate: float, service_rate: float) -> dict:
    if arrival_rate < 0 or service_rate <= 0 or arrival_rate >= service_rate:
        raise ValueError("queue must be stable")
    rho = arrival_rate / service_rate
    system_time = 1 / (service_rate - arrival_rate)
    waiting_time = arrival_rate / (service_rate * (service_rate - arrival_rate))
    return {"utilization": rho, "jobs_system": arrival_rate * system_time,
            "jobs_waiting": arrival_rate * waiting_time, "system_time": system_time,
            "waiting_time": waiting_time}
PY
