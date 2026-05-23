
"""
Smart Deep Scan Module
Menganalisis perangkat hingga level codename/HWID dan memberikan
rekomendasi firmware serta link download yang presisi.
"""
from core.device_detector import DeviceDetector
from core.device_database import DeviceDatabase
from core.logger import log, Colors
import time

def run_smart_scan(update_progress, task_id):
    """
    Fungsi utama yang akan dijalankan oleh TaskManager.
    """
    update_progress(10, "Inisialisasi Smart Deep Scan...")
    
    db = DeviceDatabase()
    db.load()
    
    update_progress(30, "Mendeteksi perangkat...")
    detector = DeviceDetector()
    devices = detector.scan_all()
    
    if not devices:
        update_progress(100, "Selesai")
        return "❌ Tidak ada perangkat yang terdeteksi. Pastikan kabel USB terpasang dan driver terinstal."
    
    dev = devices[0]
    update_progress(60, f"Menganalisis HWID/Codename untuk {dev.vendor_name}...")
    
    codename = dev.codename
    
    # Format output message
    output = []
    output.append(f"{Colors.CYAN}=== HASIL SMART DEEP SCAN ==={Colors.RESET}")
    output.append(f"Perangkat terdeteksi: {dev.vendor_name} {dev.product_name}")
    output.append(f"Mode koneksi: {dev.mode.upper()}")
    
    if codename:
        output.append(f"Codename/HWID: {Colors.GREEN}{Colors.BOLD}{codename.upper()}{Colors.RESET}")
        
        update_progress(80, "Mencari kecocokan di database...")
        profile = db.get_by_codename(codename)
        
        if profile:
            output.append(f"\n✅ {Colors.GREEN}Profil Ditemukan!{Colors.RESET}")
            output.append(f"Model: {profile.marketing_name} ({profile.model})")
            output.append(f"Chipset: {profile.chipset.manufacturer} {profile.chipset.name}")
            
            if profile.firmware_list:
                fw = profile.firmware_list[0]
                output.append(f"\n{Colors.YELLOW}--- REKOMENDASI FIRMWARE ---{Colors.RESET}")
                output.append(f"Versi: {fw.version} (Android {fw.android_version})")
                if fw.download_url:
                    output.append(f"Link Download Resmi/Terpercaya: {Colors.BLUE}{Colors.UNDERLINE}{fw.download_url}{Colors.RESET}")
                else:
                    output.append(f"Link Download: (Belum tersedia di database, cari via Google menggunakan codename {codename.upper()})")
            else:
                output.append(f"\n⚠️ Belum ada data firmware untuk model ini di database.")
        else:
            output.append(f"\n⚠️ Codename '{codename}' tidak ditemukan di database.")
            output.append("Silakan cari firmware secara manual menggunakan codename tersebut.")
            
    else:
        output.append(f"\n❌ Gagal membaca Codename/HWID secara mendalam.")
        output.append("Pastikan perangkat dalam mode ADB atau Fastboot yang benar.")
    
    output_str = "\n".join(output)
    
    # Menggunakan logger agar masuk ke UI console juga jika ter-hook
    log.info("\n" + output_str)
    
    update_progress(100, "Selesai")
    return output_str
