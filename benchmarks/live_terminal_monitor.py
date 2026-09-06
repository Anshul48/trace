import json, time, os, sys
from pathlib import Path

PROGRESS_FILE = Path("docs/program/inbox/cap-mod01/progress.json")

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def main():
    print("Initializing TRACE-CAP-001 Live Monitor...")
    last_log_count = 0
    while True:
        try:
            if not PROGRESS_FILE.exists():
                time.sleep(2)
                continue
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            active_model = data.get("active_model", "")
            overall_pct = data.get("overall_progress_percent", 0.0)
            completed_clusters = data.get("completed_clusters_all_models", 0)
            total_clusters = data.get("total_clusters_all_models", 500)
            status = data.get("status", "")
            models = data.get("models", [])
            logs = data.get("logs", [])

            clear()
            print("=" * 80)
            print(" TRACE-CAP-001: MANDATORY USER NOTIFICATION INVARIANT (LIVE MONITOR)")
            active_str = f" | Active: {active_model}" if active_model else ""
            print(f" Task: {data.get('task_name')} | Status: {status.upper()}{active_str}")
            bar_len = 30
            filled_len = int(bar_len * (min(100.0, max(0.0, overall_pct)) / 100.0))
            bar = "█" * filled_len + "░" * (bar_len - filled_len)
            print(f" Overall Progress: [{bar}] {overall_pct:.1f}% ({completed_clusters}/{total_clusters} clusters)")
            print("=" * 80)
            print(f"{'Tier':<8} {'Model':<16} {'Params':<8} {'Status':<12} {'Done/Tot':<10} {'TPS':<8} {'P95 (ms)':<10} {'Invalid'}")
            print("-" * 80)
            for m in models:
                tps_str = f"{m.get('tokens_per_sec', 0.0):.1f}" if m.get('tokens_per_sec') is not None else "--"
                p95_str = f"{m.get('p95_latency_ms', 0.0):.0f}" if m.get('p95_latency_ms') is not None else "--"
                inv_str = f"{m.get('invalid_rate', 0.0)*100:.1f}%"
                print(f"{m.get('tier', ''):<8} {m.get('name', ''):<16} {m.get('params', ''):<8} {m.get('status', ''):<12} {m.get('completed_clusters', 0)}/{m.get('total_clusters', 100):<6} {tps_str:<8} {p95_str:<10} {inv_str}")
            print("=" * 80)
            print("Recent Logs:")
            for l in logs[-12:]:
                print(f"  [{l.get('timestamp', '')[11:19]}] [{l.get('level', '')}] {l.get('message', '')}")
            print("=" * 80)
            print("Press Ctrl+C to exit monitor. (Background bake-off process will continue running)")

            if status == "completed":
                print("\n[DONE] Bake-off completed successfully.")
                break

        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            break
        except Exception:
            pass
        time.sleep(3)

if __name__ == "__main__":
    main()
