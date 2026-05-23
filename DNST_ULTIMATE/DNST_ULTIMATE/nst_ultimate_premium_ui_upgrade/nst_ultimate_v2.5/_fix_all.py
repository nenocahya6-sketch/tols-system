"""
NST FIX ALL SCRIPT v2
"""
import os
import re as re_mod

PROJECT = r"C:\Users\USER\Desktop\DNST_ULTIMATE\nst_ultimate_premium_ui_upgrade\nst_ultimate_v2.5"

NEED_CLEAN_OUTPUT_IMPORT = {
    "core/device_detector.py",
    "core/external_tools.py",
    "plugins/apple/__init__.py",
    "plugins/qualcomm/flasher.py",
    "plugins/stm32/__init__.py",
}

def fix_input_bugs(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    fixes = {
        'diagnostic.py': [
            ('choice = "".strip()', 'choice = input("  Pilih [0-5]: ").strip()'),
            ('port = "".strip()', 'port = input("  Port (COMx): ").strip()'),
        ],
        'flasher.py': [
            ('choice = "".strip()', 'choice = input("  Pilih [0-6]: ").strip()'),
            ('port = "".strip()', 'port = input("  Port (COMx): ").strip()'),
            ('addr_input = "".strip()', 'addr_input = input("  Address [0x08000000]: ").strip()'),
            ('size_input = "".strip()', 'size_input = input("  Size [65536]: ").strip()'),
        ],
        'reporter.py': [
            ('choice = "".strip()', 'choice = input("  Pilih report [1-N] atau Enter: ").strip()'),
        ],
        'firmware_verify.py': [
            ('filepath = "".strip().strip(\'"\').strip("\'")', 'filepath = input("  Path firmware: ").strip().strip(\'"\').strip("\'")'),
            ('choice = "".strip().lower()', 'choice = input("  Hash type (md5/sha256/skip): ").strip().lower()'),
        ],
        'driver_doctor.py': [
            ('if "".strip().lower() == \'y\':', 'if input("  Install ulang? (y/N): ").strip().lower() == \'y\':'),
        ],
    }

    fname = os.path.basename(filepath)
    if fname not in fixes:
        return content, False

    changed = False
    for old, new in fixes[fname]:
        if old in content:
            content = content.replace(old, new)
            changed = True

    return content, changed


def remove_clean_output_duplicate(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if filepath.endswith('core\\__init__.py') or filepath.endswith('core/__init__.py'):
        return content, False

    fname = os.path.basename(filepath)
    changed = False

    # Multiple pattern variants
    patterns = [
        # Pattern with clean_ansi + import re
        r'import re\n\nANSI_ESCAPE = re\.compile\(.*?\)\n\ndef clean_console_output\(text\):.*?return text\.strip\(\)\n\n\ndef clean_ansi\(text\):.*?return text\n\nimport re\n',
        # Pattern with clean_ansi no trailing import re
        r'import re\n\nANSI_ESCAPE = re\.compile\(.*?\)\n\ndef clean_console_output\(text\):.*?return text\.strip\(\)\n\ndef clean_ansi\(text\):.*?return text\n\n',
        # Pattern without clean_ansi, with import re
        r'import re\n\nANSI_ESCAPE = re\.compile\(.*?\)\n\ndef clean_console_output\(text\):.*?return text\.strip\(\)\n\nimport re\n',
        # Pattern without clean_ansi, no trailing import re
        r'import re\n\nANSI_ESCAPE = re\.compile\(.*?\)\n\ndef clean_console_output\(text\):.*?return text\.strip\(\)\n\n',
        # Pattern with from __future__
        r'from __future__ import annotations\n\nimport re\n\nANSI_ESCAPE = re\.compile\(.*?\)\n\ndef clean_console_output\(text\):.*?return text\.strip\(\)\n\n',
    ]

    for pattern in patterns:
        match = re_mod.search(pattern, content, re_mod.DOTALL)
        if match:
            content = content.replace(match.group(0), '')
            changed = True
            break

    if changed:
        print(f"  OK: {fname} removed clean_console_output")

    return content, changed


def add_import_from_core(filepath):
    rel = os.path.relpath(filepath, PROJECT)
    if rel not in NEED_CLEAN_OUTPUT_IMPORT:
        return None, False

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if 'from core import clean_console_output' in content:
        return content, False

    lines = content.split('\n')
    insert_at = 0

    for i, line in enumerate(lines):
        if line.startswith('from __future__'):
            continue
        if line.startswith('"""') or line.startswith("'''"):
            for j in range(i+1, len(lines)):
                if '"""' in lines[j] or "'''" in lines[j]:
                    insert_at = j + 1
                    break
            if insert_at:
                break
        elif line.strip() and not line.startswith('#'):
            insert_at = i
            break

    for i, line in enumerate(lines):
        if 'from core import' in line:
            if 'clean_console_output' not in line:
                lines[i] = line.rstrip() + ', clean_console_output'
                content = '\n'.join(lines)
                print(f"  OK: {rel} added to core import")
                return content, True
            return content, False

    lines.insert(insert_at, 'from core import clean_console_output\n')
    content = '\n'.join(lines)
    print(f"  OK: {rel} added import from core")
    return content, True


def remove_duplicate_import_re(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    lines = content.split('\n')
    import_re_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'import re' or stripped == 'import re  ':
            import_re_indices.append(i)

    if len(import_re_indices) <= 1:
        return content, False

    fname = os.path.basename(filepath)
    removed = 0
    for idx in reversed(import_re_indices[1:]):
        context_before = '\n'.join(lines[max(0,idx-2):idx])
        if '"""' in context_before or "'''" in context_before:
            continue
        if idx > 0 and ('def clean_console_output' in lines[idx-1] or 'ANSI_ESCAPE' in lines[idx-1]):
            continue
        del lines[idx]
        removed += 1

    if removed:
        content = '\n'.join(lines)
        print(f"  OK: {fname} removed {removed} duplicate import re")
        return content, True

    return content, False


def main():
    py_files = []
    for root, dirs, files in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d not in ('build', '__pycache__', '.pytest_cache', 'dist', 'node_modules', 'logs', 'tools', 'backups', 'reports', 'firmware')]
        for f in files:
            if f.endswith('.py') and not f.startswith('_fix'):
                py_files.append(os.path.join(root, f))

    py_files.sort()
    print(f"Found {len(py_files)} .py files")

    # Phase 1
    print("\n[PHASE 1: INPUT BUGS]")
    count = 0
    for fp in py_files:
        content, changed = fix_input_bugs(fp)
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
            count += 1
    print(f"  Done: {count} files")

    # Phase 2
    print("\n[PHASE 2: REMOVE DUPLICATE clean_console_output]")
    count = 0
    for fp in py_files:
        content, changed = remove_clean_output_duplicate(fp)
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
            count += 1
    print(f"  Done: {count} files")

    # Phase 3
    print("\n[PHASE 3: ADD import from core]")
    count = 0
    for fp in py_files:
        content, changed = add_import_from_core(fp)
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
            count += 1
    print(f"  Done: {count} files")

    # Phase 4
    print("\n[PHASE 4: REMOVE DUPLICATE import re]")
    count = 0
    for fp in py_files:
        content, changed = remove_duplicate_import_re(fp)
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
            count += 1
    print(f"  Done: {count} files")

    print("\n[DONE]")

if __name__ == "__main__":
    main()
