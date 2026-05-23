"""
Fix All Remaining Bugs Script v2
=================================
1. Bug #1: Remove duplicate clean_ansi() definitions
2. Bug #1b: Remove from __future__ import annotations
3. Bug #3: Change bare except: to except Exception:
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

FILES_TO_PROCESS = [
    # Files with clean_ansi() duplicates
    'core/anti_brick.py',
    'core/device_detector.py',
    'core/device_validator.py',
    'core/driver_doctor.py',
    'core/emergency.py',
    'core/firmware_verify.py',
    'core/flash_simulator.py',
    'core/mode_scanner.py',
    'core/safety.py',
    'core/update_checker.py',
    'core/nst_android.py',
    'core/nst_iphone.py',
    # Files with from __future__ import annotations
    'core/anti_brick.py', 'core/device_validator.py', 'core/driver_doctor.py',
    'core/external_tools.py', 'core/flash_simulator.py', 'core/mode_scanner.py',
    'core/device_database.py', 'plugins/apple/__init__.py', 'plugins/__init__.py',
    'plugins/unisoc/__init__.py', 'plugins/qualcomm/__init__.py',
    'plugins/qualcomm/flasher.py', 'plugins/stm32/__init__.py',
    'plugins/mediatek/__init__.py', 'plugins/loader.py', 'plugins/samsung/__init__.py',
    'plugins/kirin/__init__.py',
    # Files with bare except:
    'core/auto_recovery.py', 'core/nst_android.py', 'core/nst_iphone.py',
]


def remove_clean_ansi(content):
    """Remove def clean_ansi(text): function definition using line-based approach."""
    lines = content.split('\n')
    result = []
    skip_until_empty = False
    in_clean_ansi = False
    brace_count = 0
    
    for line in lines:
        stripped = line.strip()
        
        # Detect start of clean_ansi function
        if stripped.startswith('def clean_ansi(') and stripped.endswith(':'):
            in_clean_ansi = True
            continue
        
        if in_clean_ansi:
            # The function body lines all start with 4 spaces (or more for continuation)
            # We need to detect the end - when we hit a non-indented line
            if stripped == '':
                # Keep consuming empty lines
                continue
            elif line.startswith('    '):
                # Still in function body
                continue
            else:
                # End of function - process this line normally
                in_clean_ansi = False
                # Don't skip this line
        
        if not in_clean_ansi:
            result.append(line)
    
    return '\n'.join(result)


def remove_future_annotations(content):
    """Remove 'from __future__ import annotations' line."""
    lines = content.split('\n')
    filtered = [l for l in lines if l.strip() != 'from __future__ import annotations']
    return '\n'.join(filtered)


def fix_bare_except(content):
    """Replace bare except: with except Exception:"""
    lines = content.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped == 'except:':
            # Preserve the original indentation
            indent = line[:len(line) - len(line.lstrip())]
            result.append(indent + 'except Exception:')
        else:
            result.append(line)
    return '\n'.join(result)


def main():
    print("=" * 60)
    print("FIX ALL REMAINING BUGS")
    print("=" * 60)
    print()
    
    # Remove duplicates from FILES_TO_PROCESS while preserving order
    seen = set()
    unique_files = []
    for f in FILES_TO_PROCESS:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    
    total_modified = 0
    
    for rel_path in unique_files:
        filepath = os.path.join(BASE, rel_path)
        if not os.path.exists(filepath):
            print(f"  [SKIP] {rel_path} - file not found")
            continue
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            original = f.read()
        
        content = original
        changes = []
        
        # 1. Remove clean_ansi() duplicate
        cleaned = remove_clean_ansi(content)
        if cleaned != content:
            # Count how many clean_ansi definitions were removed
            orig_count = content.count('def clean_ansi(')
            new_count = cleaned.count('def clean_ansi(')
            removed = orig_count - new_count
            if removed > 0:
                changes.append(f"clean_ansi() removed ({removed}x)")
                content = cleaned
        
        # 2. Remove from __future__ import annotations
        cleaned = remove_future_annotations(content)
        if cleaned != content:
            changes.append("from __future__ import annotations removed")
            content = cleaned
        
        # 3. Fix bare except:
        orig_bare = sum(1 for line in content.split('\n') if line.strip() == 'except:')
        cleaned = fix_bare_except(content)
        new_bare = sum(1 for line in cleaned.split('\n') if line.strip() == 'except:')
        fixed = orig_bare - new_bare
        if fixed > 0:
            changes.append(f"bare except: -> except Exception: ({fixed}x)")
            content = cleaned
        
        if changes:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  [OK] {rel_path}: {', '.join(changes)}")
            total_modified += 1
        else:
            print(f"  [--] {rel_path}: no changes needed")
    
    print()
    print("=" * 60)
    print(f"Total files modified: {total_modified}")
    print("=" * 60)


if __name__ == '__main__':
    main()
