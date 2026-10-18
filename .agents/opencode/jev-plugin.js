import { homedir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const jevCommand = process.env.JEV_BIN || join(homedir(), ".local", "bin", "jev");
const turnCache = new Map();

function invokeJev(payload, cwd) {
  const result = spawnSync(jevCommand, ["hook", "--harness", "opencode"], {
    cwd,
    env: process.env,
    input: JSON.stringify(payload),
    encoding: "utf8",
    timeout: 5000,
    maxBuffer: 1024 * 1024,
  });
  if (result.error || result.status !== 0 || !result.stdout) {
    throw new Error("Jev hook did not complete successfully.");
  }
  return JSON.parse(result.stdout);
}

function messageText(parts) {
  if (!Array.isArray(parts)) return "";
  return parts
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n");
}

export default async function jevPlugin({ directory, client }) {
  return {
    "tool.execute.before": async (input, output) => {
      const tool = String(input.tool || "");
      const args = output.args || {};
      const isPolicySensitive = ["bash", "write", "edit", "multiedit", "patch", "apply_patch"].includes(tool);
      let result;
      try {
        result = invokeJev(
          {
            opencode_event: "tool.execute.before",
            session_id: input.sessionID || "",
            call_id: input.callID || "",
            cwd: directory || process.cwd(),
            tool,
            args,
          },
          directory || process.cwd(),
        );
      } catch (error) {
        if (isPolicySensitive) {
          throw new Error("Jev safety check failed; this tool call is blocked.");
        }
        return;
      }

      if (result.deny) {
        throw new Error(`[Jev policy] ${result.reason || "Operation denied."}`);
      }
      if (typeof result.context === "string" && result.context.trim()) {
        await client.tui.showToast({
          body: {
            title: "Jev advisory",
            message: result.context.slice(0, 1200),
            variant: "info",
            duration: 8000,
          },
          query: { directory: directory || process.cwd() },
        });
      }
    },

    "tool.execute.after": async (input, output) => {
      try {
        invokeJev({
          opencode_event: "tool.execute.after",
          session_id: input.sessionID || "",
          call_id: input.callID || "",
          cwd: directory || process.cwd(),
          tool: input.tool || "",
          args: input.args || {},
          tool_response: output.metadata || {},
        }, directory || process.cwd());
      } catch {
        // Recording is advisory and must not change an already completed tool call.
      }
    },

    "chat.message": async (input, output) => {
      const prompt = messageText(output.parts);
      if (!input.sessionID || !prompt) return;

      try {
        const result = invokeJev(
          {
            opencode_event: "turn.before",
            session_id: input.sessionID,
            message_id: output.message.id || "",
            cwd: directory || process.cwd(),
            agent: output.message.agent || input.agent || "",
            prompt,
          },
          directory || process.cwd(),
        );
        turnCache.set(input.sessionID, typeof result.context === "string" ? result.context : "");
        if (turnCache.size > 64) turnCache.delete(turnCache.keys().next().value);
      } catch {
        // Turn enrichment is advisory; deterministic tool safety remains active.
        turnCache.set(input.sessionID, "");
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      const context = input.sessionID ? turnCache.get(input.sessionID) : "";
      if (context) {
        output.system.push(`Jev context for this turn:\n${context}`);
      }
    },

    event: async ({ event }) => {
      if (event.type === "session.created") {
        const sessionID = event.properties.info?.id || "";
        if (!sessionID) return;
        try {
          const result = invokeJev(
            {
              opencode_event: "session.start",
              session_id: sessionID,
              cwd: directory || process.cwd(),
            },
            directory || process.cwd(),
          );
          if (typeof result.context === "string") turnCache.set(sessionID, result.context);
        } catch {
          // Session enrichment is advisory; tool safety remains active.
        }
      }
      if (event.type === "session.idle") {
        turnCache.delete(event.properties.sessionID);
      }
    },
  };
}
