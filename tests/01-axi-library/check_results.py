"""Print a one-line summary per cocotb result file and exit 1 on any failure or missing file."""
import sys
import xml.etree.ElementTree as ET

try:
    root = ET.parse(sys.argv[1]).getroot()
except Exception as e:
    print(f"  NO RESULTS ({e})")
    sys.exit(1)
bad = 0
n = 0
for tc in root.iter("testcase"):
    n += 1
    failed = tc.find("failure") is not None or tc.find("error") is not None
    skipped = tc.find("skipped") is not None
    print(f"  {'FAIL' if failed else ('skip' if skipped else 'pass')}  {tc.get('name')}")
    bad += failed
if n == 0:
    print("  NO TESTCASES")
    sys.exit(1)
sys.exit(1 if bad else 0)
