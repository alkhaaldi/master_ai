#!/usr/bin/env python3
"""
test_patch.py - Test the apply_text_patch system on a dummy Python file.
Run from master_ai root: python3 _tools/examples/test_patch.py
"""
import sys, os, tempfile, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from _tools.patchers.apply_text_patch import apply_patch, apply_patches

PASS = 0
FAIL = 0

def test(name, result, expect_success):
    global PASS, FAIL
    ok = result.success == expect_success
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {name}: {result.message}")
    return ok

SAMPLE_PY = "# Test file\ndef hello():\n    print(\"Hello World\")\n\ndef add(a, b):\n    return a + b\n\nVERSION = \"1.0.0\"\n"

def main():
    print("=" * 60)
    print("Patch System Test Suite")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    tmp.write(SAMPLE_PY)
    tmp.close()
    tmp_path = tmp.name
    print(f"\nTemp file: {tmp_path}\n")

    print("Test 1: Simple text replace")
    r = apply_patch(tmp_path, 'print("Hello World")', 'print("Hello Master AI")', backup=True)
    test("Replace greeting", r, True)
    with open(tmp_path) as f:
        assert "Hello Master AI" in f.read(), "Content not updated!"

    print("\nTest 2: Dry run (no modification)")
    r = apply_patch(tmp_path, 'VERSION = "1.0.0"', 'VERSION = "2.0.0"', dry_run=True)
    test("Dry run reports match", r, True)
    with open(tmp_path) as f:
        assert 'VERSION = "1.0.0"' in f.read(), "Dry run modified file!"

    print("\nTest 3: old_text not found")
    r = apply_patch(tmp_path, "THIS_DOES_NOT_EXIST", "replacement")
    test("Not found returns failure", r, False)

    print("\nTest 4: Bad patch causes syntax error - should auto-revert")
    r = apply_patch(tmp_path, "def add(a, b):", "def add(a, b:", backup=True)
    test("Syntax error detected and reverted", r, False)
    with open(tmp_path) as f:
        content = f.read()
        assert "def add(a, b):" in content, "File not reverted after syntax error!"

    print("\nTest 5: Multiple patches at once")
    r = apply_patches(tmp_path, [
        ('VERSION = "1.0.0"', 'VERSION = "2.0.0"'),
        ("return a + b", "return a + b  # patched"),
    ], backup=True)
    test("Multi-patch applied", r, True)

    print("\nTest 6: Non-Python file (YAML)")
    tmp_yaml = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    tmp_yaml.write("key: old_value\nother: 123\n")
    tmp_yaml.close()
    r = apply_patch(tmp_yaml.name, "key: old_value", "key: new_value", backup=True)
    test("YAML patch applied", r, True)

    os.unlink(tmp_path)
    os.unlink(tmp_yaml.name)
    for bak in glob.glob(f"{tmp_path}.bak.*"):
        os.unlink(bak)
    for bak in glob.glob(f"{tmp_yaml.name}.bak.*"):
        os.unlink(bak)

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed out of {PASS+FAIL}")
    print("=" * 60)
    return FAIL == 0

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
