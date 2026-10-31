"""Verbatim sources for generated harness registrations."""

from __future__ import annotations

OPENCODE_JEV_TS = """@@HEADER@@
import { spawn, spawnSync } from "node:child_process"

type Envelope = {
  decision?: string
  reason?: string
  reason_code?: string
  context?: string
  footer?: string
  checkpoint_context?: string[]
}

const PYTHON = @@PYTHON@@
const HARNESS_VERSION = @@HARNESS_VERSION@@
const PROBE_TIMEOUT_MS = 3000
const DEFAULT_TIMEOUT_MS = 750
const FOOTER_LIMIT = 4000
const MAX_PENDING = 8
const TAIL_LIMIT = 12000
const MAX_SESSIONS = 128
const FILE_MUTATIONS = new Set(["write", "edit", "apply_patch"])
const DRAIN_HOOK = "experimental.chat.system.transform"
const APPROVAL_TEXT =
  "Jev requires explicit approval for this operation. Approval is issued outside this agent session; see the Jev user guide."

const PRE_FILTER = new Set([@@PRE_FILTER@@])

const HOOKS: Record<string, string> = {
@@HOOKS@@
}

const SPAWN_TIMEOUT: Record<string, number> = {
@@TIMEOUTS@@
}

async function createHooks(input: any) {
const client = input && input.client
const directory = String((input && input.directory) || process.cwd())
let enabled = true
const reported = new Set<string>()
const pending = new Map<string, string[]>()
const tails = new Map<string, string>()
const agents = new Map<string, string>()
const recent = new Map<string, string>()
const objectives = new Map<string, string>()
const activePaths = new Map<string, string>()
const errors = new Map<string, string>()
const touched = new Map<string, number>()

function forget(session: string) {
  pending.delete(session)
  tails.delete(session)
  agents.delete(session)
  recent.delete(session)
  objectives.delete(session)
  activePaths.delete(session)
  errors.delete(session)
  reported.delete(session)
  touched.delete(session)
}

function touch(session: string) {
  if (!session) return
  touched.delete(session)
  touched.set(session, Date.now())
  while (touched.size > MAX_SESSIONS) {
    const oldest = touched.keys().next().value
    if (oldest === undefined) break
    forget(oldest)
  }
}

function denial(message: string): Error {
  const error = new Error(message) as Error & { jev?: boolean }
  error.jev = true
  return error
}

function note(message: string, session: string) {
  const key = session || "session"
  if (reported.has(key)) return
  reported.add(key)
  try {
    console.error("[jev] " + message)
  } catch {}
  try {
    const tui = client && client.tui
    if (tui && typeof tui.showToast === "function") {
      void Promise.resolve(tui.showToast({ body: { title: "Jev", message: message, variant: "error", duration: 8000 } })).catch(() => {})
    }
  } catch {}
}

function probe() {
  try {
    const raw: any = spawnSync(PYTHON, ["-m", "jev", "doctor", "--cwd", directory], {
      encoding: "utf8",
      cwd: directory,
      timeout: PROBE_TIMEOUT_MS,
    })
    if (raw && raw.status === 0) return
    note("self-test failed: jev doctor exited with status " + String(raw && raw.status), "startup")
  } catch (error: any) {
    note("self-test failed: " + String((error && error.message) || error), "startup")
  }
  enabled = false
}

let worker: any
let starting: Promise<void> | undefined
let sequence = 0
let chain: Promise<any> = Promise.resolve()
let queued = 0
const requests = new Map<number, { resolve: (value: any) => void, timer: any }>()

function stopWorker() {
  const child = worker
  worker = undefined
  starting = undefined
  if (child) { try { child.kill() } catch {} }
  for (const request of requests.values()) {
    clearTimeout(request.timer)
    request.resolve(undefined)
  }
  requests.clear()
}

function startWorker(): Promise<void> {
  if (starting) return starting
  starting = new Promise<void>((resolve, reject) => {
    let child: any
    try {
      child = spawn(PYTHON, ["-u", "-m", "jev", "hook-worker", "--harness", "opencode"], {
        cwd: directory, stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
      })
      worker = child
    } catch (error) { reject(error); return }
    let buffer = ""
    let ready = false
    const timer = setTimeout(() => fail(new Error("worker startup timed out")), PROBE_TIMEOUT_MS)
    const fail = (error: Error) => {
      clearTimeout(timer)
      if (!ready) reject(error)
      if (worker === child) stopWorker()
    }
    child.on("error", fail)
    child.on("exit", () => fail(new Error("worker exited")))
    child.stdin.on("error", fail)
    child.stderr.on("data", () => {})
    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (chunk: string) => {
      buffer += chunk
      if (buffer.length > 4194304) { fail(new Error("worker output exceeded limit")); return }
      let end: number
      while ((end = buffer.indexOf("\\n")) >= 0) {
        const line = buffer.slice(0, end)
        buffer = buffer.slice(end + 1)
        try {
          const message = JSON.parse(line)
          if (!ready && message.ready === true) {
            ready = true
            clearTimeout(timer)
            resolve()
            continue
          }
          const request = requests.get(message.request_id)
          if (!request) { fail(new Error("worker response identity mismatch")); return }
          requests.delete(message.request_id)
          clearTimeout(request.timer)
          const result = message.result
          request.resolve(result && !Array.isArray(result) && ["allow", "deny", "ask"].includes(result.decision) ? result : undefined)
        } catch { fail(new Error("invalid worker output")); return }
      }
    })
  })
  return starting
}

async function call(hook: string, payload: unknown, session: string): Promise<Envelope | undefined> {
  const deadline = Date.now() + (SPAWN_TIMEOUT[hook] || DEFAULT_TIMEOUT_MS)
  if (queued >= MAX_PENDING) { note("worker queue is full", session); return undefined }
  queued++
  const task = chain.then(async () => {
    try {
      await startWorker()
      const remaining = deadline - Date.now()
      if (remaining <= 0) return undefined
      const result = await new Promise<any>(resolve => {
        const request_id = ++sequence
        const timer = setTimeout(() => stopWorker(), remaining)
        requests.set(request_id, { resolve, timer })
        worker.stdin.write(JSON.stringify({ request_id, payload }) + "\\n")
      })
      if (!result) note(hook + " inspection unavailable", session)
      return result
    } catch { stopWorker(); note(hook + " worker unavailable", session); return undefined }
    finally { queued-- }
  })
  chain = task.catch(() => {})
  return task
}

function envelope(hook: string, session: string, turn: string, agent: string, prompt: string, native: unknown): Record<string, unknown> {
  touch(session)
  return {
    hook: hook,
    harness_version: HARNESS_VERSION,
    cwd: directory,
    session_id: session,
    turn_id: turn,
    agent: agent,
    prompt: prompt,
    prior_context: recent.get(session) || "",
    session_objective: objectives.get(session) || "",
    active_path: activePaths.get(session) || "",
    last_error: errors.get(session) || "",
    native: native || {},
  }
}

function assertAllowed(result: Envelope) {
  if (result.decision === "deny") {
    throw denial("Jev denied: " + (result.reason || result.reason_code || "policy denial"))
  }
  if (result.decision === "ask") {
    throw denial(APPROVAL_TEXT + (result.reason ? " Reason: " + result.reason : ""))
  }
}

function enqueue(session: string, text: string) {
  if (!session) return
  const list = pending.get(session) || []
  list.push(text)
  while (list.length > MAX_PENDING) list.shift()
  pending.set(session, list)
}

function bound(text: string): string {
  if (text.length <= FOOTER_LIMIT) return text
  const cut = text.slice(0, FOOTER_LIMIT)
  const open = cut.lastIndexOf("<!--")
  if (open >= 0 && cut.indexOf("-->", open) < 0) return cut.slice(0, open)
  return cut
}

async function onTurn(input: any, output: any) {
  const parts = Array.isArray(output && output.parts) ? output.parts : []
  const message = (output && output.message) || {}
  const text = parts
    .filter((part: any) => part && part.type === "text" && typeof part.text === "string")
    .map((part: any) => part.text)
    .join("\\n")
  const session = String((input && input.sessionID) || "")
  const turn = String(message.id || (input && input.messageID) || "")
  const agent = String((input && input.agent) || message.agent || "")
  if (session && agent) agents.set(session, agent)
  const result = await call("chat.message", envelope("chat.message", session, turn, agent, text, input), session)
  if (session && text.trim()) {
    if (!objectives.has(session)) objectives.set(session, text.slice(0, 400))
    recent.set(session, text.slice(0, 1000))
  }
  if (!result) return
  assertAllowed(result)
  if (!result.context) return
  const index = parts.findIndex((part: any) => part && part.type === "text" && typeof part.text === "string")
  if (index >= 0) {
    parts[index].text = parts[index].text + "\\n\\n" + result.context
    return
  }
  enqueue(session, result.context)
}

async function onToolBefore(input: any, output: any) {
  const name = String((input && input.tool) || "")
  if (PRE_FILTER.has(name)) return
  const session = String((input && input.sessionID) || "")
  const args = (output && output.args) || {}
  if (session && FILE_MUTATIONS.has(name) && typeof args.filePath === "string") {
    activePaths.set(session, args.filePath.slice(0, 500))
  }
  const payload = envelope("tool.execute.before", session, "", agents.get(session) || "", "", input)
  payload.tool = { name: name, call_id: String((input && input.callID) || ""), args: (output && output.args) || {} }
  const result = await call("tool.execute.before", payload, session)
  if (!result) {
    if (!FILE_MUTATIONS.has(name)) throw denial("Jev could not inspect this operation; retry after restoring the Jev runtime.")
    return
  }
  assertAllowed(result)
  if (result.context) enqueue(session, result.context)
}

async function onToolAfter(input: any, output: any) {
  const name = String((input && input.tool) || "")
  if (PRE_FILTER.has(name)) return
  const session = String((input && input.sessionID) || "")
  const metadata = (output && output.metadata) || {}
  if (session && ((typeof metadata.exit === "number" && metadata.exit !== 0) || metadata.error)) {
    errors.set(session, String((output && output.output) || metadata.error).slice(0, 800))
  }
  const payload = envelope("tool.execute.after", session, "", agents.get(session) || "", "", input)
  payload.tool = { name: name, call_id: String((input && input.callID) || ""), args: (input && input.args) || {} }
  payload.result = {
    title: String((output && output.title) || ""),
    output: String((output && output.output) || ""),
    metadata: (output && output.metadata) || {},
  }
  const result = await call("tool.execute.after", payload, session)
  if (!result) return
  if (result.footer && output && typeof output.output === "string") {
    output.output = output.output + "\\n" + bound(String(result.footer))
  }
  if (result.context) enqueue(session, result.context)
}

async function onCheckpoint(input: any, output: any) {
  const session = String((input && input.sessionID) || "")
  const result = await call("experimental.session.compacting", envelope("experimental.session.compacting", session, "", "", "", input), session)
  if (!result) return
  const items = Array.isArray(result.checkpoint_context) ? result.checkpoint_context : []
  const target = output && Array.isArray(output.context) ? output.context : null
  if (!target) return
  for (const item of items) {
    if (typeof item === "string" && item) target.push(item)
  }
}

async function onSystemTransform(input: any, output: any) {
  const session = String((input && input.sessionID) || "")
  if (!session) return
  touch(session)
  const queued = pending.get(session)
  if (queued && queued.length) {
    const merged = tails.get(session)
    const entries = [...(merged ? [merged] : []), ...queued]
    let tail = entries.join("\\n\\n")
    while (tail.length > TAIL_LIMIT && entries.length > 1) {
      entries.shift()
      tail = entries.join("\\n\\n")
    }
    tails.set(session, tail.slice(0, TAIL_LIMIT))
    pending.delete(session)
  }
  const tail = tails.get(session)
  if (!tail) return
  const system = output && Array.isArray(output.system) ? output.system : null
  if (!system) return
  if (system.indexOf(tail) >= 0) return
  for (let index = system.length - 1; index >= 0; index--) {
    if (typeof system[index] === "string" && system[index].startsWith("[Jev session advisories]\\n")) system.splice(index, 1)
  }
  system.push("[Jev session advisories]\\n" + tail)
}

const HANDLERS: Record<string, (input: any, output: any) => Promise<void>> = {
  "chat.message": onTurn,
  "tool.execute.before": onToolBefore,
  "tool.execute.after": onToolAfter,
  [DRAIN_HOOK]: onSystemTransform,
  "experimental.session.compacting": onCheckpoint,
}

function guard(handler: (input: any, output: any) => Promise<void>) {
  return async (hookInput: any, output: any) => {
    if (!enabled) {
      const name = String((hookInput && hookInput.tool) || "")
      if (handler === onToolBefore && !PRE_FILTER.has(name) && !FILE_MUTATIONS.has(name)) {
        throw denial("Jev self-test failed; restore the Jev runtime before retrying this operation.")
      }
      return
    }
    try {
      await handler(hookInput, output)
    } catch (error: any) {
      if (error && error.jev === true) throw error
      note("internal error: " + String((error && error.message) || error), String((hookInput && hookInput.sessionID) || ""))
      const name = String((hookInput && hookInput.tool) || "")
      if (handler === onToolBefore && !PRE_FILTER.has(name) && !FILE_MUTATIONS.has(name)) {
        throw denial("Jev could not inspect this operation; retry after restoring the Jev runtime.")
      }
    }
  }
}

    probe()
    if (enabled) {
      try { await startWorker() }
      catch { enabled = false; note("worker startup failed", "startup") }
    }
    const hooks: Record<string, any> = {}
    for (const hook of Object.keys(HOOKS)) {
      const handler = HANDLERS[hook]
      if (handler) hooks[hook] = guard(handler)
    }
    const drain = HANDLERS[DRAIN_HOOK]
    if (drain) hooks[DRAIN_HOOK] = guard(drain)
    hooks.event = async ({ event }: any) => {
      if (event && event.type === "message.part.updated") {
        const part = event.properties && event.properties.part
        const state = part && part.state
        if (part && part.type === "tool" && part.sessionID && state && state.status === "error") {
          const session = String(part.sessionID)
          touch(session)
          errors.set(session, String(state.error || "Tool failed").slice(0, 800))
        }
      }
      if (event && event.type === "session.deleted") {
        const info = event.properties && event.properties.info
        const session = String((info && info.id) || "")
        if (session) {
          forget(session)
          await call("session.deleted", envelope("session.deleted", session, "", "", "", event), session)
          forget(session)
        }
      }
    }
    hooks.dispose = async () => {
      stopWorker()
      pending.clear()
      tails.clear()
      agents.clear()
      recent.clear()
      objectives.clear()
      activePaths.clear()
      errors.clear()
      touched.clear()
      reported.clear()
    }
    return hooks
}

export default {
  id: "jev",
  async server(input: any) {
    return createHooks(input)
  },
}
"""
