#!/usr/bin/env python3
"""
apply_text_patch.py — Safe Python file patcher for Master AI.

Usage:
    python3 apply_text_patch.py <file> --old "OLD_TEXT" --new "NEW_TEXT" [--backup] [--dry-run]
    
    Or from Python:
        from _tools.patchers.apply_text_patch import apply_patch, apply_patches
        result = apply_patch("/path/to/file.py", old_text, new_text, backup=True)
        result = apply_patches("/path/to/file.py", [(old1, new1), (old2, new2)])
"""
import sys, os, shutil, ast, argparse, datetime, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PatchResult:
    """Result of a patch operation."""
    def __init__(self, success, file_path, message, backup_path=None, changes=0):
        self.success = success
        self.file_path = file_path
        self.message = message
        self.backup_path = backup_path
        self.changes = changes

    def to_dict(self):
        return {
            "success": self.success,
            "file": self.file_path,
            "message": self.message,
            "backup": self.backup_path,
            "changes": self.changes,
        }

    def __repr__(self):
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.file_path}: {self.message}"


def _make_backup(file_path):
    """Create timestamped backup, return backup path."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.bak.patch_{ts}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def _syntax_check(file_path):
    """Check Python syntax. Returns (ok, error_message)."""
    if not file_path.endswith(".py"):
        return True, "Not a Python file, skipping syntax check"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source, filename=file_path)
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def _restore_backup(file_path, backup_path):
    """Restore file from backup."""
    if backup_path and os.path.exists(backup_path):
        shutil.copy2(backup_path, file_path)
        return True
    return False


def apply_patch(file_path, old_text, new_text, backup=True, dry_run=False):
    """
    Apply a single text replacement patch to a file.
    
    Args:
        file_path: Path to the file to patch
        old_text: Exact text to find and replace
        new_text: Replacement text
        backup: Create backup before patching (default True)
        dry_run: If True, only check if patch would apply without modifying
    
    Returns:
        PatchResult object
    """
    # Resolve relative paths
    if not os.path.isabs(file_path):
        file_path = os.path.join(BASE_DIR, file_path)

    # Check file exists
    if not os.path.exists(file_path):
        return PatchResult(False, file_path, f"File not found: {file_path}")

    # Read current content
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check old_text exists
    count = content.count(old_text)
    if count == 0:
        return PatchResult(False, file_path, "old_text not found in file")
    if count > 1:
        return PatchResult(False, file_path, f"old_text found {count} times — must be unique (found {count})")

    # Dry run — just report
    if dry_run:
        return PatchResult(True, file_path, f"Dry run: patch would apply (1 match found)", changes=1)

    # Create backup
    backup_path = None
    if backup:
        backup_path = _make_backup(file_path)

    # Apply patch
    new_content = content.replace(old_text, new_text, 1)

    # Write patched content
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Syntax check for Python files
    syntax_ok, syntax_msg = _syntax_check(file_path)
    if not syntax_ok:
        # Restore backup
        if backup_path:
            _restore_backup(file_path, backup_path)
            return PatchResult(False, file_path,
                f"Syntax check FAILED after patch — reverted to backup. {syntax_msg}",
                backup_path=backup_path)
        else:
            return PatchResult(False, file_path,
                f"Syntax check FAILED after patch — NO BACKUP to restore! {syntax_msg}")

    return PatchResult(True, file_path, f"Patch applied. {syntax_msg}",
                       backup_path=backup_path, changes=1)


def apply_patches(file_path, patches, backup=True, dry_run=False):
    """
    Apply multiple patches to a single file atomically.
    
    Args:
        file_path: Path to the file
        patches: List of (old_text, new_text) tuples
        backup: Create backup before patching
        dry_run: Only check without modifying
    
    Returns:
        PatchResult object
    """
    if not os.path.isabs(file_path):
        file_path = os.path.join(BASE_DIR, file_path)

    if not os.path.exists(file_path):
        return PatchResult(False, file_path, f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Pre-validate all patches
    for i, (old_text, new_text) in enumerate(patches):
        count = content.count(old_text)
        if count == 0:
            return PatchResult(False, file_path, f"Patch #{i+1}: old_text not found")
        if count > 1:
            return PatchResult(False, file_path, f"Patch #{i+1}: old_text found {count} times — must be unique")

    if dry_run:
        return PatchResult(True, file_path, f"Dry run: all {len(patches)} patches would apply",
                           changes=len(patches))

    # Backup
    backup_path = None
    if backup:
        backup_path = _make_backup(file_path)

    # Apply all patches sequentially
    new_content = content
    for old_text, new_text in patches:
        new_content = new_content.replace(old_text, new_text, 1)

    # Write
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Syntax check
    syntax_ok, syntax_msg = _syntax_check(file_path)
    if not syntax_ok:
        if backup_path:
            _restore_backup(file_path, backup_path)
            return PatchResult(False, file_path,
                f"Syntax check FAILED — reverted to backup. {syntax_msg}",
                backup_path=backup_path)
        else:
            return PatchResult(False, file_path,
                f"Syntax check FAILED — NO BACKUP! {syntax_msg}")

    return PatchResult(True, file_path, f"All {len(patches)} patches applied. {syntax_msg}",
                       backup_path=backup_path, changes=len(patches))


# ── CLI ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Safe Python file patcher")
    parser.add_argument("file", help="File to patch")
    parser.add_argument("--old", required=True, help="Text to find")
    parser.add_argument("--new", required=True, help="Replacement text")
    parser.add_argument("--backup", action="store_true", default=True, help="Create backup (default: True)")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup")
    parser.add_argument("--dry-run", action="store_true", help="Check only, don't modify")
    args = parser.parse_args()

    backup = not args.no_backup
    result = apply_patch(args.file, args.old, args.new, backup=backup, dry_run=args.dry_run)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
