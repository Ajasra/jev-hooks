// @jev-spike — temporary RFC-27 S0 contract probe. Delete once S0 receipts are recorded.
// Dropped at ~/.config/opencode/plugins/jev-spike.ts on the boot under test.
// Raw hook inputs are appended as JSONL under $TMPDIR/jev-spike/ for fixture capture.
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { spawnSync } from "node:child_process"

const DIR = path.join(tmpdir(), "jev-spike")
const PYTHON = process.env.JEV_HOOK_PYTHON || "python"

function log(hook: string, input: unknown, output: unknown, extra?: Record<string, unknown>) {
  try {
    appendFileSync(
      path.join(DIR, hook + ".jsonl"),
      JSON.stringify({ ts: new Date().toISOString(), input, output, ...extra }) + "\n",
    )
  } catch {}
}

export default {
  id: "jev-spike",
  async server() {
    try {
      writeFileSync(path.join(DIR, "loaded.txt"), "loaded " + new Date().toISOString() + "\n")
    } catch {}
    return {
      "chat.message": async (input: any, output: any) => {
        log("chat.message", input, output)
        try {
          const parts = output.parts as any[]
          const idx = parts.findIndex((p) => p.type === "text")
          if (idx >= 0) parts[idx].text += "\n<jev-spike>SPIKE_TURN_MARKER</jev-spike>"
        } catch {}
      },
      "tool.execute.before": async (input: any, output: any) => {
        const t0 = Date.now()
        let spawnMs = -1
        let spawnOk = false
        try {
          const r = spawnSync(PYTHON, ["-m", "jev", "doctor", "--cwd", "."], {
            encoding: "utf8",
            timeout: 5000,
            cwd: process.cwd(),
          })
          spawnMs = Date.now() - t0
          spawnOk = r.status === 0
        } catch {
          spawnMs = Date.now() - t0
        }
        log("tool.execute.before", input, output, { spawn_ms: spawnMs, spawn_ok: spawnOk })
        const cmd = String((output && output.args && output.args.command) || "")
        if (cmd.includes("JEV_SPIKE_DENY")) {
          throw new Error("jev-spike: blocked marked command (RFC-27 S0 receipt)")
        }
      },
      "tool.execute.after": async (input: any, output: any) => {
        log("tool.execute.after", input, output)
        try {
          output.output = String(output.output ?? "") + "\n<!-- jev-spike-footer -->"
        } catch {}
      },
      "experimental.chat.system.transform": async (input: any, output: any) => {
        log("experimental.chat.system.transform", input, {
          system_len: Array.isArray(output?.system) ? output.system.length : -1,
        })
        try {
          output.system.push("<jev-spike>SPIKE_SYSTEM_INSTRUCTION_OK</jev-spike>")
        } catch {}
      },
      "experimental.session.compacting": async (input: any, output: any) => {
        log("experimental.session.compacting", input, output)
        try {
          output.context.push("<jev-spike>SPIKE_CHECKPOINT_CONTEXT</jev-spike>")
        } catch {}
      },
    }
  },
}
