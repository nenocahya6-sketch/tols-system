#!/usr/bin/env python3
"""
CREATE DESKTOP SHORTCUT - NEAR CELL SYSTEM
Membuat shortcut di desktop dengan icon menarik
"""
import os
import sys
import platform

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def create_windows_shortcut():
    """Buat shortcut Windows (.bat + VBS)"""
    desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\Public"), "Desktop")
    bat_path = os.path.join(desktop, "Near Cell System.bat")
    vbs_path = os.path.join(desktop, "Near Cell System.launcher.vbs")

    # Batch file to run Python
    python_exe = sys.executable
    launcher_script = os.path.join(PROJECT_DIR, "near_cell_system.py")

    bat_content = f'''@echo off
title NEAR CELL SYSTEM - Professional Phone Service Tool
color 0B
echo.
echo  ==========================================
echo        NEAR CELL SYSTEM
echo   Professional Phone Service Tool
echo  ==========================================
echo.
echo  Initializing...
echo.
cd /d "{PROJECT_DIR}"
"{python_exe}" "{launcher_script}"
pause
'''
    with open(bat_path, 'w') as f:
        f.write(bat_content)

    # VBS for normal console launch
    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "{bat_path}" & Chr(34), 1
Set WshShell = Nothing
'''
    with open(vbs_path, 'w') as f:
        f.write(vbs_content)

    print(f"[OK] Shortcut created: {bat_path}")
    print(f"[OK] Launcher: {vbs_path}")
    
    return bat_path


def create_linux_shortcut():
    """Buat shortcut Linux (.desktop)"""
    desktop = os.path.join(os.environ.get("HOME", "/tmp"), "Desktop")
    os.makedirs(desktop, exist_ok=True)

    desktop_entry_path = os.path.join(desktop, "near-cell-system.desktop")
    python_exe = sys.executable
    launcher_script = os.path.join(PROJECT_DIR, "near_cell_system.py")

    desktop_entry = f'''[Desktop Entry]
Version=1.0
Type=Application
Name=Near Cell System
Comment=Professional Phone Service Toolkit - Scan, Diagnose, Flash, Unlock, Root
Exec={python_exe} {launcher_script}
Icon={PROJECT_DIR}/near_cell_icon.png
Terminal=true
Categories=Utility;Development;
Keywords=phone;android;iphone;flash;service;repair;
'''
    with open(desktop_entry_path, 'w') as f:
        f.write(desktop_entry)
    os.chmod(desktop_entry_path, 0o755)

    print(f"[OK] Shortcut created: {desktop_entry_path}")
    return desktop_entry_path


def create_near_cell_icon():
    """Create a simple HTML-based icon for the shortcut"""
    icon_path = os.path.join(PROJECT_DIR, "near_cell_icon.png")
    
    # Buat file SVG sederhana sebagai icon
    svg_path = os.path.join(PROJECT_DIR, "near_cell_icon.svg")
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#1a237e"/>
      <stop offset="100%" style="stop-color:#0d47a1"/>
    </linearGradient>
    <linearGradient id="icon" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#00bcd4"/>
      <stop offset="100%" style="stop-color:#0097a7"/>
    </linearGradient>
  </defs>
  <!-- Background circle -->
  <circle cx="64" cy="64" r="62" fill="url(#bg)" stroke="#00bcd4" stroke-width="2"/>
  <!-- Phone icon -->
  <rect x="44" y="24" width="40" height="80" rx="8" fill="url(#icon)"/>
  <!-- Screen -->
  <rect x="48" y="32" width="32" height="56" rx="3" fill="#e3f2fd"/>
  <!-- Signal bars -->
  <rect x="22" y="42" width="6" height="14" rx="1" fill="#4caf50"/>
  <rect x="30" y="38" width="6" height="18" rx="1" fill="#8bc34a"/>
  <rect x="38" y="34" width="6" height="22" rx="1" fill="#cddc39"/>
  <!-- Wifi icon -->
  <path d="M80 38 Q90 48 80 56" fill="none" stroke="#00bcd4" stroke-width="2"/>
  <path d="M86 32 Q100 48 86 62" fill="none" stroke="#00bcd4" stroke-width="1.5"/>
  <!-- Dr. symbol -->
  <text x="64" y="78" text-anchor="middle" font-size="12" fill="#0d47a1" font-family="Arial" font-weight="bold">NST</text>
  <!-- Small dots decoration -->
  <circle cx="92" cy="90" r="3" fill="#ff9800"/>
  <circle cx="96" cy="96" r="2" fill="#ff5722"/>
  <circle cx="32" cy="96" r="2" fill="#4caf50"/>
  <!-- Text label -->
  <text x="64" y="120" text-anchor="middle" font-size="10" fill="#00bcd4" font-family="Arial" font-weight="bold">NEAR CELL</text>
</svg>'''
    with open(svg_path, 'w') as f:
        f.write(svg_content)

    # Try to convert SVG to PNG if available
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=icon_path, output_width=128, output_height=128)
        print(f"[OK] Icon created: {icon_path}")
    except ImportError:
        # Fallback: just use SVG as icon
        icon_path = svg_path
        print(f"[i] Created SVG icon: {svg_path}")
        print("[i] Install cairosvg for PNG: pip install cairosvg")
    
    return icon_path


if __name__ == "__main__":
    print("=" * 50)
    print("  NEAR CELL SYSTEM - Desktop Shortcut Creator")
    print("=" * 50)
    print()
    
    # Create icon
    icon_path = create_near_cell_icon()
    
    # Create shortcut based on OS
    if platform.system() == "Windows":
        shortcut_path = create_windows_shortcut()
    elif platform.system() == "Linux":
        shortcut_path = create_linux_shortcut()
    else:
        print("Mac OS: Silakan buat shortcut manual dari Automator")
        print(f"  Run: python3 {os.path.join(PROJECT_DIR, 'near_cell_system.py')}")
        shortcut_path = None
    
    print()
    if shortcut_path:
        print(f"[OK] NEAR CELL SYSTEM shortcut siap di desktop!")
    print()
    print("  Jalankan shortcut untuk meluncurkan toolkit.")
    print()
    ""
