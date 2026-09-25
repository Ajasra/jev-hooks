import sqlite3, os
from pathlib import Path

db = Path(os.path.expanduser("~/.gemini/config/safety_decisions.db"))
conn = sqlite3.connect(str(db))
conn.execute("DROP TABLE IF EXISTS rules")
conn.execute("DROP TABLE IF EXISTS decision_log")
conn.commit()
conn.close()
print(f"[+] Cleared: {db}")
