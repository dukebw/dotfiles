import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { Plugin } from "@opencode-ai/plugin";

const execute = promisify(execFile);
const sessionLookupDelaysMs = [0, 250, 750];
// `opencode run` is headless, so its turn-end notifications are pure noise.
// The zsh `opencode` wrapper stamps run sessions with this title prefix
// (run renames every session it prompts, so --continue/--session are covered).
const runSessionTitlePrefix = "[run]";
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
  async setup(context) {
    const controller = new AbortController();
    const sessions = new Map<
      string,
      { id: string; parentID?: string; title?: string }
    >();

    const sessionInfo = (value: any) => {
      const info =
        value?.data?.info ??
        value?.properties?.info ??
        value?.info ??
        value?.data ??
        value;
      if (typeof info?.id !== "string") return;

      const result = {
        id: info.id,
        parentID:
          typeof info.parentID === "string" ? info.parentID : undefined,
        title: typeof info.title === "string" ? info.title : undefined,
      };
      sessions.set(result.id, result);
      return result;
    };

    const rememberSessionEvent = (event: any) => {
      if (event.type === "session.created") {
        const data = event.data;
        sessions.set(data.sessionID, {
          id: data.sessionID,
          parentID: data.parentID,
          title: data.title,
        });
      }
      if (event.type === "session.renamed") {
        const data = event.data;
        sessions.set(data.sessionID, {
          ...sessions.get(data.sessionID),
          id: data.sessionID,
          title: data.title,
        });
      }
    };

    const getSession = async (sessionID: string) => {
      for (const delayMs of sessionLookupDelaysMs) {
        if (delayMs) {
          await new Promise((resolve) => setTimeout(resolve, delayMs));
        }

        try {
          const info = sessionInfo(await context.session.get({ sessionID }));
          if (info?.title) return info;
        } catch (error) {
          console.error("opencode notify: session lookup failed", error);
        }

        const cached = sessions.get(sessionID);
        if (cached?.title) return cached;
      }

      return sessions.get(sessionID);
    };

    const notifySession = async (
      sessionID: string,
      title: string,
      message?: string,
    ) => {
      // Subagent (child-session) events are parent-turn noise. Session lookup
      // failure must not suppress the notification itself.
      const session = await getSession(sessionID);
      if (session?.parentID) return;
      if (session?.title?.startsWith(runSessionTitlePrefix)) return;

      const sessionTitle = session?.title ?? "session";
      await notify(sessionID, sessionTitle, title, message ?? sessionTitle);
    };

    await context.tool.hook("execute.before", async (event) => {
      if (event.tool.split(".").at(-1) !== "question") return;
      const input = event.input as {
        questions?: Array<{ question?: string }>;
      };
      await notifySession(
        event.sessionID,
        "opencode — question",
        input.questions?.[0]?.question ?? "Input needed",
      );
    });

    const task = (async () => {
      for await (const event of context.event.subscribe({
        signal: controller.signal,
      })) {
        try {
          if (
            event.type === "session.created" ||
            event.type === "session.renamed"
          )
            rememberSessionEvent(event);

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

          await notifySession(
            notification.sessionID,
            notification.title,
            notification.message,
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
