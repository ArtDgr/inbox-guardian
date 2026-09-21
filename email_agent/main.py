import argparse
from .config import load_config
from .monitor import run_once, run_daemon

def main():
    parser = argparse.ArgumentParser(description="Email Copilot Agent — monitor ALL Outlook folders and highlight urgent mail")
    parser.add_argument("--once", action="store_true", help="single sweep (default)")
    parser.add_argument("--daemon", action="store_true", help="poll loop")
    parser.add_argument("--dry-run", action="store_true", help="do not write flags/categories to Outlook")
    args = parser.parse_args()

    cfg = load_config()
    # dry-run override
    if args.dry_run:
        cfg["env"]["allow_write"] = False

    if args.daemon:
        run_daemon(cfg)
    else:
        highlights = run_once(cfg, dry_run=args.dry_run or not cfg["env"]["allow_write"])
        # exit code 2 if urgent found (useful for alerting)
        urgent_count = sum(1 for h in highlights if h["label"] == "urgent")
        if urgent_count > 0:
            print(f"\n[!] {urgent_count} URGENT emails require immediate attention")
        else:
            print("\nNo urgent mail — inbox clear")

if __name__ == "__main__":
    main()
