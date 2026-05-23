"""
NST FIX PHASE 3 - Add imports to files that need clean_console_output
"""
import os
import sys

PROJECT = r"C:\Users\USER\Desktop\DNST_ULTIMATE\nst_ultimate_premium_ui_upgrade\nst_ultimate_v2.5"

FILES_NEED_IMPORT = [
    "core/device_detector.py",
    "core/external_tools.py",
    "plugins/apple/__init__.py",
    "plugins/qualcomm/flasher.py",
    "plugins/stm32/__init__.py",
]

for fname in FILES_NEED_IMPORT:
    fpath = os.path.join(PROJECT, fname)
    if not os.path.exists(fpath):
        print(f"NOT FOUND: {fname}")
        continue
    
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Check if already imported
    if 'from core import clean_console_output' in content:
        print(f"ALREADY HAS IMPORT: {fname}")
        continue
    
    # Also check if function is still defined locally
    if 'def clean_console_output' in content:
        print(f"STILL HAS LOCAL DEF: {fname} - skipping import")
        continue
    
    lines = content.split('\n')
    insert_at = 0
    
    # Find where to insert - after docstring or __future__ imports
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
    
    # Check if there's already a from core import line
    for i, line in enumerate(lines):
        if 'from core import' in line:
            if 'clean_console_output' not in line:
                lines[i] = line.rstrip() + ', clean_console_output'
            content = '\n'.join(lines)
            break
    else:
        lines.insert(insert_at, 'from core import clean_console_output\n')
        content = '\n'.join(lines)
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"FIXED: {fname}")

print("\nDONE")
