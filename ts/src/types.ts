export type BenchTask = {
  task_id: string;
  prompt: string;
  instruction: string;
  task_files: {
    encoding: string;
    content: string;
  };
  data_source?: string;
  env_type?: string;
};

export type CommandResult = {
  stdout: string;
  stderr: string;
  returnCode: number;
  usage?: CommandUsage;
};

export type CommandUsage = {
  wall_seconds?: number;
  user_cpu_seconds?: number;
  system_cpu_seconds?: number;
  peak_rss_kb?: number;
  stdout_bytes?: number;
  stderr_bytes?: number;
  timed_out?: boolean;
  signal?: string;
};

export type ProviderRunTrace = {
  label?: string;
};

export type Provider = {
  start(): Promise<void>;
  run(command: string, cwd: string | undefined, timeoutSeconds: number, trace?: ProviderRunTrace): Promise<CommandResult>;
  stop(): Promise<void>;
  metadata?(): Record<string, unknown>;
};

export type ProviderName = "local" | "vercel" | "modal" | "daytona" | "aws-microvm";
export type RunMode = "cold" | "warm";
export type RunKind = "verifier" | "solve";
export type ResourcePolicyName = "static" | "observe" | "adaptive";

export type TaskEnv = {
  envType: string;
  dataSource?: string;
  workdir: string;
  verifierCwd: string;
  runtime?: string;
  dockerImage?: string;
  dockerfileCommands?: string[];
  dockerfilePath?: string;
  repoKey?: string;
  sourceId?: string;
  manifest?: import("./env_manifest").EnvManifestEntry;
  resources?: import("./env_manifest").RepoResources;
};

export type BenchArgs = {
  provider: ProviderName;
  mode: RunMode;
  dataset: string;
  taskIndex: string;
  taskLimit?: number;
  runtime: string;
  timeoutSeconds: number;
  solveTimeoutSeconds: number;
  solveCommand?: string;
  solveCommandFile?: string;
  forwardEnv: string[];
  prewarmProfile?: string;
  vercelSnapshotId?: string;
  modalImageId?: string;
  daytonaSnapshot?: string;
  awsMicrovmImageId?: string;
  awsMicrovmImageVersion?: string;
  awsMicrovmExecutionRoleArn?: string;
  concurrency: number;
  cpu: number;
  memoryGb: number;
  diskGb: number;
  resourcePolicy: ResourcePolicyName;
  resourceConfigPath?: string;
  resourceObservationsOutput?: string;
  output?: string;
};
