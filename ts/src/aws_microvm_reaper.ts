import { LambdaMicrovmsClient, ListMicrovmsCommand, TerminateMicrovmCommand } from "@aws-sdk/client-lambda-microvms";

type ReaperArgs = {
  region: string;
  imageIdentifier?: string;
  imageVersion?: string;
  maxSuspendedAgeSeconds: number;
  terminateRunning: boolean;
  execute: boolean;
};

type ListedMicrovm = {
  microvmId?: string;
  state?: string;
  imageArn?: string;
  imageVersion?: string;
  startedAt?: Date;
};

function parseArgs(argv: string[]): ReaperArgs {
  const values = new Map<string, string>();
  const flags = new Set<string>();
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "--execute" || item === "--terminate-running") {
      flags.add(item);
      continue;
    }
    values.set(item, argv[index + 1]);
    index += 1;
  }
  return {
    region: values.get("--region") ?? process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION ?? "us-east-1",
    imageIdentifier: values.get("--image-id") ?? values.get("--image-identifier") ?? process.env.AWS_MICROVM_IMAGE_ID,
    imageVersion: values.get("--image-version") ?? process.env.AWS_MICROVM_IMAGE_VERSION,
    maxSuspendedAgeSeconds: Number.parseInt(values.get("--max-suspended-age-seconds") ?? "25200", 10),
    terminateRunning: flags.has("--terminate-running"),
    execute: flags.has("--execute")
  };
}

async function listMicrovms(client: LambdaMicrovmsClient, args: ReaperArgs): Promise<ListedMicrovm[]> {
  const items: ListedMicrovm[] = [];
  let nextToken: string | undefined;
  do {
    const response = await client.send(
      new ListMicrovmsCommand({
        imageIdentifier: args.imageIdentifier,
        imageVersion: args.imageVersion,
        // The Lambda MicroVM API accepts at most 50 items per page.
        maxResults: 50,
        nextToken
      })
    );
    items.push(...(response.items ?? []));
    nextToken = response.nextToken;
  } while (nextToken);
  return items;
}

function shouldTerminate(item: ListedMicrovm, args: ReaperArgs, now: number): boolean {
  if (!item.microvmId) {
    return false;
  }
  if (item.state === "SUSPENDED") {
    const ageSeconds = item.startedAt ? (now - item.startedAt.getTime()) / 1000 : Number.POSITIVE_INFINITY;
    return ageSeconds >= args.maxSuspendedAgeSeconds;
  }
  return args.terminateRunning && item.state === "RUNNING";
}

async function main(): Promise<void> {
  const args = parseArgs(Bun.argv.slice(2));
  if (!args.imageIdentifier) {
    throw new Error("AWS MicroVM reaper requires --image-id or AWS_MICROVM_IMAGE_ID");
  }
  const client = new LambdaMicrovmsClient({ region: args.region });
  const now = Date.now();
  const items = await listMicrovms(client, args);
  const candidates = items.filter((item) => shouldTerminate(item, args, now));
  const terminated: string[] = [];
  if (args.execute) {
    for (const item of candidates) {
      if (!item.microvmId) {
        continue;
      }
      await client.send(new TerminateMicrovmCommand({ microvmIdentifier: item.microvmId }));
      terminated.push(item.microvmId);
    }
  }
  const summary = {
    region: args.region,
    image_identifier: args.imageIdentifier,
    image_version: args.imageVersion,
    dry_run: !args.execute,
    scanned: items.length,
    candidates: candidates.map((item) => ({
      microvmId: item.microvmId,
      state: item.state,
      startedAt: item.startedAt?.toISOString(),
      ageSeconds: item.startedAt ? (now - item.startedAt.getTime()) / 1000 : undefined
    })),
    terminated
  };
  console.log(JSON.stringify(summary, null, 2));
}

await main();
