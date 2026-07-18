import { homedir } from "node:os";
import { join } from "node:path";
import type { Plugin } from "@opencode-ai/plugin";

const FOCUS_SCRIPT = join(
  homedir(),
  ".config",
  "opencode",
  "scripts",
  "opencode-focus-pane.sh",
);
const TERMINAL_NOTIFIER = "/opt/homebrew/bin/terminal-notifier";

const shellQuote = (s: string) => `'${s.replace(/'/g, `'\\''`)}'`;

export const NotifyPlugin: Plugin = async ({ client, $ }) => {
  return {
    event: async ({ event }) => {
      if (event.type !== "session.idle") {
        return;
      }

      const sessionID = (event.properties as { sessionID?: string }).sessionID;
      if (!sessionID) {
        return;
      }

      // Subagent sessions also go idle mid-turn; only notify for top-level ones.
      const session = await client.session.get({ path: { id: sessionID } });
      if (session.data?.parentID) {
        return;
      }

      const title = session.data?.title ?? "session";
      const clickCommand = `${shellQuote(FOCUS_SCRIPT)} ${shellQuote(sessionID)} ${shellQuote(title)}`;

      try {
        // -group coalesces repeat notifications per session instead of stacking.
        await $`${TERMINAL_NOTIFIER} -group ${sessionID} -title ${"opencode — turn finished"} -message ${title} -sound Glass -execute ${clickCommand}`;
      } catch {
        // terminal-notifier missing/failed: plain notification, no click action.
        const script = `display notification "${title.replace(/"/g, '\\"')}" with title "opencode — turn finished" sound name "Glass"`;
        await $`osascript -e ${script}`;
      }
    },
  };
};
