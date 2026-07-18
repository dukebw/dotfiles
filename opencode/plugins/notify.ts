import { homedir } from "node:os";
import { join } from "node:path";
import type { Plugin } from "@opencode-ai/plugin";

const NOTIFY_SCRIPT = join(
  homedir(),
  ".config",
  "opencode",
  "scripts",
  "opencode-notify.sh",
);

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

      try {
        // The script owns the notify decision (focus suppression, click
        // action), so it can change without an opencode server restart.
        await $`${NOTIFY_SCRIPT} ${sessionID} ${title}`;
      } catch {
        // Script missing/failed: plain notification, no click action.
        const script = `display notification "${title.replace(/"/g, '\\"')}" with title "opencode — turn finished" sound name "Glass"`;
        await $`osascript -e ${script}`;
      }
    },
  };
};
