"""
Test that library modules in src/forecasting/ do not contain debug __main__ blocks.

Per V5.4.3 PHASE 1: Library modules should be import-clean and not contain
path-specific examples or sys.path hacks.
"""

from pathlib import Path


def test_no_sys_path_insert_in_library():
    """Library modules must not contain sys.path.insert()"""
    src_dir = Path(__file__).parent.parent / "src" / "forecasting"
    violations = []

    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text()
        if "sys.path.insert" in content:
            violations.append(str(py_file.relative_to(src_dir.parent)))

    assert len(violations) == 0, f"Found sys.path.insert in library modules: {violations}"


def test_no_absolute_paths_in_library():
    """Library modules must not contain /home/ubuntu/ absolute paths"""
    src_dir = Path(__file__).parent.parent / "src" / "forecasting"
    violations = []

    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text()
        if "/home/ubuntu/" in content:
            violations.append(str(py_file.relative_to(src_dir.parent)))

    assert len(violations) == 0, f"Found /home/ubuntu/ paths in library modules: {violations}"


def test_no_main_blocks_in_library():
    """
    Library modules must not contain if __name__ == "__main__": blocks.

    Exception: run_daily.py is the CLI entry point, so it's allowed.
    """
    src_dir = Path(__file__).parent.parent / "src" / "forecasting"
    violations = []

    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        # Allow run_daily.py (it's the CLI entry point)
        if py_file.name == "run_daily.py":
            continue

        content = py_file.read_text()
        if 'if __name__ == "__main__":' in content:
            violations.append(str(py_file.relative_to(src_dir.parent)))

    assert len(violations) == 0, f"Found __main__ blocks in library modules: {violations}"
