

"""
Plugin Loader — Auto-discovery + hot-reload untuk plugin NST.

Cara kerja:
1. Scan plugins/ directory untuk subdirectory
2. Cari file plugin.py di setiap subdirectory
3. Import dan register plugin
4. Support hot-reload (detect perubahan file)
"""


import os
import sys
import time
import logging
import importlib
import importlib.util
from typing import Dict, List, Optional, Tuple

from plugins import BasePlugin, PluginRegistry

log = logging.getLogger("nst.plugin.loader")

# Path ke directory plugins
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def discover_plugin_dirs() -> List[str]:
    """
    Scan plugins/ directory untuk subdirectory yang berisi plugin.
    Return list nama subdirectory (bukan path lengkap).
    """
    plugins = []
    if not os.path.isdir(PLUGIN_DIR):
        log.warning(f"Plugin directory tidak ditemukan: {PLUGIN_DIR}")
        return plugins

    for entry in sorted(os.listdir(PLUGIN_DIR)):
        entry_path = os.path.join(PLUGIN_DIR, entry)
        if entry.startswith("_"):
            continue  # skip __pycache__, __init__, dll.
        if os.path.isdir(entry_path):
            # Cek apakah ada plugin.py atau __init__.py
            if os.path.isfile(os.path.join(entry_path, "plugin.py")) or \
               os.path.isfile(os.path.join(entry_path, "__init__.py")):
                plugins.append(entry)
    
    return plugins


def import_plugin(plugin_name: str) -> Optional[BasePlugin]:
    """
    Import plugin dari subdirectory.
    
    Priority:
    1. plugin.py — file utama plugin (recommended)
    2. __init__.py — fallback
    
    Plugin Wajib memiliki:
    - Variabel `__plugin__` (instance BasePlugin) ATAU
    - Fungsi `register()` yang return BasePlugin instance
    """
    plugin_path = os.path.join(PLUGIN_DIR, plugin_name)
    
    # Cari file entry point
    entry_file = os.path.join(plugin_path, "plugin.py")
    if not os.path.exists(entry_file):
        entry_file = os.path.join(plugin_path, "__init__.py")
    if not os.path.exists(entry_file):
        log.warning(f"Plugin {plugin_name}: tidak ada plugin.py atau __init__.py")
        return None

    # Pastikan path ada di sys.path
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)
    if PLUGIN_DIR not in sys.path:
        sys.path.insert(0, PLUGIN_DIR)

    try:
        # Import module
        spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}", entry_file)
        if spec is None or spec.loader is None:
            log.warning(f"Plugin {plugin_name}: spec tidak valid")
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Cari plugin instance
        plugin: Optional[BasePlugin] = None
        
        if hasattr(module, "__plugin__"):
            plugin = module.__plugin__
        elif hasattr(module, "register"):
            result = module.register()
            if isinstance(result, BasePlugin):
                plugin = result
            elif isinstance(result, list):
                # register() bisa return list of plugins
                for p in result:
                    if isinstance(p, BasePlugin):
                        PluginRegistry.register(p)
                return result[0] if result else None

        if plugin is None:
            log.warning(f"Plugin {plugin_name}: tidak ada __plugin__ atau register()")
            return None

        return plugin

    except Exception as e:
        log.error(f"Plugin {plugin_name}: gagal load — {e}")
        import traceback
        log.debug(traceback.format_exc())
        return None


def load_all_plugins() -> int:
    """
    Load SEMUA plugin dari plugins/ directory.
    Return jumlah plugin yang berhasil di-load.
    """
    loaded = 0
    plugin_dirs = discover_plugin_dirs()

    log.info(f"Menemukan {len(plugin_dirs)} plugin directory: {plugin_dirs}")

    for dir_name in plugin_dirs:
        plugin = import_plugin(dir_name)
        if plugin is not None:
            if PluginRegistry.register(plugin):
                loaded += 1
                log.info(f"  ✅ Plugin terdaftar: {plugin.name} v{plugin.version}")
            else:
                log.warning(f"  ⚠️ Plugin {plugin.name} sudah terdaftar (skip)")

    log.info(f"Total: {loaded} plugin berhasil di-load")
    return loaded


def reload_plugin(plugin_name: str) -> bool:
    """
    Hot-reload plugin tertentu.
    Hapus dari registry, clear module cache, lalu import ulang.
    """
    # Unregister dulu
    PluginRegistry.unregister(plugin_name)

    # Clear module cache
    module_keys = [
        f"plugins.{plugin_name}",
        f"plugins.{plugin_name}.plugin",
        f"plugins.{plugin_name}.__init__",
    ]
    for key in module_keys:
        if key in sys.modules:
            del sys.modules[key]

    # Reload
    plugin = import_plugin(plugin_name)
    if plugin and PluginRegistry.register(plugin):
        log.info(f"  ✅ Reload: {plugin.name}")
        return True
    
    log.warning(f"  ❌ Reload gagal: {plugin_name}")
    return False


def load_plugin_by_path(path: str) -> Optional[BasePlugin]:
    """
    Load plugin dari path absolut (untuk development/testing).
    """
    if not os.path.isfile(path):
        log.warning(f"File tidak ditemukan: {path}")
        return None

    plugin_name = os.path.splitext(os.path.basename(path))[0]
    
    spec = importlib.util.spec_from_file_location(f"plugins.custom.{plugin_name}", path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "__plugin__"):
        return module.__plugin__
    if hasattr(module, "register"):
        return module.register()

    return None


def get_plugin_status() -> List[Dict]:
    """
    Return status semua plugin untuk display.
    """
    plugins = PluginRegistry.get_all_plugins()
    result = []
    for p in plugins:
        result.append({
            "name": p.name,
            "version": p.version,
            "description": p.description[:80] if p.description else "",
            "author": p.author,
            "modes": [str(m) for m in p.supported_modes()[:8]],
            "mode_count": len(p.supported_modes()),
        })
    return result


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Plugin Discovery ===")
    dirs = discover_plugin_dirs()
    print(f"Found directories: {dirs}")
    
    count = load_all_plugins()
    print(f"\n=== Loaded: {count} plugins ===")
    print(PluginRegistry.summary())