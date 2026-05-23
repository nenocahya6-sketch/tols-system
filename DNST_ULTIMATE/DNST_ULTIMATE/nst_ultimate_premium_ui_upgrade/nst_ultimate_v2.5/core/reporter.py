
"""
NST Report Generator
Membuat laporan hasil diagnosa/service dalam format HTML dan TXT
Untuk diberikan ke customer atau dokumentasi
"""
import os
from datetime import datetime
from typing import Dict, List, Optional

from core.logger import log

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


class ReportGenerator:
    """Generate laporan dalam berbagai format"""

    @staticmethod
    def ensure_report_dir():
        os.makedirs(REPORT_DIR, exist_ok=True)
        return REPORT_DIR

    @staticmethod
    def generate_html(title: str, data: Dict, filename: str = None) -> str:
        """Generate laporan HTML"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not filename:
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        report_dir = ReportGenerator.ensure_report_dir()
        filepath = os.path.join(report_dir, filename)

        # Build HTML
        rows = ""
        for section, content in data.items():
            if isinstance(content, dict):
                rows += f"""
                <tr><td colspan="2" class="section">{section}</td></tr>
                """
                for k, v in content.items():
                    status = "ok" if v and v not in ["False", "Tidak", "X", "Error"] else "fail"
                    rows += f"""
                    <tr class="{status}">
                        <td class="key">{k}</td>
                        <td class="val">{v if v else '-'}</td>
                    </tr>
                    """
            elif isinstance(content, list):
                rows += f"""
                <tr><td colspan="2" class="section">{section}</td></tr>
                """
                for item in content:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            rows += f"""
                            <tr>
                                <td class="key">{k}</td>
                                <td class="val">{v if v else '-'}</td>
                            </tr>
                            """
                    else:
                        rows += f"""
                        <tr>
                            <td class="key">-</td>
                            <td class="val">{item}</td>
                        </tr>
                        """
            else:
                rows += f"""
                <tr>
                    <td class="key">{section}</td>
                    <td class="val">{content}</td>
                </tr>
                """

        html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1a237e, #283593); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .header .sub {{ opacity: 0.8; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        tr.section td {{ background: #e8eaf6; font-weight: bold; padding: 12px 20px; font-size: 14px; color: #283593; }}
        tr.ok td {{ background: #f1f8e9; }}
        tr.fail td {{ background: #fff3e0; }}
        td.key {{ padding: 10px 20px; width: 40%; color: #555; font-size: 13px; border-bottom: 1px solid #eee; }}
        td.val {{ padding: 10px 20px; font-weight: 500; color: #333; font-size: 13px; border-bottom: 1px solid #eee; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="sub">Generated: {timestamp}</div>
        </div>
        <table>
            {rows}
        </table>
        <div class="footer">
            NST Ultimate Console - Professional Service Tool<br>
            &copy; 2024 NST. All rights reserved.
        </div>
    </div>
</body>
</html>"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        log.success(f"Report: {filepath}")
        return filepath

    @staticmethod
    def generate_txt(title: str, data: Dict, filename: str = None) -> str:
        """Generate laporan TXT"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not filename:
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        report_dir = ReportGenerator.ensure_report_dir()
        filepath = os.path.join(report_dir, filename)

        lines = [
            "=" * 60,
            f"  {title}",
            f"  Generated: {timestamp}",
            "=" * 60,
            ""
        ]

        for section, content in data.items():
            lines.append(f"[ {section} ]")
            lines.append("-" * 40)
            if isinstance(content, dict):
                for k, v in content.items():
                    lines.append(f"  {k}: {v if v else '-'}")
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            lines.append(f"  {k}: {v if v else '-'}")
                    else:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"  {content}")
            lines.append("")

        lines.extend([
            "=" * 60,
            "  NST Ultimate Console - Professional Service Tool",
            "=" * 60
        ])

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        log.success(f"Report: {filepath}")
        return filepath

    @staticmethod
    def list_reports() -> List[Dict]:
        """Daftar semua report"""
        ReportGenerator.ensure_report_dir()
        reports = []
        if os.path.exists(REPORT_DIR):
            for f in sorted(os.listdir(REPORT_DIR), reverse=True):
                fpath = os.path.join(REPORT_DIR, f)
                if os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    modified = datetime.fromtimestamp(os.path.getmtime(fpath))
                    reports.append({
                        "name": f,
                        "path": fpath,
                        "size_kb": round(size / 1024, 1),
                        "type": "HTML" if f.endswith('.html') else "TXT" if f.endswith('.txt') else "Unknown",
                        "modified": modified.strftime("%Y-%m-%d %H:%M:%S")
                    })
        return reports

    @staticmethod
    def show_reports():
        """Tampilkan daftar report"""
        log.header("[MANAGER REPORT]")
        reports = ReportGenerator.list_reports()

        if not reports:
            log.info("Belum ada report")
            return

        for i, r in enumerate(reports, 1):
            print(f"  {i}. {r['name']}")
            print(f"     {r['type']} | {r['size_kb']} KB | {r['modified']}")

        print()
        choice = input("  Pilih report [1-N] atau Enter: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(reports):
            report = reports[int(choice)-1]
            try:
                if report['type'] == 'HTML':
                    import webbrowser
                    webbrowser.open(f"file://{os.path.abspath(report['path'])}")
                    log.info(f"Membuka {report['name']} di browser...")
                else:
                    import subprocess
                    if os.name == 'nt':
                        os.startfile(report['path'])
                    else:
                        subprocess.run(['xdg-open', report['path']], timeout=5)
                    log.info(f"Membuka {report['name']}...")
            except Exception as e:
                log.warning(f"Tidak bisa buka file: {e}")

    @staticmethod
    def clean_old_reports(days: int = 30):
        """Hapus report yang lebih lama dari N hari"""
        ReportGenerator.ensure_report_dir()
        now = datetime.now()
        count = 0
        for f in os.listdir(REPORT_DIR):
            fpath = os.path.join(REPORT_DIR, f)
            if os.path.isfile(fpath):
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if (now - mtime).days > days:
                    os.remove(fpath)
                    count += 1
        if count:
            log.info(f"{count} report lama dihapus")


def run():
    """Jalankan Report Manager"""
    ReportGenerator.show_reports()

def run_clean():
    """Bersihkan report lama"""
    ReportGenerator.clean_old_reports()
