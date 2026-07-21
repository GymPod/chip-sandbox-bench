import { v } from "convex/values";
import { query } from "./_generated/server";

export const list = query({
  args: {},
  handler: async (ctx) => {
    const [tasks, files] = await Promise.all([
      ctx.db.query("tasks").withIndex("by_task_id").collect(),
      ctx.db.query("taskFiles").collect(),
    ]);
    const filesByTask = new Map<string, typeof files>();

    for (const file of files) {
      const taskFiles = filesByTask.get(file.taskId) ?? [];
      taskFiles.push(file);
      filesByTask.set(file.taskId, taskFiles);
    }

    return tasks.map(({ _id, _creationTime, taskId, ...task }) => ({
      ...task,
      task_id: taskId,
      files: (filesByTask.get(taskId) ?? [])
        .sort((a, b) => a.path.localeCompare(b.path))
        .map(({ _id: fileId, _creationTime: createdAt, content, taskId: owner, ...file }) => file),
      file_count: filesByTask.get(taskId)?.length ?? 0,
    }));
  },
});

export const readFile = query({
  args: {
    taskId: v.string(),
    path: v.string(),
  },
  handler: async (ctx, args) => {
    const file = await ctx.db
      .query("taskFiles")
      .withIndex("by_task_and_path", (q) => q.eq("taskId", args.taskId).eq("path", args.path))
      .unique();
    return file ? { path: file.path, content: file.content } : null;
  },
});
