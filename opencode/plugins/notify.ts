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
      // CLI events can precede the SDK typings pinned in this config.
      const eventType: string = event.type;
      const properties = event.properties as {
        sessionID?: string;
        questions?: Array<{ question?: string }>;
      };
      const notification = (() => {
        if (eventType === "session.idle") {
          return {
            sessionID: properties.sessionID,
            title: "opencode — turn finished",
          };
        }
        if (
          eventType === "question.asked" ||
          eventType === "question.v2.asked"
        ) {
          return {
            sessionID: properties.sessionID,
            title: "opencode — question",
            message: properties.questions?.[0]?.question ?? "Input needed",
          };
        }
      })();
      if (!notification) {
        return;
      }

      const sessionID = notification.sessionID;
      if (!sessionID) {
        return;
      }

      // Subagent attention events are parent-turn noise.
      const session = await client.session.get({ path: { id: sessionID } });
      if (session.data?.parentID) {
        return;
      }

      const sessionTitle = session.data?.title ?? "session";
      const message = notification.message ?? sessionTitle;

      try {
        // The script owns the notify decision (focus suppression, click
        // action), so it can change without an opencode server restart.
        await $`${NOTIFY_SCRIPT} ${sessionID} ${sessionTitle} ${notification.title} ${message}`;
      } catch {
        // Script missing/failed: plain notification, no click action.
        const script = `display notification "${message.replace(/"/g, '\\"')}" with title "${notification.title}" sound name "Glass"`;
        await $`osascript -e ${script}`;
      }
    },
  };
};
