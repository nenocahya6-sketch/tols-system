

"""
NST Update Checker v1
======================
Auto-update system:
1. Cek versi terbaru dari GitHub Releases
2. Bandingkan dengan versi lokal
3. Download + extract update otomatis
4. Backup versi lama sebelum update
"""
import os
import sys
import json
import urllib.request
import zipfile
import tarfile
import shutil
import re
from datetime import datetime
from typing import Dict, Optional, Tuple
from packaging.version import Version, InvalidVersion

from core.logger import log, Colors
from core.safety import ConfirmationChain, ActionLogger


class UpdateChecker:
    """
    Check update dari GitHub Releases.
    Format: https://api.github.com/repos/{owner}/{repo}/releases/latest
    """

    # Konfigurasi GitHub
    GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
    GITHUB_DOWNLOAD = "https://github.com/{owner}/{repo}/releases/download/{tag}/{asset}"

    def __init__(self, owner: str = "", repo: str = "", current_version: str = ""):
        from config import VERSION
        self.owner = owner or "nst-service"
        self.repo = repo or "nst-ultimate"
        self.current_version = current_version or VERSION
        self.latest_version: Optional[str] = None
        self.release_data: Optional[Dict] = None

    def check_latest(self, timeout: int = 10) -> Optional[str]:
        """
        Cek versi terbaru dari GitHub Releases.
        Returns version string jika ada update, None jika gagal atau sudah terbaru.
        """
        api_url = self.GITHUB_API.format(owner=self.owner, repo=self.repo)

        try:
            log.info(f"Mengecek update dari GitHub...")
            log.debug(f"API: {api_url}")

            req = urllib.request.Request(api_url)
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("User-Agent", f"NST-UpdateChecker/{self.current_version}")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                self.release_data = json.loads(resp.read().decode())

            # Parse version dari tag_name (format: "v3.2" atau "3.2")
            tag = self.release_data.get("tag_name", "")
            self.latest_version = tag.lstrip("vV")

            log.info(f"Versi lokal: {self.current_version}")
            log.info(f"Versi terbaru: {self.latest_version} (tag: {tag})")

            # Bandingkan versi
            if self._is_newer(self.latest_version, self.current_version):
                log.success(f"Update tersedia: {self.current_version} -> {self.latest_version}")
                return self.latest_version
            else:
                log.success("Aplikasi sudah versi terbaru!")
                return None

        except urllib.error.HTTPError as e:
            if e.code == 403:
                log.warning(f"Rate limit GitHub API tercapai. Coba lagi nanti.")
            elif e.code == 404:
                log.warning(f"Repository tidak ditemukan: {self.owner}/{self.repo}")
            else:
                log.warning(f"GitHub API error: {e.code} {e.reason}")
            return None
        except urllib.error.URLError as e:
            log.warning(f"Tidak bisa connect ke GitHub: {e.reason}")
            return None
        except (json.JSONDecodeError, Exception) as e:
            log.warning(f"Gagal parse response: {e}")
            return None

    def _is_newer(self, version_a: str, version_b: str) -> bool:
        """Bandingkan dua versi menggunakan packaging.version"""
        try:
            va = Version(version_a)
            vb = Version(version_b)
            return va > vb
        except (InvalidVersion, Exception):
            # Fallback: string comparison sederhana
            try:
                parts_a = [int(x) for x in re.findall(r'\d+', version_a)]
                parts_b = [int(x) for x in re.findall(r'\d+', version_b)]
                return parts_a > parts_b if parts_a and parts_b else version_a > version_b
            except Exception:
                return version_a > version_b

    def get_download_url(self, asset_pattern: str = "") -> Optional[str]:
        """Dapatkan URL download dari release terbaru"""
        if not self.release_data:
            return None

        assets = self.release_data.get("assets", [])
        if not assets:
            # Fallback: source code zip
            tag = self.release_data.get("tag_name", f"v{self.latest_version}")
            return self.GITHUB_DOWNLOAD.format(
                owner=self.owner, repo=self.repo,
                tag=tag, asset=f"{tag}.zip"
            )

        # Cari asset yang cocok dengan pattern
        if asset_pattern:
            for asset in assets:
                name = asset.get("name", "")
                if asset_pattern.lower() in name.lower():
                    return asset.get("browser_download_url")

        # Return asset pertama
        return assets[0].get("browser_download_url")

    def get_release_notes(self) -> str:
        """Dapatkan release notes dari release terbaru"""
        if not self.release_data:
            return "Tidak ada info release"
        return self.release_data.get("body", "Tidak ada catatan release").strip()

    @staticmethod
    def get_update_info(owner: str = "", repo: str = "") -> Dict:
        """
        Satu fungsi lengkap: cek update + tampilkan info.
        Returns dict dengan hasil pengecekan.
        """
        from config import VERSION
        checker = UpdateChecker(owner, repo, VERSION)

        result = {
            "checked": False,
            "has_update": False,
            "current_version": VERSION,
            "latest_version": None,
            "release_notes": "",
            "error": None,
        }

        latest = checker.check_latest()
        if latest:
            result["checked"] = True
            result["has_update"] = True
            result["latest_version"] = latest
            result["release_notes"] = checker.get_release_notes()
        elif latest is None:
            # Tidak error, berarti sudah terbaru atau gagal cek
            result["checked"] = True
            result["latest_version"] = checker.latest_version or VERSION
        else:
            result["error"] = "Gagal cek update"

        return result


class UpdateInstaller:
    """
    Download + install update secara otomatis.
    - Backup folder lama
    - Download release baru
    - Extract
    - Verifikasi
    """

    def __init__(self):
        from config import BASE_DIR
        self.base_dir = BASE_DIR
        self.backup_dir = os.path.join(BASE_DIR, "backups", "update_backups")
        os.makedirs(self.backup_dir, exist_ok=True)

    def backup_current(self) -> Optional[str]:
        """Backup folder aplikasi sebelum update"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"pre_update_{timestamp}.zip")

        log.info(f"Backup aplikasi sebelum update...")
        try:
            # Backup file-file penting (exclude backups, logs, tools)
            shutil.make_archive(
                backup_path.replace('.zip', ''),
                'zip',
                self.base_dir
            )
            log.success(f"Backup: {backup_path}")
            return backup_path
        except Exception as e:
            log.warning(f"Gagal backup: {e}")
            return None

    def download_update(self, url: str) -> Optional[str]:
        """Download file update"""
        temp_dir = os.path.join(self.base_dir, "temp_update")
        os.makedirs(temp_dir, exist_ok=True)

        filename = url.split("/")[-1]
        download_path = os.path.join(temp_dir, filename)

        log.info(f"Mendownload update: {filename}...")
        try:
            def report(block_count, block_size, total_size):
                if total_size > 0:
                    downloaded = block_count * block_size / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    percent = min(100, int(downloaded / total_mb * 100))
                    bar = "#" * (percent // 5) + "." * (20 - percent // 5)
                    print(f"\r  [{bar}] {percent}% ({downloaded:.1f}/{total_mb:.1f} MB)", end="")

            urllib.request.urlretrieve(url, download_path, report)
            print()
            log.success(f"Download selesai: {download_path}")
            return download_path
        except Exception as e:
            log.error(f"Download gagal: {e}")
            # Bersihkan file partial
            if os.path.exists(download_path):
                os.remove(download_path)
            return None

    def install_update(self, download_path: str) -> bool:
        """
        Install update dari file yang sudah di-download.
        Hanya extract file yang lebih baru (skip konfigurasi lokal).
        """
        log.info("Menginstall update...")

        try:
            # Buat temp directory untuk extract
            extract_dir = os.path.join(self.base_dir, "temp_update", "extracted")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            os.makedirs(extract_dir, exist_ok=True)

            # Extract
            if download_path.endswith('.zip'):
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(extract_dir)
            elif download_path.endswith('.tar.gz') or download_path.endswith('.tgz'):
                with tarfile.open(download_path, 'r:gz') as tf:
                    tf.extractall(extract_dir)
            else:
                log.error(f"Format file tidak didukung: {download_path}")
                return False

            # Cari folder utama di dalam extract
            extracted_items = os.listdir(extract_dir)
            source_dir = extract_dir
            if len(extracted_items) == 1:
                possible_dir = os.path.join(extract_dir, extracted_items[0])
                if os.path.isdir(possible_dir):
                    source_dir = possible_dir

            # Copy file baru (skip file konfigurasi lokal)
            skip_patterns = [
                "config.json", ".env", "device_compatibility.json",
                ".crash_sentinel", "logs/", "backups/", "reports/",
                "temp_update/", "__pycache__/", ".git/",
            ]

            copied = 0
            skipped = 0
            for root, dirs, files in os.walk(source_dir):
                # Dapatkan relative path
                rel_path = os.path.relpath(root, source_dir)
                if rel_path == ".":
                    rel_path = ""

                # Skip pattern
                should_skip = False
                for pattern in skip_patterns:
                    if pattern in rel_path:
                        should_skip = True
                        break
                if should_skip:
                    skipped += len(files)
                    continue

                # Pastikan direktori tujuan ada
                dest_root = os.path.join(self.base_dir, rel_path) if rel_path else self.base_dir
                os.makedirs(dest_root, exist_ok=True)

                for f in files:
                    src_file = os.path.join(root, f)
                    dst_file = os.path.join(dest_root, f)

                    # Skip konfigurasi lokal
                    if f in ["config.json", ".env", "device_compatibility.json"]:
                        skipped += 1
                        continue

                    try:
                        shutil.copy2(src_file, dst_file)
                        copied += 1
                    except Exception:
                        skipped += 1

            log.success(f"Update diinstall: {copied} files baru, {skipped} files skip")
            return True

        except Exception as e:
            log.error(f"Install update gagal: {e}")
            return False
        finally:
            # Bersihkan temp
            temp_dir = os.path.join(self.base_dir, "temp_update")
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

    def run_update_flow(self) -> bool:
        """
        Full update flow:
        1. Cek update
        2. Tampilkan info + release notes
        3. Konfirmasi user
        4. Backup
        5. Download
        6. Install
        7. Saran restart
        """
        log.header("[UPDATE CHECKER]")

        # Step 1: Cek update
        info = UpdateChecker.get_update_info()
        if not info["has_update"]:
            if info["latest_version"]:
                log.success(f"Aplikasi sudah versi terbaru: v{info['current_version']}")
            else:
                log.warning("Tidak bisa cek update (periksa koneksi internet)")
            return False

        # Step 2: Tampilkan info
        log.success(f"Update tersedia: v{info['current_version']} -> v{info['latest_version']}!")
        print()
        if info["release_notes"]:
            log.info("Release Notes:")
            for line in info["release_notes"].split('\n')[:15]:
                if line.strip():
                    print(f"  {Colors.DIM}{line}{Colors.RESET}")
            print()

        # Step 3: Konfirmasi
        if not ConfirmationChain.confirm_simple(
            f"Download & install update v{info['latest_version']}? (aplikasi akan direstart)", "n"
        ):
            log.info("Update dibatalkan.")
            return False

        # Step 4: Backup
        print()
        self.backup_current()

        # Step 5: Download
        print()
        url = UpdateChecker().get_download_url()
        if not url:
            log.warning("Tidak ada URL download")
            return False

        download_path = self.download_update(url)
        if not download_path:
            return False

        # Step 6: Install
        print()
        success = self.install_update(download_path)
        if success:
            ActionLogger.log("UPDATE", "SUCCESS", f"v{info['current_version']} -> v{info['latest_version']}")

            log.success("UPDATE BERHASIL!")
            log.info("Silakan restart aplikasi untuk menggunakan versi baru.")
            print()

            if ConfirmationChain.confirm_simple("Restart aplikasi sekarang?", "n"):
                log.info("Merestart aplikasi...")
                # Restart
                import subprocess
                import platform as _pf
                cmd = [sys.executable] + sys.argv
                if _pf.system() == "Windows":
                    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen(cmd)
                sys.exit(0)
        else:
            ActionLogger.log("UPDATE", "ERROR", f"Gagal install v{info['latest_version']}")
            log.error("UPDATE GAGAL! Coba manual.")
            log.info(f"Download: {url}")

        return success
