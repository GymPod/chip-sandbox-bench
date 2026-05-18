import { readFileSync } from "node:fs";
import type { BenchTask } from "./types";

export function loadTasks(path: string, taskIndex: string): BenchTask[] {
  const tasks = readFileSync(path, "utf8")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as BenchTask);
  if (taskIndex === "all") {
    return tasks;
  }
  return [tasks[Number.parseInt(taskIndex, 10)]];
}

