# Workflow changes needed for branch `test-output-check`

To be applied to `.github/workflows/unit_tests.yml` during integration (this branch does not edit `.github/`).

Printed output is now checked per test (`test/framework/output_check.py`), so the grep on the suite log goes away.

**Careful:** on `develop`, `test.framework.suite` always exits 0, and the step has no `pipefail`, so the grep is
also what makes CI fail on *test failures* (`FAIL: ...`/`ERROR: ...` lines match it). This branch makes `suite.py`
exit 1 on failure; the workflow must check that exit status (via `PIPESTATUS`), or failing tests would go unnoticed.

## Before (step "run test suite", inside the `for module_syntax` loop)

```bash
            # run test suite
            python -O -m test.framework.suite 2>&1 | tee test_framework_suite.log
            # try and make sure output of running tests is clean (no printed messages/warnings)
            IGNORE_PATTERNS="no GitHub token available"
            IGNORE_PATTERNS+="|skipping SvnRepository test"
            IGNORE_PATTERNS+="|requires Lmod as modules tool"
            IGNORE_PATTERNS+="|stty: 'standard input': Inappropriate ioctl for device"
            IGNORE_PATTERNS+="|CryptographyDeprecationWarning: Python 3.[78]"
            IGNORE_PATTERNS+="|from cryptography.* import "
            IGNORE_PATTERNS+="|Blowfish"
            IGNORE_PATTERNS+="|GC3Pie not available, skipping test"
            IGNORE_PATTERNS+="|CryptographyDeprecationWarning: TripleDES has been moved"
            IGNORE_PATTERNS+="|algorithms.TripleDES"
            # ignore lines with only successful ('.') and skipped ('s') tests
            IGNORE_PATTERNS+="|^[\.s]+$"
            # '|| true' is needed to avoid that GitHub Actions stops the job on non-zero exit of grep (i.e. when there are no matches)
            PRINTED_MSG=$(egrep -v "${IGNORE_PATTERNS}" test_framework_suite.log | grep '\.\n*[A-Za-z]' || true)
            test "x$PRINTED_MSG" = "x" || (echo "ERROR: Found printed messages in output of test suite" && echo "${PRINTED_MSG}" && exit 1)
          done
```

## After

```bash
            # run test suite;
            # tests that print unexpected output to stdout/stderr fail (see test/framework/output_check.py)
            python -O -m test.framework.suite 2>&1 | tee test_framework_suite.log
            # exit code of the test suite, not of 'tee'
            test "${PIPESTATUS[0]}" -eq 0 || (echo "ERROR: test suite failed with ${module_syntax} module syntax" && exit 1)
          done
```

The allowlist that used to be `IGNORE_PATTERNS` now lives in `ALLOWED_OUTPUT_PATTERNS` in
`test/framework/output_check.py`.
