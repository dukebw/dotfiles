#!/usr/bin/env node

import { createOpencodeClient } from "@opencode-ai/sdk";
import { access } from "node:fs/promises";
import { join } from "node:path";

const DEFAULT_CONTINUE_MESSAGE =
  "Continue from the latest state. Read MEMORY.md and TODO.md first.";
const DEFAULT_INJECT_MESSAGE =
  "Reload MEMORY.md and TODO.md from disk and treat them as authoritative.";

function printHelp() {
  process.stdout.write(`Usage: node ~/.config/opencode/scripts/opencode-watchdog.mjs [options]

Options:
  --session <id>            Session ID to monitor (default: latest session)
  --directory <path>        Project/worktree directory (default: cwd)
  --base-url <url>          OpenCode server URL (default: http://127.0.0.1:4096)
  --model <provider/model>  Compaction model (default: openai/gpt-5.3-codex)
  --interval-min <number>   Scheduled compaction interval minutes (default: 25)
  --min-gap-min <number>    Minimum minutes between compactions (default: 3)
  --continue-message <msg>  Prompt to continue after summarize
  --inject-message <msg>    noReply prompt injected after summarize
  --no-continue             Do not send a follow-up continue prompt
  -h, --help                Show this help

Example:
  node ~/.config/opencode/scripts/opencode-watchdog.mjs \\
    --directory /path/to/worktree \\
    --model openai/gpt-5.3-codex \\
    --interval-min 20
`);
}

function parseArgs(argv) {
  const options = {
    baseUrl: process.env.OPENCODE_BASE_URL || "http://127.0.0.1:4096",
    directory: process.cwd(),
    sessionID: undefined,
    providerID: "openai",
    modelID: "gpt-5.3-codex",
    intervalMs: 25 * 60 * 1000,
    minGapMs: 3 * 60 * 1000,
    continueMessage: DEFAULT_CONTINUE_MESSAGE,
    injectMessage: DEFAULT_INJECT_MESSAGE,
    noContinue: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    }

    if (arg === "--session" && next) {
      options.sessionID = next;
      i += 1;
      continue;
    }

    if (arg === "--directory" && next) {
      options.directory = next;
      i += 1;
      continue;
    }

    if (arg === "--base-url" && next) {
      options.baseUrl = next;
      i += 1;
      continue;
    }

    if (arg === "--model" && next) {
      const [providerID, modelID] = next.split("/");
      if (providerID && modelID) {
        options.providerID = providerID;
        options.modelID = modelID;
      } else {
        options.modelID = next;
      }
      i += 1;
      continue;
    }

    if (arg === "--interval-min" && next) {
      const parsed = Number(next);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new Error(`Invalid --interval-min value: ${next}`);
      }
      options.intervalMs = Math.round(parsed * 60_000);
      i += 1;
      continue;
    }

    if (arg === "--min-gap-min" && next) {
      const parsed = Number(next);
      if (!Number.isFinite(parsed) || parsed < 0) {
        throw new Error(`Invalid --min-gap-min value: ${next}`);
      }
      options.minGapMs = Math.round(parsed * 60_000);
      i += 1;
      continue;
    }

    if (arg === "--continue-message" && next) {
      options.continueMessage = next;
      i += 1;
      continue;
    }

    if (arg === "--inject-message" && next) {
      options.injectMessage = next;
      i += 1;
      continue;
    }

    if (arg === "--no-continue") {
      options.noContinue = true;
      continue;
    }

    throw new Error(`Unknown argument: ${arg}`);
  }

  return options;
}

function log(message) {
  process.stdout.write(`[${new Date().toISOString()}] ${message}\n`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fileExists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function matchesSession(watchedSessionID, eventSessionID) {
  if (!eventSessionID) {
    return false;
  }
  return watchedSessionID === eventSessionID;
}

function isOverflowError(error) {
  if (!error || typeof error !== "object") {
    return false;
  }

  const name = error.name;
  const data = error.data || {};

  if (name === "ContextOverflowError") {
    return true;
  }

  if (name === "APIError" && data.statusCode === 413) {
    return true;
  }

  const haystack = `${data.message || ""} ${data.responseBody || ""}`.toLowerCase();
  const patterns = [
    "input exceeds context window",
    "context window",
    "context length",
    "maximum context length",
    "request entity too large",
    "too many tokens",
  ];

  return patterns.some((pattern) => haystack.includes(pattern));
}

async function resolveSessionID(client, options) {
  if (options.sessionID) {
    return options.sessionID;
  }

  const result = await client.session.list({
    directory: options.directory,
    limit: 20,
  });

  if (!result.data || result.data.length === 0) {
    throw new Error(
      "No sessions found. Start OpenCode in this worktree first, then rerun the watchdog.",
    );
  }

  const active = result.data.find((session) => !session.time.archived) || result.data[0];
  log(`Monitoring latest session ${active.id} (${active.title || "untitled"}).`);
  return active.id;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));

  const client = createOpencodeClient({
    baseUrl: options.baseUrl,
    directory: options.directory,
  });

  const sessionID = await resolveSessionID(client, options);

  const pathInfo = await client.path.get({ directory: options.directory });
  const worktreeRoot = pathInfo.data?.worktree || options.directory;
  const memoryPath = join(worktreeRoot, "MEMORY.md");
  const todoPath = join(worktreeRoot, "TODO.md");

  if (!(await fileExists(memoryPath))) {
    log(`Note: missing ${memoryPath} (compaction memory will skip it).`);
  }
  if (!(await fileExists(todoPath))) {
    log(`Note: missing ${todoPath} (compaction memory will skip it).`);
  }

  let inProgress = false;
  let lastCompactionAt = 0;

  const compactAndResume = async (reason, force) => {
    if (inProgress) {
      log(`Skipping compaction (${reason}): already running.`);
      return;
    }

    const now = Date.now();
    if (!force && now - lastCompactionAt < options.minGapMs) {
      log(`Skipping compaction (${reason}): min gap not reached.`);
      return;
    }

    if (!force) {
      const statusResponse = await client.session.status({
        directory: options.directory,
      });
      const status = statusResponse.data?.[sessionID];
      if (status?.type === "busy") {
        log(`Skipping compaction (${reason}): session is busy.`);
        return;
      }
    }

    inProgress = true;
    try {
      log(`Compacting session ${sessionID} (${reason})...`);
      await client.session.summarize({
        sessionID,
        directory: options.directory,
        providerID: options.providerID,
        modelID: options.modelID,
        auto: true,
      });

      lastCompactionAt = Date.now();
      log("Compaction completed.");

      await client.session.prompt({
        sessionID,
        directory: options.directory,
        noReply: true,
        parts: [{ type: "text", text: options.injectMessage }],
      });

      if (!options.noContinue) {
        await client.session.prompt({
          sessionID,
          directory: options.directory,
          model: {
            providerID: options.providerID,
            modelID: options.modelID,
          },
          parts: [{ type: "text", text: options.continueMessage }],
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      log(`Compaction attempt failed: ${message}`);
    } finally {
      inProgress = false;
    }
  };

  const interval = setInterval(() => {
    void compactAndResume("timer", false);
  }, options.intervalMs);

  if (typeof interval.unref === "function") {
    interval.unref();
  }

  process.on("SIGINT", () => {
    log("Stopping watchdog.");
    clearInterval(interval);
    process.exit(0);
  });

  log(
    `Watchdog started for session ${sessionID} in ${worktreeRoot}. ` +
      `Model ${options.providerID}/${options.modelID}, interval ${Math.round(
        options.intervalMs / 60_000,
      )}m.`,
  );

  while (true) {
    try {
      const events = await client.event.subscribe({ directory: options.directory });
      for await (const event of events.stream) {
        if (event.type !== "session.error") {
          continue;
        }

        const errorSessionID = event.properties.sessionID;
        if (!matchesSession(sessionID, errorSessionID)) {
          continue;
        }

        if (isOverflowError(event.properties.error)) {
          await compactAndResume("session.error overflow", true);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      log(`Event stream disconnected: ${message}`);
      await sleep(2000);
    }
  }
}

void main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`Watchdog failed to start: ${message}\n`);
  process.exit(1);
});
