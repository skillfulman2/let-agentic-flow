"""
Evaluation harness for autobuilder experiments.
Builds the SvelteKit app, starts preview server, runs Playwright tests,
runs Lighthouse audit, and computes a composite score.

Usage:
    python evaluate.py

Score formula (0-100):
    Playwright pass rate gates the score (any failure caps at 50).
    Lighthouse categories are weighted:
        performance:    25%
        accessibility:  25%
        best-practices: 25%
        seo:            25%
    Final = lighthouse_composite if all tests pass,
            else min(50, lighthouse_composite) * (tests_passed / tests_total)
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

AUTOBUILDER_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(AUTOBUILDER_DIR, "app")

BUILD_TIMEOUT = 60
SERVER_STARTUP_TIMEOUT = 15
TEST_TIMEOUT = 120
LIGHTHOUSE_TIMEOUT = 90

# Lighthouse category weights (must sum to 1.0)
LIGHTHOUSE_WEIGHTS = {
    "performance": 0.25,
    "accessibility": 0.25,
    "best-practices": 0.25,
    "seo": 0.25,
}

# Playwright's chromium — discovered at startup
CHROME_PATH = None


def find_chrome():
    """Find Playwright's bundled Chromium."""
    import glob
    patterns = [
        os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-linux/chrome"),
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    return None


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def build_app():
    """Run npm run build. Returns (success, build_time_ms)."""
    t0 = time.time()
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT,
        )
        build_time_ms = int((time.time() - t0) * 1000)
        if result.returncode != 0:
            print(f"Build failed:\n{result.stderr}")
            return False, build_time_ms
        return True, build_time_ms
    except subprocess.TimeoutExpired:
        build_time_ms = int((time.time() - t0) * 1000)
        print(f"Build timed out after {BUILD_TIMEOUT}s")
        return False, build_time_ms


def start_preview_server(port):
    """Start npm run preview on given port. Returns subprocess."""
    proc = subprocess.Popen(
        ["npm", "run", "preview", "--", "--port", str(port)],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.time() + SERVER_STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return proc
        except (ConnectionRefusedError, OSError):
            if proc.poll() is not None:
                print(f"Preview server exited with code {proc.returncode}")
                return None
            time.sleep(0.3)
    print("Preview server failed to start within timeout")
    kill_process(proc)
    return None


def kill_process(proc):
    """Kill process and its process group."""
    if proc is None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass


def run_playwright_tests(port):
    """Run Playwright tests against the server. Returns parsed JSON results."""
    env = os.environ.copy()
    env["BASE_URL"] = f"http://localhost:{port}"

    result = subprocess.run(
        ["npx", "playwright", "test", "--reporter", "json"],
        cwd=AUTOBUILDER_DIR,
        capture_output=True,
        text=True,
        timeout=TEST_TIMEOUT,
        env=env,
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Failed to parse Playwright JSON output")
        if result.stdout:
            print(f"stdout (first 500 chars): {result.stdout[:500]}")
        if result.stderr:
            print(f"stderr (first 500 chars): {result.stderr[:500]}")
        return None


def count_playwright_results(results):
    """Count passed/failed from Playwright JSON results."""
    if results is None:
        return 0, 0, 0

    passed = 0
    failed = 0

    def count_specs(suite):
        nonlocal passed, failed
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    if result.get("status") == "passed":
                        passed += 1
                    else:
                        failed += 1
        for child in suite.get("suites", []):
            count_specs(child)

    for suite in results.get("suites", []):
        count_specs(suite)

    return passed, failed, passed + failed


def run_lighthouse(port):
    """Run Lighthouse audit. Returns dict of category scores (0-100) or None."""
    if CHROME_PATH is None:
        print("Lighthouse: no Chrome found, skipping")
        return None

    url = f"http://localhost:{port}"
    cmd = [
        "npx", "lighthouse", url,
        "--chrome-flags=--headless",
        f"--chrome-path={CHROME_PATH}",
        "--output", "json",
        "--quiet",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=AUTOBUILDER_DIR,
            capture_output=True,
            text=True,
            timeout=LIGHTHOUSE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"Lighthouse timed out after {LIGHTHOUSE_TIMEOUT}s")
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Lighthouse: failed to parse JSON output")
        if result.stderr:
            print(f"stderr (first 300 chars): {result.stderr[:300]}")
        return None

    categories = data.get("categories", {})
    scores = {}
    for name, cat in categories.items():
        raw = cat.get("score")
        scores[name] = round(raw * 100, 1) if raw is not None else 0.0
    return scores


def compute_composite(pw_passed, pw_total, lighthouse_scores):
    """
    Composite score (0-100).

    If all Playwright tests pass, score = Lighthouse weighted average.
    If any Playwright test fails, score is capped at 50 and scaled by pass rate.
    If Lighthouse is unavailable, falls back to Playwright pass rate.
    """
    if pw_total == 0:
        return 0.0

    pw_rate = pw_passed / pw_total

    if lighthouse_scores is None:
        return round(pw_rate * 100, 1)

    lh_composite = 0.0
    for category, weight in LIGHTHOUSE_WEIGHTS.items():
        lh_composite += lighthouse_scores.get(category, 0.0) * weight

    if pw_passed == pw_total:
        return round(lh_composite, 1)
    else:
        return round(min(50.0, lh_composite) * pw_rate, 1)


def main():
    global CHROME_PATH
    CHROME_PATH = find_chrome()
    t_start = time.time()

    # Step 1: Build
    print("Building app...")
    build_ok, build_time_ms = build_app()
    if not build_ok:
        print("---")
        print(f"score:            0.0")
        print(f"build_time_ms:    {build_time_ms}")
        print(f"total_seconds:    {time.time() - t_start:.1f}")
        print(f"tests_passed:     0")
        print(f"tests_failed:     0")
        print(f"tests_total:      0")
        print(f"lh_performance:   0.0")
        print(f"lh_accessibility: 0.0")
        print(f"lh_best_practices: 0.0")
        print(f"lh_seo:           0.0")
        sys.exit(1)
    print(f"Build succeeded in {build_time_ms}ms")

    # Step 2: Start preview server
    port = find_free_port()
    print(f"Starting preview server on port {port}...")
    server = start_preview_server(port)
    if server is None:
        print("---")
        print(f"score:            0.0")
        print(f"build_time_ms:    {build_time_ms}")
        print(f"total_seconds:    {time.time() - t_start:.1f}")
        print(f"tests_passed:     0")
        print(f"tests_failed:     0")
        print(f"tests_total:      0")
        print(f"lh_performance:   0.0")
        print(f"lh_accessibility: 0.0")
        print(f"lh_best_practices: 0.0")
        print(f"lh_seo:           0.0")
        sys.exit(1)

    try:
        # Step 3: Run Playwright tests
        print("Running Playwright tests...")
        pw_results = run_playwright_tests(port)
        pw_passed, pw_failed, pw_total = count_playwright_results(pw_results)
        print(f"Playwright: {pw_passed}/{pw_total} passed")

        # Step 4: Run Lighthouse
        print("Running Lighthouse audit...")
        lh_scores = run_lighthouse(port)
        if lh_scores:
            for cat, val in lh_scores.items():
                print(f"  {cat}: {val}")

        # Step 5: Compute composite score
        score = compute_composite(pw_passed, pw_total, lh_scores)
        total_seconds = time.time() - t_start

        lh = lh_scores or {}

        # Step 6: Print summary
        print("---")
        print(f"score:            {score:.1f}")
        print(f"build_time_ms:    {build_time_ms}")
        print(f"total_seconds:    {total_seconds:.1f}")
        print(f"tests_passed:     {pw_passed}")
        print(f"tests_failed:     {pw_failed}")
        print(f"tests_total:      {pw_total}")
        print(f"lh_performance:   {lh.get('performance', 0.0)}")
        print(f"lh_accessibility: {lh.get('accessibility', 0.0)}")
        print(f"lh_best_practices: {lh.get('best-practices', 0.0)}")
        print(f"lh_seo:           {lh.get('seo', 0.0)}")

    finally:
        kill_process(server)


if __name__ == "__main__":
    main()
