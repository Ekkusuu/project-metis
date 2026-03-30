from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
import webbrowser


def is_ready(url: str, timeout: float) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ProjectMetis/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a URL once all readiness checks succeed.")
    parser.add_argument("--url", required=True, help="URL to open in the browser")
    parser.add_argument("--wait-for", action="append", dest="wait_for", default=[], help="Readiness URL to poll; can be provided multiple times")
    parser.add_argument("--timeout", type=float, default=300.0, help="Maximum total time to wait in seconds")
    parser.add_argument("--interval", type=float, default=1.5, help="Polling interval in seconds")
    parser.add_argument("--request-timeout", type=float, default=2.0, help="Per-request timeout in seconds")
    args = parser.parse_args()

    wait_urls = args.wait_for or [args.url]
    deadline = time.time() + max(args.timeout, 1.0)

    while time.time() < deadline:
        if all(is_ready(url, args.request_timeout) for url in wait_urls):
            webbrowser.open(args.url, new=2)
            return 0
        time.sleep(max(args.interval, 0.2))

    print(f"Timed out waiting for: {', '.join(wait_urls)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
