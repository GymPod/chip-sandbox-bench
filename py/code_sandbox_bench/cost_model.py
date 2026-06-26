import os


def estimate_cost(provider: str, seconds: float, cpu: int, memory_gb: int, disk_gb: int) -> float:
    if provider in {"local", "docker"}:
        return 0.0
    if provider == "vercel":
        return (seconds / 3600.0) * ((cpu * 0.128) + (memory_gb * 0.0212)) + 0.60 / 1_000_000
    if provider == "modal":
        return seconds * ((cpu / 2.0) * 0.00003942 + memory_gb * 0.00000672)
    if provider == "daytona":
        billable_storage_gb = max(0, disk_gb - 5)
        return seconds * (cpu * 0.00001400 + memory_gb * 0.00000450 + billable_storage_gb * 0.00000003)
    if provider == "aws-microvm":
        vcpu_second_usd = env_float("AWS_MICROVM_ESTIMATE_VCPU_SECOND_USD", env_float("AWS_MICROVM_ESTIMATE_VCPU_HOUR_USD", 0) / 3600 or 0.0000276944)
        gb_second_usd = env_float("AWS_MICROVM_ESTIMATE_GB_SECOND_USD", env_float("AWS_MICROVM_ESTIMATE_GB_HOUR_USD", 0) / 3600 or 0.0000036667)
        return seconds * (aws_microvm_baseline_vcpu(memory_gb) * vcpu_second_usd + memory_gb * gb_second_usd)
    return 0.0


def aws_microvm_baseline_vcpu(memory_gb: int) -> float:
    return memory_gb / 2.0


def env_float(name: str, fallback: float) -> float:
    value = os.environ.get(name)
    return fallback if value is None else float(value)
