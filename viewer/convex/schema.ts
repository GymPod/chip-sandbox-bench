import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  tasks: defineTable({
    taskId: v.string(),
    discipline: v.string(),
    benchmark: v.string(),
    tools: v.array(v.string()),
    source: v.object({
      repo: v.string(),
      commit: v.string(),
      paths: v.array(v.string()),
    }),
    prompt: v.string(),
    instruction: v.string(),
  }).index("by_task_id", ["taskId"]),
  taskFiles: defineTable({
    taskId: v.string(),
    path: v.string(),
    name: v.string(),
    group: v.string(),
    size: v.number(),
    language: v.string(),
    content: v.string(),
  })
    .index("by_task_id", ["taskId"])
    .index("by_task_and_path", ["taskId", "path"]),
});
