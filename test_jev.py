import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / ".agents" / "hooks"))
import env_loader

def test_connection():
    api_key, endpoint, model, headers = env_loader.get_client_config()
    print(f"[*] API Key detected: {api_key[:12]}...{api_key[-4:] if len(api_key)>16 else ''}")
    print(f"[*] Endpoint: {endpoint}")
    print(f"[*] Model: {model}")



    payload = {
        "model": model,
        "state": "git status",
        "questions": {
            "is_safe": {
                "type": "noul",
                "instructions": "Is git status a read-only safe operation?"
            }
        }
    }

    print("\n[*] Sending request to Jev...")
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[+] HTTP Status: {resp.status}")
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[+] Response JSON:\n{json.dumps(data, indent=2)}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error {e.code}: {e.reason}")
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"[-] Error body:\n{err_body}")
        return False
    except Exception as e:
        print(f"[-] Error: {e}")
        return False

if __name__ == "__main__":
    test_connection()
