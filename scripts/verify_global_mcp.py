"""Read-only smoke check of the installed MCP registrations on Windows."""
import asyncio
import json
import pathlib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    home = pathlib.Path.home()
    project_root = pathlib.Path(__file__).resolve().parents[1]
    smoke_workspace = project_root / 'temp' / 'jev-live-smoke-20261002'
    try:
        import tomllib as tomli
    except ImportError:
        import tomli
    codex = tomli.loads((home / '.codex/config.toml').read_text())['mcp_servers']['jev']
    ag = json.loads((home / '.gemini/antigravity/mcp_config.json').read_text())['mcpServers']['jev']
    oc = json.loads((home / '.config/opencode/opencode.jsonc').read_text())['mcp']['jev']
    for name, config in [('codex', codex), ('antigravity', ag), ('opencode', oc)]:
        command = config['command']
        args = config.get('args', [])
        if isinstance(command, list):
            command, args = command[0], command[1:]
        params = StdioServerParameters(command=command, args=args, cwd=str(smoke_workspace))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool('skills_list', {})
                assert not result.is_error, (name, result)
                skills = (result.structured_content or {}).get('result', [])
                print(name, 'skills:', len(skills))
                assert len(skills) >= 7, (name, skills)
                diagnostics = await session.call_tool('diagnostics_status', {})
                assert not diagnostics.is_error, (name, diagnostics)
                for item in diagnostics.content:
                    if hasattr(item, 'text'):
                        data = json.loads(item.text)
                        print(name, 'identity:', data.get('harness_identity'), 'workspace:', data.get('workspace_root'))


if __name__ == '__main__':
    asyncio.run(main())
