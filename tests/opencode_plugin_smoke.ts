/** Execute the generated plugin against a deterministic subprocess fixture.
 * Run: npm exec --yes --package=tsx -- tsx tests/opencode_plugin_smoke.ts
 */
import assert from "node:assert/strict"
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import plugin from "./fixtures/opencode/jev.ts"

async function main() {
  const root = mkdtempSync(join(tmpdir(), "jev-plugin-"))
  const oldPath = process.env.PYTHONPATH
  const log = join(root, "calls.jsonl")
  const modeFile = join(root, "mode.txt")
  const mode = (value: string) => writeFileSync(modeFile, value)
  mode("allow")
  mkdirSync(join(root, "jev"))
  writeFileSync(join(root, "jev", "__init__.py"), "")
  writeFileSync(join(root, "jev", "__main__.py"), `
import json, os, sys, time
def mode():
    with open(os.environ["JEV_TEST_MODE_FILE"]) as source: return source.read()
if "doctor" in sys.argv:
    sys.exit(1 if mode() == "probe_failure" else 0)
print('{"ready":true}', flush=True)
for line in sys.stdin:
    request = json.loads(line)
    raw = request["payload"]
    current = mode()
    with open(os.environ["JEV_TEST_LOG"], "a", encoding="utf-8") as out:
        out.write(json.dumps(raw) + "\\n")
    if current == "timeout": time.sleep(2)
    if current == "exit": sys.exit(1)
    if current == "malformed":
        print("not JSON", flush=True)
    else:
        result = {"decision": current if current in ("deny", "ask", "invalid") else "allow",
                  "context": "advice" * 800 if current == "context" else "",
                  "reason": "fixture denial", "checkpoint_context": []}
        print(json.dumps({"request_id": request["request_id"], "result": result}), flush=True)
`)
  process.env.PYTHONPATH = root
  process.env.JEV_TEST_LOG = log
  process.env.JEV_TEST_MODE_FILE = modeFile
  const a = join(root, "a"), b = join(root, "b")
  mkdirSync(a); mkdirSync(b)
  const calls = () => readFileSync(log, "utf8").trim().split("\n").map(line => JSON.parse(line))
  const turn = (hooks: any, prompt: string, sessionID = "shared") => hooks["chat.message"](
    { sessionID }, { message: { id: prompt, agent: "build" }, parts: [{ type: "text", text: prompt }] },
  )
  const tool = (hooks: any, name = "bash", sessionID = "shared") => hooks["tool.execute.before"](
    { sessionID, tool: name, callID: "call" }, { args: { command: "git status", filePath: "src/app.py" } },
  )
  try {
    mode("allow")
    const first = await plugin.server({ directory: a })
    const second = await plugin.server({ directory: b })
    await turn(first, "alpha")
    await turn(second, "beta")
    await turn(first, "fix it")
    let last = calls().at(-1)
    assert.equal(last.cwd, a)
    assert.equal(last.prior_context, "alpha")
    assert.equal(last.session_objective, "alpha")
    await second.dispose()
    await tool(first, "edit")
    await first["tool.execute.after"]({ sessionID: "shared", tool: "bash", callID: "error", args: {} },
      { output: "test failed", metadata: { exit: 1 } })
    await turn(first, "repair")
    last = calls().at(-1)
    assert.equal(last.active_path, "src/app.py")
    assert.equal(last.last_error, "test failed")
    await first.event({ event: { type: "session.deleted", properties: { info: { id: "shared" } } } })
    await turn(first, "new session")
    last = calls().at(-1)
    assert.equal(last.prior_context, "")
    assert.equal(last.session_objective, "")

    for (const fault of ["deny", "ask", "malformed", "invalid", "exit", "timeout"]) {
      mode(fault)
      await assert.rejects(() => tool(first), /Jev/)
      if (!["deny", "ask"].includes(fault)) await tool(first, "edit")
      await tool(first, "read")
    }
    mode("probe_failure")
    const broken = await plugin.server({ directory: b })
    await assert.rejects(() => tool(broken), /self-test failed/)
    await tool(broken, "write")
    await tool(broken, "read")
    await broken.dispose()

    mode("context")
    const system = { system: ["native system"] }
    for (let i = 0; i < 8; i++) {
      await tool(first)
      await first["experimental.chat.system.transform"]({ sessionID: "shared" }, system)
    }
    assert.equal(system.system.length, 2)
    assert.ok(system.system[1].length <= 12030)

    mode("allow")
    for (let i = 0; i < 129; i++) await turn(first, "request", "session-" + i)
    await turn(first, "again", "session-0")
    assert.equal(calls().at(-1).prior_context, "")
    await first.dispose()
    console.log("OpenCode plugin smoke passed: instance isolation, recency, errors, cleanup, bounded state, denial and fault policy")
  } finally {
    if (oldPath === undefined) delete process.env.PYTHONPATH
    else process.env.PYTHONPATH = oldPath
    delete process.env.JEV_TEST_MODE_FILE
    delete process.env.JEV_TEST_LOG
    rmSync(root, { recursive: true, force: true })
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
