# System One Speculative Fan-Out Protocol

**Domain**: `tool_harness` | **Confidence**: 1.00 | **Updated**: 2026-09-25T13:49:14Z

## 1. Problem Context & Architectural Invariant
System One Speculative Fan-Out Protocol
Batches 4-question speculative evaluations in ~110ms to prefetch git diffs and test states before LLM reasoning.

## 2. Canonical Solution & Implementation Diff
```diff
diff --git a/.agents/hooks/safety_db.py b/.agents/hooks/safety_db.py
index 2d59ffe..56951bd 100644
--- a/.agents/hooks/safety_db.py
+++ b/.agents/hooks/safety_db.py
@@ -341,4 +341,21 @@ def clear_all_rules() -> int:
 
 
+def clear_logs() -> Tuple[int, int]:
+    """
+    Clears all historical audit logs (decision_log and speculative_decisions)
+    for a clean calibration reset, preserving active user rules.
+    Returns (cleared_decision_logs, cleared_speculative_logs).
+    """
+    init_db()
+    conn = get_connection()
+    try:
+        with conn:
+            c1 = conn.execute("DELETE FROM decision_log").rowcount
+            c2 = conn.execute("DELETE FROM speculative_decisions").rowcount
+            return c1, c2
+    finally:
+        conn.close()
+
+
 def prune_db(days: int = 30) -> Tuple[int, int]:
     """
@@ -586,8 +603,14 @@ if __name__ == "__main__":
     parser.add_argument("--workspace",     type=str, default="")
     parser.add_argument("--reason",        type=str, default="User specified rule")
+    parser.add_argument("--clear-logs",    action="store_true", help="Clear all audit and speculative decision logs")
     parser.add_argument("--clear-all",     action="store_true", help="Clear all saved rules")
     parser.add_argument("--test-cmd",      type=str, help="Test how a command resolves")
     args = parser.parse_args()
 
+    if args.clear_logs:
+        c1, c2 = clear_logs()
+        print(f"[+] Cleared {c1} decision logs and {c2} speculative decisions from audit database.")
+        sys.exit(0)
+
     if args.review_speculative:
         print_speculative_review()
```
