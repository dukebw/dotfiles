import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { Plugin } from "@opencode-ai/plugin";

const execute = promisify(execFile);
const notifyScript = join(
  homedir(),
  ".config",
  "opencode",
  "scripts",
  "opencode-notify.sh",
);

async function notify(
  sessionID: string,
  sessionTitle: string,
  title: string,
  message: string,
) {
  try {
    await execute(notifyScript, [sessionID, sessionTitle, title, message]);
  } catch {
    await execute("/opt/homebrew/bin/terminal-notifier", [
      "-group",
      sessionID,
      "-title",
      title,
      "-message",
      message,
      "-sound",
      "Glass",
    ]);
  }
}

export default Plugin.define({
  id: "brendanduke.notifications",
  setup(context) {
    const controller = new AbortController();
    const task = (async () => {
      for await (const event of context.event.subscribe({
        signal: controller.signal,
      })) {
        try {
          const notification = (() => {
            // Turn end is session.execution.{succeeded,failed,interrupted};
            // interrupted is user-initiated, so it needs no notification.
            if (event.type === "session.execution.succeeded") {
              return {
                sessionID: event.data.sessionID,
                title: "opencode — turn finished",
              };
            }
            if (event.type === "session.execution.failed") {
              return {
                sessionID: event.data.sessionID,
                title: "opencode — turn failed",
              };
            }
            if (event.type === "question.asked") {
              return {
                sessionID: event.data.sessionID,
                title: "opencode — question",
                message: event.data.questions?.[0]?.question ?? "Input needed",
              };
            }
          })();
          if (!notification) continue;

          // Subagent (child-session) events are parent-turn noise. Session
          // lookup failure must not suppress the notification itself.
          let parentID: string | undefined;
          let sessionTitle = "session";
          try {
            const session = await context.session.get({
              sessionID: notification.sessionID,
            });
            const info = (session as any)?.data ?? session;
            parentID = info?.parentID;
            sessionTitle = info?.title ?? sessionTitle;
          } catch (error) {
            console.error("opencode notify: session lookup failed", error);
          }
          if (parentID) continue;

          await notify(
            notification.sessionID,
            sessionTitle,
            notification.title,
            notification.message ?? sessionTitle,
          );
        } catch (error) {
          console.error("OpenCode notification failed", error);
        }
      }
    })().catch((error: unknown) => {
      if (!controller.signal.aborted) {
        console.error("OpenCode notification plugin stopped", error);
      }
    });

    return async () => {
      controller.abort();
      await task;
    };
  },
});
