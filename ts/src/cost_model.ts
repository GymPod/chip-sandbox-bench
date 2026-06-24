export function estimateCost(provider: string, seconds: number, cpu: number, memoryGb: number, diskGb: number): number {
  if (provider === "vercel") {
    return (seconds / 3600) * (cpu * 0.128 + memoryGb * 0.0212) + 0.60 / 1_000_000;
  }
  if (provider === "modal") {
    return seconds * ((cpu / 2) * 0.00003942 + memoryGb * 0.00000672);
  }
  if (provider === "daytona") {
    const billableStorageGb = Math.max(0, diskGb - 5);
    return seconds * (cpu * 0.000014 + memoryGb * 0.0000045 + billableStorageGb * 0.00000003);
  }
  if (provider === "aws-microvm") {
    const vcpuSecond = envNumber(
      "AWS_MICROVM_ESTIMATE_VCPU_SECOND_USD",
      envNumber("AWS_MICROVM_ESTIMATE_VCPU_HOUR_USD", 0) / 3600 || 0.0000276944
    );
    const gbSecond = envNumber(
      "AWS_MICROVM_ESTIMATE_GB_SECOND_USD",
      envNumber("AWS_MICROVM_ESTIMATE_GB_HOUR_USD", 0) / 3600 || 0.0000036667
    );
    return seconds * (awsMicrovmBaselineVcpu(memoryGb) * vcpuSecond + memoryGb * gbSecond);
  }
  return 0;
}

export function awsMicrovmBaselineVcpu(memoryGb: number): number {
  return memoryGb / 2;
}

function envNumber(name: string, fallback: number): number {
  const value = process.env[name];
  return value === undefined ? fallback : Number.parseFloat(value);
}
