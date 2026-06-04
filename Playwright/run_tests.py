import argparse
import html
import os
import time
import unittest
from pathlib import Path

class HTMLTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append((test, "passed", ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append((test, "failed", self._exc_info_to_string(err, test)))

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append((test, "error", self._exc_info_to_string(err, test)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append((test, "skipped", reason))

class HTMLTestRunner(unittest.TextTestRunner):
    resultclass = HTMLTestResult

def build_html_report(result, started_at, duration):
    rows = []

    for test, status, details in result.records:
        status_class = {
            "passed": "passed",
            "failed": "failed",
            "error": "failed",
            "skipped": "skipped",
        }[status]
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(test))}</td>"
            f"<td class=\"{status_class}\">{html.escape(status.upper())}</td>"
            f"<td><pre>{html.escape(details)}</pre></td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>QIWI Wallet API Test Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #202124; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #5f6368; margin-bottom: 24px; }}
    .summary {{ display: flex; gap: 12px; margin-bottom: 24px; }}
    .badge {{ border: 1px solid #dadce0; border-radius: 6px; padding: 10px 14px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e0e0e0; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; }}
    pre {{ white-space: pre-wrap; margin: 0; }}
    .passed {{ color: #188038; font-weight: 700; }}
    .failed {{ color: #d93025; font-weight: 700; }}
    .skipped {{ color: #b06000; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>QIWI Wallet API Test Report</h1>
  <div class="meta">Started: {html.escape(started_at)} | Duration: {duration:.3f}s</div>
  <div class="summary">
    <div class="badge">Run: {result.testsRun}</div>
    <div class="badge">Failures: {len(result.failures)}</div>
    <div class="badge">Errors: {len(result.errors)}</div>
    <div class="badge">Skipped: {len(result.skipped)}</div>
  </div>
  <table>
    <thead>
      <tr><th>Test</th><th>Status</th><th>Details</th></tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
</body>
</html>
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", action="store_true", help="Write an HTML report.")
    parser.add_argument("--report", default="reports/test-report.html", help="HTML report path.")
    args = parser.parse_args()

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    started = time.time()
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    runner = HTMLTestRunner(verbosity=2)
    result = runner.run(suite)
    duration = time.time() - started

    if args.html:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_html_report(result, started_at, duration), encoding="utf-8")
        print(f"\nHTML report: {report_path.resolve()}")

    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()