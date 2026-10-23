#!/usr/bin/env python3
"""Run the test suite.

    python3 tests/run_tests.py                  Python implementation; PowerShell too when it is found
    python3 tests/run_tests.py --impl py        Python only
    python3 tests/run_tests.py --impl ps1       PowerShell only
    python3 tests/run_tests.py --impl both      both (a missing runtime is skipped, or a failure when CI=true)
    python3 tests/run_tests.py -v -k report     verbose; only tests whose name contains "report"
    python3 tests/run_tests.py --bless          write tests/fixtures/cases/*/expected from the Python implementation

PowerShell is found as powershell.exe on Windows, else pwsh on PATH; the environment variable SPANHARNESS_PWSH names
another executable. With CI=true a missing runtime is a failure, not a skip.
"""
import argparse
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the spanharness tests.")
    ap.add_argument("--impl", choices=("py", "ps1", "both"), help="which implementation to test (default: py, plus ps1 when PowerShell is found)")
    ap.add_argument("-v", "--verbose", action="store_true", help="one line per test")
    ap.add_argument("-k", dest="patterns", action="append", metavar="PATTERN", help="only tests whose name contains PATTERN (repeatable)")
    ap.add_argument("-f", "--failfast", action="store_true", help="stop at the first failure")
    ap.add_argument("--bless", action="store_true", help="rewrite the expected files of the conformance cases from the Python implementation")
    args = ap.parse_args(argv)

    if args.impl:
        os.environ["SPANHARNESS_IMPLS"] = args.impl
    if args.bless:
        os.environ["SPANHARNESS_BLESS"] = "1"
        os.environ.setdefault("SPANHARNESS_IMPLS", "py")
    sys.path.insert(0, HERE)

    import test_conformance as conf
    chosen = sorted(conf.wanted())
    note = []
    for impl in chosen:
        if conf.impl_command(impl) is None:
            note.append("%s cannot run here" % impl)
    print("implementations: %s%s" % (", ".join(chosen), " (" + "; ".join(note) + ")" if note else ""))

    loader = unittest.TestLoader()
    if args.patterns:
        loader.testNamePatterns = ["*%s*" % p for p in args.patterns]
    suite = loader.discover(HERE, pattern="test_*.py", top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1, failfast=args.failfast).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
