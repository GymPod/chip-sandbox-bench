import { gunzipSync } from "node:zlib";
import type { BenchTask, ProviderName, TaskEnv } from "./types";

export function resolveTaskEnv(task: BenchTask, defaultRuntime: string, provider: ProviderName): TaskEnv {
  if (task.env_type === "harbor_swesmith") {
    const dockerfile = readArchiveText(task, "environment/Dockerfile");
    const dockerImage = dockerfile ? parseDockerfileFrom(dockerfile) : undefined;
    return {
      envType: task.env_type,
      dataSource: task.data_source,
      workdir: "/testbed",
      verifierCwd: "/testbed",
      runtime: providerSupportsDockerRuntime(provider) ? dockerImage : defaultRuntime,
      dockerImage,
      dockerfilePath: dockerfile ? "environment/Dockerfile" : undefined
    };
  }
  return {
    envType: task.env_type ?? "terminalbench",
    dataSource: task.data_source,
    workdir: "/workspace",
    verifierCwd: "/workspace",
    runtime: defaultRuntime
  };
}

export function providerSupportsDockerRuntime(provider: ProviderName): boolean {
  return provider === "modal" || provider === "daytona";
}

function parseDockerfileFrom(dockerfile: string): string | undefined {
  return dockerfile
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("FROM "))
    ?.split(/\s+/)[1];
}

function readArchiveText(task: BenchTask, path: string): string | undefined {
  if (task.task_files.encoding !== "tar.gz+base64") {
    return undefined;
  }
  const tar = gunzipSync(Buffer.from(task.task_files.content, "base64"));
  for (let offset = 0; offset + 512 <= tar.length; offset += 512) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) {
      return undefined;
    }
    const name = header.subarray(0, 100).toString("utf8").replace(/\0.*$/, "");
    const prefix = header.subarray(345, 500).toString("utf8").replace(/\0.*$/, "");
    const fullName = prefix ? `${prefix}/${name}` : name;
    const sizeText = header.subarray(124, 136).toString("utf8").replace(/\0.*$/, "").trim();
    const size = Number.parseInt(sizeText || "0", 8);
    const fileStart = offset + 512;
    const fileEnd = fileStart + size;
    if (fullName === path) {
      return tar.subarray(fileStart, fileEnd).toString("utf8");
    }
    offset += Math.ceil(size / 512) * 512;
  }
  return undefined;
}
