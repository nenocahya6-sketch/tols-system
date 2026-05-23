

"""
NST Full Device Profile Database v1
====================================
Database profil device komprehensif untuk flashing aman.

Fitur:
  ✅ Partition map per device (boot, vbmeta, super, etc.)
  ✅ Chipset info (type, platform, codename)
  ✅ Auth type (KG, Mi Unlock, Bootloader Code)
  ✅ Test point locations (EDL, BROM, UART)
  ✅ Rollback policy (ARB version, anti-rollback)
  ✅ Firmware compatibility mapping
  ✅ Download mode key combinations

Struktur data:
  device_profiles.json — database utama (bisa diupdate user)
  core/device_database.py — engine untuk load, query, manage
"""


import os
import json
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

from core.logger import log, Colors


# ===========================================================================
# Data Models
# ===========================================================================

@dataclass
class PartitionInfo:
    """Info satu partisi dalam partition map."""
    name: str = ""
    size_mb: float = 0.0
    type: str = "raw"           # raw, sparse, ext4, f2fs
    is_critical: bool = False    # boot, vbmeta, recovery
    is_dangerous: bool = False   # preloader, tz, abl, xbl
    backup_recommended: bool = True
    description: str = ""


@dataclass
class ChipsetInfo:
    """Info chipset."""
    name: str = ""
    manufacturer: str = ""
    platform: str = ""
    arch: str = ""               # ARMv7, ARMv8, ARMv9
    cores: int = 0
    gpu: str = ""
    modem: str = ""
    bootrom_protocol: str = ""   # Qualcomm Sahara, MTK BROM, Unisoc FDL
    edl_support: bool = False
    brom_support: bool = False


@dataclass
class FirmwareInfo:
    """Info firmware untuk device."""
    version: str = ""
    android_version: str = ""
    security_patch: str = ""
    arb_version: int = -1
    bootloader_version: str = ""
    baseband_version: str = ""
    region: str = ""
    recommended: bool = False
    download_url: str = ""


@dataclass
class AuthInfo:
    """Info authentication untuk flashing."""
    type: str = ""               # samsung_kg, xiaomi_unlock, huawei_bootloader_code
    required: bool = False
    description: str = ""
    unlock_method: str = ""
    unlock_url: str = ""
    wait_period_days: int = 0    # 0 = no wait


@dataclass
class TestPointInfo:
    """Info test point untuk hardware recovery."""
    mode: str = ""               # EDL, BROM, UART, Download
    location: str = ""           # Motherboard description
    image_url: str = ""
    difficulty: str = "MEDIUM"   # EASY, MEDIUM, HARD
    requires_soldering: bool = False
    notes: str = ""


@dataclass
class KeyComboInfo:
    """Info key combination untuk masuk mode spesial."""
    mode: str = ""               # Fastboot, Recovery, Download, DFU
    combination: str = ""
    duration_seconds: int = 10
    notes: str = ""


@dataclass
class DeviceProfile:
    """Profil lengkap satu device."""
    model: str = ""              # SM-G998B
    brand: str = ""              # samsung
    marketing_name: str = ""     # Galaxy S21 Ultra
    codename: str = ""           # o1s
    year: int = 0
    
    # Chipset
    chipset: ChipsetInfo = field(default_factory=ChipsetInfo)
    
    # Partition map
    partitions: List[PartitionInfo] = field(default_factory=list)
    total_partitions: int = 0
    super_partition: bool = False   # Using logical partitions (dynamic)
    
    # Auth
    auth: AuthInfo = field(default_factory=AuthInfo)
    
    # Test points
    test_points: List[TestPointInfo] = field(default_factory=list)
    
    # Key combos
    key_combos: List[KeyComboInfo] = field(default_factory=list)
    
    # Firmware
    firmware_list: List[FirmwareInfo] = field(default_factory=list)
    latest_firmware: str = ""
    
    # Rollback policy
    max_arb_version: int = -1      # Maximum supported ARB version
    rollback_possible: bool = True
    rollback_notes: str = ""
    
    # Metadata
    last_updated: str = ""
    source: str = ""               # samfw, xiaomifirmware, manual
    
    def summary(self) -> str:
        """Ringkasan satu baris."""
        return (f"{self.brand.upper()} {self.marketing_name} ({self.model}) "
                f"[{self.chipset.manufacturer} {self.chipset.name}] "
                f"ARB: v{self.max_arb_version}")


# ===========================================================================
# DEVICE DATABASE ENGINE
# ===========================================================================

class DeviceDatabase:
    """
    Engine database profil device.
    
    Load/save/query device profiles dari device_profiles.json.
    Auto-create database jika belum ada.
    """
    
    DB_FILENAME = "device_profiles.json"
    
    def __init__(self):
        self.db_path = self._get_db_path()
        self._profiles: Dict[str, DeviceProfile] = {}  # key: model_code
        self._brands: Dict[str, List[str]] = {}        # brand -> [model_codes]
        self._loaded = False
    
    def _get_db_path(self) -> str:
        """Dapatkan path ke database file."""
        # Cari di project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(project_root, self.DB_FILENAME),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", self.DB_FILENAME),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return os.path.normpath(path)
        return os.path.normpath(candidates[0])
    
    def load(self) -> bool:
        """Load database dari file JSON."""
        if not os.path.isfile(self.db_path):
            log.warning(f"Database tidak ditemukan: {self.db_path}")
            log.info("Membuat database default...")
            self._create_default()
            return False
        
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            count = 0
            for model, profile_data in data.get("profiles", {}).items():
                try:
                    profile = self._dict_to_profile(profile_data)
                    self._profiles[model.upper()] = profile
                    
                    brand = profile.brand.lower()
                    if brand not in self._brands:
                        self._brands[brand] = []
                    self._brands[brand].append(model.upper())
                    
                    count += 1
                except Exception as e:
                    log.warning(f"Error parse profile {model}: {e}")
            
            self._loaded = True
            log.success(f"Database loaded: {count} profiles ({len(self._brands)} brands)")
            return True
            
        except Exception as e:
            log.error(f"Gagal load database: {e}")
            self._create_default()
            return False
    
    def save(self) -> bool:
        """Simpan database ke file JSON."""
        try:
            data = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "total_profiles": len(self._profiles),
                "profiles": {},
            }
            
            for model, profile in self._profiles.items():
                data["profiles"][model] = self._profile_to_dict(profile)
            
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            log.success(f"Database saved: {len(self._profiles)} profiles ke {self.db_path}")
            return True
        except Exception as e:
            log.error(f"Gagal save database: {e}")
            return False
    
    # ── Query Methods ──
    
    def get_profile(self, model: str) -> Optional[DeviceProfile]:
        """Cari profil device berdasarkan model code."""
        self._ensure_loaded()
        return self._profiles.get(model.upper())
    
    def search(self, query: str) -> List[DeviceProfile]:
        """
        Cari device berdasarkan query.
        
        Query bisa: model (SM-G998B), brand (samsung), 
        marketing_name (Galaxy), chipset (snapdragon), codename (o1s)
        """
        self._ensure_loaded()
        query = query.lower().strip()
        if not query:
            return []
        
        results = []
        for profile in self._profiles.values():
            if (query in profile.model.lower() or
                query in profile.brand.lower() or
                query in profile.marketing_name.lower() or
                query in profile.codename.lower() or
                query in profile.chipset.name.lower() or
                query in profile.chipset.manufacturer.lower()):
                results.append(profile)
        
        return results
    
    def get_by_brand(self, brand: str) -> List[DeviceProfile]:
        """Dapatkan semua device dari brand tertentu."""
        self._ensure_loaded()
        brand = brand.lower()
        models = self._brands.get(brand, [])
        return [self._profiles[m] for m in models if m in self._profiles]
    
    def get_by_chipset(self, chipset_name: str) -> List[DeviceProfile]:
        """Dapatkan device berdasarkan chipset."""
        self._ensure_loaded()
        chipset_name = chipset_name.lower()
        return [p for p in self._profiles.values() 
                if chipset_name in p.chipset.name.lower()]
    
    def get_by_codename(self, codename: str) -> Optional[DeviceProfile]:
        """Cari device berdasarkan codename."""
        self._ensure_loaded()
        codename = codename.lower()
        for profile in self._profiles.values():
            if profile.codename.lower() == codename:
                return profile
        return None
    
    def get_partition_map(self, model: str) -> List[PartitionInfo]:
        """Dapatkan partition map untuk device."""
        profile = self.get_profile(model)
        if profile:
            return profile.partitions
        return []
    
    def get_auth_info(self, model: str) -> Optional[AuthInfo]:
        """Dapatkan info authentication untuk device."""
        profile = self.get_profile(model)
        if profile:
            return profile.auth
        return None
    
    def get_test_points(self, model: str) -> List[TestPointInfo]:
        """Dapatkan test point locations untuk device."""
        profile = self.get_profile(model)
        if profile:
            return profile.test_points
        return []
    
    def get_key_combos(self, model: str) -> List[KeyComboInfo]:
        """Dapatkan key combinations untuk device."""
        profile = self.get_profile(model)
        if profile:
            return profile.key_combos
        return []
    
    def get_brands(self) -> List[str]:
        """Dapatkan daftar brand yang ada di database."""
        self._ensure_loaded()
        return sorted(self._brands.keys())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Statistik database."""
        self._ensure_loaded()
        total = len(self._profiles)
        brands = len(self._brands)
        
        chipset_types = {}
        for p in self._profiles.values():
            mfr = p.chipset.manufacturer or "Unknown"
            chipset_types[mfr] = chipset_types.get(mfr, 0) + 1
        
        return {
            "total_profiles": total,
            "total_brands": brands,
            "brands": list(self._brands.keys()),
            "chipset_distribution": chipset_types,
            "db_path": self.db_path,
            "last_updated": "",
        }
    
    # ── Profile Management ──
    
    def add_profile(self, profile: DeviceProfile) -> bool:
        """Tambah profil baru ke database."""
        if not profile.model:
            log.error("Model code wajib diisi!")
            return False
        
        model = profile.model.upper()
        self._profiles[model] = profile
        
        brand = profile.brand.lower()
        if brand not in self._brands:
            self._brands[brand] = []
        if model not in self._brands[brand]:
            self._brands[brand].append(model)
        
        profile.last_updated = datetime.now().isoformat()
        return True
    
    def remove_profile(self, model: str) -> bool:
        """Hapus profil dari database."""
        model = model.upper()
        if model not in self._profiles:
            return False
        
        profile = self._profiles.pop(model)
        brand = profile.brand.lower()
        if brand in self._brands and model in self._brands[brand]:
            self._brands[brand].remove(model)
            if not self._brands[brand]:
                del self._brands[brand]
        
        return True
    
    # ── Helper ──
    
    def _ensure_loaded(self):
        """Pastikan database sudah di-load."""
        if not self._loaded:
            self.load()
    
    def _profile_to_dict(self, profile: DeviceProfile) -> Dict:
        """Konversi DeviceProfile ke dict untuk JSON."""
        return {
            "model": profile.model,
            "brand": profile.brand,
            "marketing_name": profile.marketing_name,
            "codename": profile.codename,
            "year": profile.year,
            "chipset": asdict(profile.chipset),
            "partitions": [asdict(p) for p in profile.partitions],
            "total_partitions": profile.total_partitions,
            "super_partition": profile.super_partition,
            "auth": asdict(profile.auth),
            "test_points": [asdict(tp) for tp in profile.test_points],
            "key_combos": [asdict(kc) for kc in profile.key_combos],
            "firmware_list": [asdict(fw) for fw in profile.firmware_list],
            "latest_firmware": profile.latest_firmware,
            "max_arb_version": profile.max_arb_version,
            "rollback_possible": profile.rollback_possible,
            "rollback_notes": profile.rollback_notes,
            "last_updated": profile.last_updated,
            "source": profile.source,
        }
    
    def _dict_to_profile(self, d: Dict) -> DeviceProfile:
        """Konversi dict dari JSON ke DeviceProfile."""
        chipset_data = d.get("chipset", {})
        chipset = ChipsetInfo(
            name=chipset_data.get("name", ""),
            manufacturer=chipset_data.get("manufacturer", ""),
            platform=chipset_data.get("platform", ""),
            arch=chipset_data.get("arch", ""),
            cores=chipset_data.get("cores", 0),
            gpu=chipset_data.get("gpu", ""),
            modem=chipset_data.get("modem", ""),
            bootrom_protocol=chipset_data.get("bootrom_protocol", ""),
            edl_support=chipset_data.get("edl_support", False),
            brom_support=chipset_data.get("brom_support", False),
        )
        
        partitions = []
        for p in d.get("partitions", []):
            partitions.append(PartitionInfo(
                name=p.get("name", ""),
                size_mb=p.get("size_mb", 0.0),
                type=p.get("type", "raw"),
                is_critical=p.get("is_critical", False),
                is_dangerous=p.get("is_dangerous", False),
                backup_recommended=p.get("backup_recommended", True),
                description=p.get("description", ""),
            ))
        
        auth_data = d.get("auth", {})
        auth = AuthInfo(
            type=auth_data.get("type", ""),
            required=auth_data.get("required", False),
            description=auth_data.get("description", ""),
            unlock_method=auth_data.get("unlock_method", ""),
            unlock_url=auth_data.get("unlock_url", ""),
            wait_period_days=auth_data.get("wait_period_days", 0),
        )
        
        test_points = []
        for tp in d.get("test_points", []):
            test_points.append(TestPointInfo(
                mode=tp.get("mode", ""),
                location=tp.get("location", ""),
                image_url=tp.get("image_url", ""),
                difficulty=tp.get("difficulty", "MEDIUM"),
                requires_soldering=tp.get("requires_soldering", False),
                notes=tp.get("notes", ""),
            ))
        
        key_combos = []
        for kc in d.get("key_combos", []):
            key_combos.append(KeyComboInfo(
                mode=kc.get("mode", ""),
                combination=kc.get("combination", ""),
                duration_seconds=kc.get("duration_seconds", 10),
                notes=kc.get("notes", ""),
            ))
        
        firmware_list = []
        for fw in d.get("firmware_list", []):
            firmware_list.append(FirmwareInfo(
                version=fw.get("version", ""),
                android_version=fw.get("android_version", ""),
                security_patch=fw.get("security_patch", ""),
                arb_version=fw.get("arb_version", -1),
                bootloader_version=fw.get("bootloader_version", ""),
                baseband_version=fw.get("baseband_version", ""),
                region=fw.get("region", ""),
                recommended=fw.get("recommended", False),
                download_url=fw.get("download_url", ""),
            ))
        
        return DeviceProfile(
            model=d.get("model", ""),
            brand=d.get("brand", ""),
            marketing_name=d.get("marketing_name", ""),
            codename=d.get("codename", ""),
            year=d.get("year", 0),
            chipset=chipset,
            partitions=partitions,
            total_partitions=d.get("total_partitions", len(partitions)),
            super_partition=d.get("super_partition", False),
            auth=auth,
            test_points=test_points,
            key_combos=key_combos,
            firmware_list=firmware_list,
            latest_firmware=d.get("latest_firmware", ""),
            max_arb_version=d.get("max_arb_version", -1),
            rollback_possible=d.get("rollback_possible", True),
            rollback_notes=d.get("rollback_notes", ""),
            last_updated=d.get("last_updated", ""),
            source=d.get("source", ""),
        )
    
    def _create_default(self):
        """Buat database default dengan beberapa profil sample."""
        log.info("Membuat database default dengan profil device populer...")
        
        # Samsung Galaxy S21 Ultra (Exynos)
        s21_ultra = DeviceProfile(
            model="SM-G998B",
            brand="samsung",
            marketing_name="Galaxy S21 Ultra",
            codename="o1s",
            year=2021,
            chipset=ChipsetInfo(
                name="Exynos 2100",
                manufacturer="Samsung",
                platform="Exynos 2100",
                arch="ARMv8",
                cores=8,
                gpu="Mali-G78 MP14",
                modem="Exynos 5123",
                bootrom_protocol="Samsung Download",
                brom_support=False,
            ),
            partitions=[
                PartitionInfo(name="xbl", size_mb=5.0, type="raw", is_dangerous=True, description="Boot ROM第一阶段"),
                PartitionInfo(name="abl", size_mb=2.0, type="raw", is_dangerous=True, description="ABL bootloader"),
                PartitionInfo(name="boot", size_mb=64.0, is_critical=True, description="Kernel + initramfs"),
                PartitionInfo(name="vbmeta", size_mb=1.0, is_critical=True, description="Verified boot metadata"),
                PartitionInfo(name="recovery", size_mb=64.0, is_critical=True, description="Recovery mode"),
                PartitionInfo(name="super", size_mb=6000.0, is_critical=True, description="Logical partitions (dynamic)"),
                PartitionInfo(name="dtbo", size_mb=16.0, is_critical=True, description="Device tree blob overlay"),
            ],
            super_partition=True,
            auth=AuthInfo(
                type="samsung_kg",
                required=True,
                description="Samsung KG (Knowledge Guard) - OEM must be unlocked",
                unlock_method="Settings > Developer Options > OEM Unlock",
                unlock_url="https://developer.samsung.com/android-usb-driver",
                wait_period_days=0,
            ),
            test_points=[
                TestPointInfo(
                    mode="UART", location="Test points near SIM slot",
                    difficulty="HARD", requires_soldering=True,
                    notes="Need to identify UART_RX and UART_TX"
                ),
            ],
            key_combos=[
                KeyComboInfo(mode="Download", combination="Vol Down + Power + Home", duration_seconds=10),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power + Home", duration_seconds=10),
            ],
            max_arb_version=7,
            rollback_possible=False,
            rollback_notes="Exynos 2100 tidak bisa rollback firmware di bawah ARB v7",
            source="samfw",
        )
        self.add_profile(s21_ultra)
        
        # Samsung Galaxy S21 Ultra (Snapdragon)
        s21_ultra_q = DeviceProfile(
            model="SM-G998U",
            brand="samsung",
            marketing_name="Galaxy S21 Ultra",
            codename="o1s",
            year=2021,
            chipset=ChipsetInfo(
                name="Snapdragon 888",
                manufacturer="Qualcomm",
                platform="SM8350",
                arch="ARMv8",
                cores=8,
                gpu="Adreno 660",
                modem="Snapdragon X60",
                bootrom_protocol="Qualcomm Sahara / EDL",
                edl_support=True,
            ),
            auth=AuthInfo(
                type="samsung_kg",
                required=True,
                unlock_method="Settings > Developer Options > OEM Unlock",
            ),
            key_combos=[
                KeyComboInfo(mode="Download", combination="Vol Down + Power + Home", duration_seconds=10),
            ],
            max_arb_version=5,
            source="samfw",
        )
        self.add_profile(s21_ultra_q)
        
        # Xiaomi Mi 11
        mi11 = DeviceProfile(
            model="M2011K2G",
            brand="xiaomi",
            marketing_name="Mi 11",
            codename="venus",
            year=2020,
            chipset=ChipsetInfo(
                name="Snapdragon 888",
                manufacturer="Qualcomm",
                platform="SM8350",
                arch="ARMv8",
                cores=8,
                gpu="Adreno 660",
                bootrom_protocol="Qualcomm Sahara / EDL",
                edl_support=True,
            ),
            partitions=[
                PartitionInfo(name="xbl", size_mb=5.0, type="raw", is_dangerous=True),
                PartitionInfo(name="abl", size_mb=2.0, type="raw", is_dangerous=True),
                PartitionInfo(name="boot", size_mb=96.0, is_critical=True),
                PartitionInfo(name="vbmeta", size_mb=1.0, is_critical=True),
                PartitionInfo(name="recovery", size_mb=96.0, is_critical=True),
                PartitionInfo(name="super", size_mb=6000.0, is_critical=True),
                PartitionInfo(name="dtbo", size_mb=16.0, is_critical=True),
            ],
            super_partition=True,
            auth=AuthInfo(
                type="xiaomi_unlock",
                required=True,
                description="Xiaomi Mi Unlock - butuh approval dari Xiaomi",
                unlock_method="Mi Unlock Tool from en.miui.com/unlock/",
                unlock_url="https://en.miui.com/unlock/",
                wait_period_days=7,
            ),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            max_arb_version=-1,
            rollback_possible=True,
            source="xiaomifirmware",
        )
        self.add_profile(mi11)
        
        # Google Pixel 6
        pixel6 = DeviceProfile(
            model="Pixel 6",
            brand="google",
            marketing_name="Pixel 6",
            codename="oriole",
            year=2021,
            chipset=ChipsetInfo(
                name="Tensor",
                manufacturer="Google",
                platform="GS101",
                arch="ARMv8",
                cores=8,
                gpu="Mali-G78 MP20",
                bootrom_protocol="EDL (limited)",
                edl_support=True,
            ),
            partitions=[
                PartitionInfo(name="boot", size_mb=64.0, is_critical=True),
                PartitionInfo(name="vbmeta", size_mb=1.0, is_critical=True),
                PartitionInfo(name="recovery", size_mb=64.0, is_critical=True),
                PartitionInfo(name="super", size_mb=5000.0, is_critical=True),
                PartitionInfo(name="vendor_boot", size_mb=64.0, is_critical=True),
            ],
            super_partition=True,
            auth=AuthInfo(
                type="google_unlock",
                required=False,
                description="Google bootloader unlock - free but wipes data",
                unlock_method="fastboot flashing unlock",
            ),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Down + Power (choose Recovery)"),
            ],
            max_arb_version=-1,
            rollback_possible=True,
            rollback_notes="Pixel mudah di-unbrick, flash factory image via fastboot",
            source="google",
        )
        self.add_profile(pixel6)
        
        # OnePlus 9 Pro
        op9p = DeviceProfile(
            model="LE2123",
            brand="oneplus",
            marketing_name="OnePlus 9 Pro",
            codename="lemonade",
            year=2021,
            chipset=ChipsetInfo(
                name="Snapdragon 888",
                manufacturer="Qualcomm",
                platform="SM8350",
                arch="ARMv8",
                cores=8,
                gpu="Adreno 660",
                bootrom_protocol="Qualcomm Sahara / EDL",
                edl_support=True,
            ),
            partitions=[
                PartitionInfo(name="xbl", size_mb=5.0, type="raw", is_dangerous=True),
                PartitionInfo(name="abl", size_mb=2.0, type="raw", is_dangerous=True),
                PartitionInfo(name="boot", size_mb=96.0, is_critical=True),
                PartitionInfo(name="vbmeta", size_mb=1.0, is_critical=True),
                PartitionInfo(name="super", size_mb=6000.0, is_critical=True),
            ],
            super_partition=True,
            auth=AuthInfo(
                type="oneplus_unlock",
                required=False,
                description="OnePlus bootloader unlock - free",
                unlock_method="fastboot oem unlock",
            ),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            max_arb_version=-1,
            rollback_possible=True,
            source="oneplus",
        )
        self.add_profile(op9p)
        
        # Huawei P40 Pro
        p40p = DeviceProfile(
            model="ELS-NX9",
            brand="huawei",
            marketing_name="P40 Pro",
            codename="els",
            year=2020,
            chipset=ChipsetInfo(
                name="Kirin 990 5G",
                manufacturer="HiSilicon",
                platform="Kirin 990",
                arch="ARMv8",
                cores=8,
                gpu="Mali-G76 MP16",
                modem="Balong 5000",
                bootrom_protocol="HiSilicon USB Download",
                brom_support=True,
            ),
            partitions=[
                PartitionInfo(name="boot", size_mb=64.0, is_critical=True),
                PartitionInfo(name="recovery", size_mb=64.0, is_critical=True),
                PartitionInfo(name="system", size_mb=3000.0, is_critical=True),
                PartitionInfo(name="vendor", size_mb=1000.0, is_critical=True),
                PartitionInfo(name="product", size_mb=2000.0, is_critical=True),
                PartitionInfo(name="recovery_ramdisk", size_mb=64.0, is_critical=True),
            ],
            super_partition=False,
            auth=AuthInfo(
                type="huawei_bootloader_code",
                required=True,
                description="Huawei requires bootloader code (no longer provided officially)",
                unlock_method="Third-party unlock services",
                wait_period_days=0,
            ),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            max_arb_version=-1,
            rollback_possible=False,
            rollback_notes="Huawei tidak menyediakan firmware untuk flashing publik. Gunakan HiSuite.",
            source="huawei",
        )
        self.add_profile(p40p)
        
        # MediaTek device sample - Xiaomi Redmi Note 10
        redmi_n10 = DeviceProfile(
            model="M2101K7AG",
            brand="xiaomi",
            marketing_name="Redmi Note 10",
            codename="mojito",
            year=2021,
            chipset=ChipsetInfo(
                name="Snapdragon 678",
                manufacturer="Qualcomm",
                platform="SM6150",
                arch="ARMv8",
                cores=8,
                gpu="Adreno 612",
                bootrom_protocol="Qualcomm Sahara / EDL",
                edl_support=True,
            ),
            partitions=[
                PartitionInfo(name="boot", size_mb=64.0, is_critical=True),
                PartitionInfo(name="vbmeta", size_mb=1.0, is_critical=True),
                PartitionInfo(name="recovery", size_mb=64.0, is_critical=True),
                PartitionInfo(name="super", size_mb=5000.0, is_critical=True),
            ],
            super_partition=True,
            auth=AuthInfo(
                type="xiaomi_unlock", required=True, wait_period_days=7,
            ),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            source="xiaomifirmware",
        )
        self.add_profile(redmi_n10)
        
        # MediaTek device - Xiaomi Redmi Note 11 (MTK)
        redmi_n11_mtk = DeviceProfile(
            model="2201117TG",
            brand="xiaomi",
            marketing_name="Redmi Note 11",
            codename="spes",
            year=2021,
            chipset=ChipsetInfo(
                name="Snapdragon 680",
                manufacturer="Qualcomm",
                platform="SM6225",
                arch="ARMv8",
                cores=8,
                gpu="Adreno 610",
                bootrom_protocol="Qualcomm Sahara / EDL",
                edl_support=True,
            ),
            partitions=[
                PartitionInfo(name="boot", size_mb=96.0, is_critical=True),
                PartitionInfo(name="vbmeta", size_mb=1.0, is_critical=True),
                PartitionInfo(name="super", size_mb=6000.0, is_critical=True),
            ],
            super_partition=True,
            auth=AuthInfo(type="xiaomi_unlock", required=True, wait_period_days=7),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
            ],
            source="xiaomifirmware",
        )
        self.add_profile(redmi_n11_mtk)
        
        # Samsung Galaxy A52
        a52 = DeviceProfile(
            model="SM-A525F",
            brand="samsung",
            marketing_name="Galaxy A52",
            codename="a52q",
            year=2021,
            chipset=ChipsetInfo(
                name="Snapdragon 720G",
                manufacturer="Qualcomm",
                platform="SM7125",
                arch="ARMv8",
                cores=8,
                gpu="Adreno 618",
                bootrom_protocol="Qualcomm Sahara / EDL",
                edl_support=True,
            ),
            auth=AuthInfo(type="samsung_kg", required=True),
            key_combos=[
                KeyComboInfo(mode="Download", combination="Vol Down + Power + Home"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power + Home"),
            ],
            source="samfw",
        )
        self.add_profile(a52)
        
        # Exynos device - Samsung Galaxy A53
        a53 = DeviceProfile(
            model="SM-A536B",
            brand="samsung",
            marketing_name="Galaxy A53 5G",
            codename="a53x",
            year=2022,
            chipset=ChipsetInfo(
                name="Exynos 1280",
                manufacturer="Samsung",
                platform="Exynos 1280",
                arch="ARMv8",
                cores=8,
                gpu="Mali-G68",
                bootrom_protocol="Samsung Download",
                brom_support=False,
            ),
            auth=AuthInfo(type="samsung_kg", required=True),
            key_combos=[
                KeyComboInfo(mode="Download", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            source="samfw",
        )
        self.add_profile(a53)
        
        # Kirin device - Huawei Mate 40 Pro
        mate40 = DeviceProfile(
            model="NOH-NX9",
            brand="huawei",
            marketing_name="Mate 40 Pro",
            codename="noh",
            year=2020,
            chipset=ChipsetInfo(
                name="Kirin 9000",
                manufacturer="HiSilicon",
                platform="Kirin 9000",
                arch="ARMv8",
                cores=8,
                gpu="Mali-G78 MP24",
                bootrom_protocol="HiSilicon USB Download",
                brom_support=True,
            ),
            auth=AuthInfo(type="huawei_bootloader_code", required=True),
            key_combos=[
                KeyComboInfo(mode="Fastboot", combination="Vol Down + Power"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            source="huawei",
        )
        self.add_profile(mate40)
        
        # Unisoc device sample
        # (generic Unisoc reference)
        unisoc_dev = DeviceProfile(
            model="Unisoc-T606",
            brand="generic",
            marketing_name="Generic Unisoc Device",
            codename="unisoc_t606",
            year=2022,
            chipset=ChipsetInfo(
                name="T606",
                manufacturer="Unisoc",
                platform="Spreadtrum",
                arch="ARMv8",
                cores=8,
                gpu="Mali-G57",
                bootrom_protocol="Unisoc FDL (Fast Download Loader)",
                brom_support=True,
            ),
            auth=AuthInfo(type="none", required=False),
            key_combos=[
                KeyComboInfo(mode="FDL", combination="Vol Up + Vol Down + USB connect"),
                KeyComboInfo(mode="Recovery", combination="Vol Up + Power"),
            ],
            source="manual",
        )
        self.add_profile(unisoc_dev)
        
        # Save to file
        self.save()
        log.success(f"Database default dibuat: {len(self._profiles)} profiles")


# ===========================================================================
# DISPLAY & REPORT
# ===========================================================================

def display_profile(profile: DeviceProfile):
    """Tampilkan profil device ke layar."""
    if not profile:
        log.warning("Profil tidak ditemukan")
        return
    
    print(f"  {Colors.BOLD}{Colors.CYAN}Device Profile: {profile.marketing_name}{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    print(f"  Model:        {profile.model}")
    print(f"  Brand:        {profile.brand.upper()}")
    print(f"  Codename:     {profile.codename}")
    print(f"  Year:         {profile.year}")
    print()
    
    # Chipset
    c = profile.chipset
    print(f"  {Colors.YELLOW}Chipset:{Colors.RESET}")
    print(f"    Name:       {c.name}")
    print(f"    Mfr:        {c.manufacturer}")
    print(f"    Platform:   {c.platform}")
    print(f"    Arch:       {c.arch}")
    print(f"    BootROM:    {c.bootrom_protocol}")
    print(f"    EDL:        {'Yes' if c.edl_support else 'No'}")
    print(f"    BROM:       {'Yes' if c.brom_support else 'No'}")
    print()
    
    # Auth
    a = profile.auth
    if a.type:
        print(f"  {Colors.RED}Auth:{Colors.RESET}")
        print(f"    Type:      {a.type}")
        print(f"    Required:  {'Yes' if a.required else 'No'}")
        print(f"    Method:    {a.unlock_method}")
        if a.wait_period_days > 0:
            print(f"    Wait:      {a.wait_period_days} days")
        print()
    
    # Partitions
    if profile.partitions:
        print(f"  {Colors.GREEN}Partition Map ({len(profile.partitions)}):{Colors.RESET}")
        for p in profile.partitions:
            icon = "🔴" if p.is_dangerous else ("🟢" if p.is_critical else "📦")
            print(f"    {icon} {p.name:20s} {p.size_mb:>8.1f} MB  {p.type:10s} {Colors.DIM}{p.description[:40]}{Colors.RESET}")
        print()
    
    # Test points
    if profile.test_points:
        print(f"  {Colors.MAGENTA}Test Points:{Colors.RESET}")
        for tp in profile.test_points:
            print(f"    📍 {tp.mode}: {tp.location}")
            print(f"       Difficulty: {tp.difficulty}, Soldering: {'Yes' if tp.requires_soldering else 'No'}")
        print()
    
    # Key combos
    if profile.key_combos:
        print(f"  {Colors.CYAN}Key Combinations:{Colors.RESET}")
        for kc in profile.key_combos:
            print(f"    ⌨️ {kc.mode:15s} {kc.combination} ({kc.duration_seconds}s)")
        print()
    
    # Rollback
    if profile.max_arb_version >= 0:
        print(f"  {Colors.RED}ARB Max: v{profile.max_arb_version} | Rollback: {'Yes' if profile.rollback_possible else 'No'}{Colors.RESET}")
        if profile.rollback_notes:
            print(f"  {Colors.DIM}  Notes: {profile.rollback_notes}{Colors.RESET}")
        print()
    
    print(f"  {Colors.DIM}Source: {profile.source} | Updated: {profile.last_updated[:10]}{Colors.RESET}")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")


def display_search_results(results: List[DeviceProfile], query: str):
    """Tampilkan hasil pencarian."""
    if not results:
        log.info(f"Tidak ada device ditemukan untuk: '{query}'")
        return
    
    log.success(f"Ditemukan {len(results)} device untuk: '{query}'")
    print(f"  {Colors.DIM}{'─' * 56}{Colors.RESET}")
    for p in results[:20]:
        print(f"  {p.summary()}")
    if len(results) > 20:
        print(f"  ... dan {len(results) - 20} lainnya")


# ===========================================================================
# MAIN ENTRY
# ===========================================================================

def run():
    """Jalankan Device Profile Database — cari profil."""
    log.header("[DEVICE PROFILE DATABASE]")
    
    db = DeviceDatabase()
    db.load()
    
    stats = db.get_statistics()
    print()
    log.info(f"Database: {stats['total_profiles']} profiles, {stats['total_brands']} brands")
    print(f"  Brands: {', '.join(stats['brands'])}")
    print()
    
    query = input(f"  {Colors.CYAN}Cari model/brand/chipset: {Colors.RESET}").strip()
    if not query:
        return
    
    results = db.search(query)
    
    if not results:
        log.warning(f"Device '{query}' tidak ditemukan di database")
        print()
        log.info("Database masih awal. Kontribusi data device baru sangat dihargai!")
        return
    
    print()
    for i, profile in enumerate(results[:5], 1):
        print(f"  {Colors.CYAN}{i}.{Colors.RESET} {profile.summary()}")
    
    if len(results) > 1:
        print()
        choice = input(f"  {Colors.CYAN}Pilih nomor untuk detail (Enter=exit): {Colors.RESET}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            display_profile(results[int(choice) - 1])
    else:
        display_profile(results[0])


def run_search():
    """Cari device di database — langsung query."""
    import sys
    log.header("[DEVICE SEARCH]")
    
    query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "".strip()
    if not query:
        return
    
    db = DeviceDatabase()
    db.load()
    results = db.search(query)
    display_search_results(results, query)
    
    if len(results) == 1:
        print()
        if input(f"  Lihat detail? (Y/n): ").strip().lower() != 'n':
            display_profile(results[0])


def run_stats():
    """Tampilkan statistik database."""
    db = DeviceDatabase()
    db.load()
    
    stats = db.get_statistics()
    
    log.header("[DATABASE STATISTICS]")
    print(f"  Total Profiles:   {stats['total_profiles']}")
    print(f"  Total Brands:     {stats['total_brands']}")
    print(f"  Brands:           {', '.join(stats['brands'])}")
    print()
    
    if stats['chipset_distribution']:
        log.info("Chipset Distribution:")
        for mfr, count in sorted(stats['chipset_distribution'].items(), key=lambda x: -x[1]):
            print(f"  {Colors.DIM}  {mfr:20s}: {count} devices{Colors.RESET}")
    print()
    log.info(f"Database path: {stats['db_path']}")


# ===========================================================================
# QUICK ACCESS FUNCTIONS
# ===========================================================================

def get_partition_map(model: str) -> Optional[List[PartitionInfo]]:
    """Cepat dapat partition map untuk device."""
    db = DeviceDatabase()
    db.load()
    return db.get_partition_map(model)


def get_auth_info(model: str) -> Optional[AuthInfo]:
    """Cepat dapat auth info untuk device."""
    db = DeviceDatabase()
    db.load()
    return db.get_auth_info(model)


def get_test_points(model: str) -> Optional[List[TestPointInfo]]:
    """Cepat dapat test point untuk device."""
    db = DeviceDatabase()
    db.load()
    return db.get_test_points(model)