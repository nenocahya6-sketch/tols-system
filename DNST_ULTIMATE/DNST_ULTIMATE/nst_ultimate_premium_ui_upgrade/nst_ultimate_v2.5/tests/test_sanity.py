
import os
import sys

# Tambahkan root path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_system_sanity():
    """Verifikasi environment dan core logic minimal"""
    from core.device_detector import DeviceDetector
    detector = DeviceDetector()
    assert detector is not None
    assert hasattr(detector, 'scan_all')
