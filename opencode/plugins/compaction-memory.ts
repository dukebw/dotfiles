import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { Plugin } from "@opencode-ai/plugin";

const MAX_LINES = 220;
const MAX_CHARS = 12000;
const MEMORY_FILES = ["MEMORY.md", "TODO.md"] as const;

async function readText(path: string): Promise<string | null> {
  try {
    return await readFile(path, "utf8");
  } catch {
    return null;
  }
}

function truncate(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return "";
  }

  const originalLines = trimmed.split("\n");
  const lineLimited = originalLines.slice(0, MAX_LINES).join("\n");
  const charLimited = lineLimited.slice(0, MAX_CHARS);
  const truncated =
    originalLines.length > MAX_LINES || lineLimited.length > MAX_CHARS;

  return truncated
    ? `${charLimited}\n\n[Truncated by global compaction-memory plugin]`
    : charLimited;
}

export const CompactionMemoryPlugin: Plugin = async ({ directory, worktree }) => {
  const root = worktree || directory;

  return {
    "experimental.session.compacting": async (_input, output) => {
      const sections: string[] = [];

      for (const name of MEMORY_FILES) {
        const content = await readText(join(root, name));
        if (!content) {
          continue;
        }

        const truncated = truncate(content);
        if (!truncated) {
          continue;
        }

        sections.push(`### ${name}\n${truncated}`);
      }

      if (sections.length === 0) {
        return;
      }

      output.context.push(
        [
          "## Durable Worktree State",
          `Worktree root: ${root}`,
          "",
          ...sections,
          "",
          "Preserve hard constraints, decisions, and next steps exactly as written.",
          "Treat MEMORY.md and TODO.md as canonical project state.",
        ].join("\n"),
      );
    },
  };
};
