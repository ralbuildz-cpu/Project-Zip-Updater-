#!/usr/bin/env python3
"""
ZIP Update Tool – hassle‑free selective file update from a ZIP archive.
Compares a ZIP file against your live project, lets you pick which files to overwrite,
backs up originals, and optionally launches the version manager.
"""

import os
import sys
import shutil
import hashlib
import zipfile
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

# ==================== CONFIG ====================
SCRIPT_PATH = Path(__file__).resolve()
LIVE_ROOT = SCRIPT_PATH.parent
SCRIPT_NAME = SCRIPT_PATH.name

# ==================== RAW KEYBOARD INPUT ====================
# Cross-platform single key press without Enter
if os.name == 'nt':
    import msvcrt
    
    def _get_key():
        """Return the character of a single keypress on Windows, handling arrow keys."""
        try:
            ch = msvcrt.getch()
            if ch == b'\xe0':  # Arrow keys and some others
                ch2 = msvcrt.getch()
                if ch2 == b'H': return 'UP'
                if ch2 == b'P': return 'DOWN'
                if ch2 == b'M': return 'RIGHT'
                if ch2 == b'K': return 'LEFT'
                return None
            return ch.decode('utf-8', errors='ignore')
        except:
            return None
else:
    import termios
    import tty
    import sys
    import select

    def _init_raw_input():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        return old

    def _restore_input(old):
        fd = sys.stdin.fileno()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def _get_key():
        if select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': return 'UP'
                    elif ch3 == 'B': return 'DOWN'
                    elif ch3 == 'C': return 'RIGHT'
                    elif ch3 == 'D': return 'LEFT'
                    elif ch3 == '5':  # Page Up
                        sys.stdin.read(1)
                        return 'PAGE_UP'
                    elif ch3 == '6':  # Page Down
                        sys.stdin.read(1)
                        return 'PAGE_DOWN'
                return None
            return ch
        return None

# ==================== DISPLAY HELPERS ====================
def header():
    """Clear screen and print main header."""
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n  " + "=" * 50)
    print("    ZIP UPDATE TOOL")
    print("  " + "=" * 50 + "\n")

def ok(msg):   print(f"  [OK] {msg}" + "\033[0m")
def err(msg):  print(f"  [!!] {msg}" + "\033[0m")
def info(msg): print(f"       {msg}")
def warn(msg): print(f"  [>>] {msg}")

def pause():
    input("\n  Press Enter to continue...")

def pause_error():
    input("\n  Press Enter to close this message and exit...")

# ==================== ANSI TERMINAL HELPERS ====================
def clear_line():
    sys.stdout.write('\033[2K')  # clear entire line

def move_home():
    sys.stdout.write('\033[H')   # move cursor to home (row 1, col 1)

def get_terminal_height():
    try:
        return shutil.get_terminal_size().lines
    except:
        return 40  # fallback

HEADER_HEIGHT = 7  # approximate lines used by header and info

# ==================== SCROLLING SELECTION ====================
def scroll_select(items, title="", shortcuts=None, page_size=20):
    """
    Display a scrollable list of items. Returns the selected item (or None if cancelled).
    'items' is a list of (display_string, value) where value is returned on selection.
    'shortcuts' is a dict of key: (description, callback) for special actions.
    """
    if shortcuts is None:
        shortcuts = {}
    total = len(items)
    cursor = 0
    top = 0
    term_height = get_terminal_height()

    # Save terminal state for raw input
    if os.name != 'nt':
        old_term = _init_raw_input()
    else:
        old_term = None

    try:
        # Clear screen once at start
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

        while True:
            move_home()

            # Print header (without using header() which clears)
            print("  " + "=" * 50)
            print("    ZIP UPDATE TOOL")
            print("  " + "=" * 50)
            print(f"  {title}")
            print("  ---------------------------------------------")
            print(f"  Total: {total} item(s). Use ↑/↓ to move, Enter to select.")
            if shortcuts:
                shortcut_text = ", ".join(f"'{k}'={desc}" for k, (desc, _) in shortcuts.items())
                print(f"  Shortcuts: {shortcut_text}  'q'=quit")
            else:
                print("  Press 'q' to quit")
            print()

            # Determine visible range
            if cursor < top:
                top = cursor
            elif cursor >= top + page_size:
                top = cursor - page_size + 1
            end = min(top + page_size, total)

            # Print visible items
            for i in range(top, end):
                clear_line()
                prefix = "  >" if i == cursor else "   "
                display = items[i][0]
                print(f"  {prefix} {display}")
            # Clear remaining lines up to page_size
            for i in range(end - top, page_size):
                clear_line()
                print()
            # Clear any extra lines beyond page_size up to terminal height
            extra_lines = term_height - HEADER_HEIGHT - page_size - 2
            if extra_lines > 0:
                for _ in range(extra_lines):
                    clear_line()
                    print()

            sys.stdout.flush()

            key = _get_key()
            if key is None:
                continue

            if key.lower() == 'q':
                return None
            
            if key in shortcuts:
                callback = shortcuts[key][1]
                result = callback()
                if result is not None:
                    return result
                continue

            if key == 'UP':
                cursor = max(0, cursor - 1)
            elif key == 'DOWN':
                cursor = min(total - 1, cursor + 1)
            elif key == 'PAGE_UP':
                cursor = max(0, cursor - page_size)
            elif key == 'PAGE_DOWN':
                cursor = min(total - 1, cursor + page_size)
            elif key == '\r' or key == '\n':
                if total > 0:
                    return items[cursor][1]
    finally:
        if old_term is not None:
            _restore_input(old_term)

# ==================== MULTI-SELECT WITH SCROLLING ====================
def multi_select(items, title="", page_size=20):
    """
    Scrollable multi-select list. Returns list of selected values.
    Items is a list of (display_string, value).
    Use ↑/↓ to move, Space to toggle, Enter to confirm, 'q' to cancel.
    """
    total = len(items)
    cursor = 0
    top = 0
    selected = [False] * total
    term_height = get_terminal_height()

    if os.name != 'nt':
        old_term = _init_raw_input()
    else:
        old_term = None

    try:
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

        while True:
            move_home()
            print("  " + "=" * 50)
            print("    ZIP UPDATE TOOL")
            print("  " + "=" * 50)
            print(f"  {title}")
            print("  ---------------------------------------------")
            print(f"  Total: {total} item(s). Use ↑/↓ to move, Space to toggle, Enter to confirm.")
            print("  Press 'q' to cancel without selecting.")
            print()

            if cursor < top:
                top = cursor
            elif cursor >= top + page_size:
                top = cursor - page_size + 1
            end = min(top + page_size, total)

            for i in range(top, end):
                clear_line()
                prefix = "  >" if i == cursor else "   "
                marker = "[X]" if selected[i] else "[ ]"
                display = items[i][0]
                print(f"  {prefix} {marker} {display}")
            for i in range(end - top, page_size):
                clear_line()
                print()
            extra_lines = term_height - HEADER_HEIGHT - page_size - 2
            if extra_lines > 0:
                for _ in range(extra_lines):
                    clear_line()
                    print()

            sys.stdout.flush()

            key = _get_key()
            if key is None:
                continue
            if key.lower() == 'q':
                return None
            if key == 'UP':
                cursor = max(0, cursor - 1)
            elif key == 'DOWN':
                cursor = min(total - 1, cursor + 1)
            elif key == 'PAGE_UP':
                cursor = max(0, cursor - page_size)
            elif key == 'PAGE_DOWN':
                cursor = min(total - 1, cursor + page_size)
            elif key == ' ':
                selected[cursor] = not selected[cursor]
            elif key == '\r' or key == '\n':
                result = [items[i][1] for i in range(total) if selected[i]]
                return result
    finally:
        if old_term is not None:
            _restore_input(old_term)

# ==================== FILE UTILITIES ====================
def get_file_hash(filepath):
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None

def safe_copy(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

# ==================== ZIP FILE SELECTION (SCROLLABLE) ====================
def get_downloads_folder():
    if os.name == 'nt':
        return Path(os.environ.get('USERPROFILE', '~')) / 'Downloads'
    else:
        return Path.home() / 'Downloads'

def get_available_drives():
    drives = []
    if os.name == 'nt':
        import string
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(f"{letter}:")
    return drives

def list_zip_files(folder):
    zips = []
    try:
        for item in folder.iterdir():
            if item.is_file() and item.suffix.lower() == '.zip':
                zips.append((item, item.stat().st_mtime))
        zips.sort(key=lambda x: x[1], reverse=True)
    except PermissionError:
        pass
    return zips

def select_zip_file():
    current_dir = get_downloads_folder()
    if not current_dir.exists():
        current_dir = Path.cwd()

    while True:
        drives = get_available_drives()
        dirs = []
        try:
            for d in current_dir.iterdir():
                if d.is_dir() and not d.name.startswith('.'):
                    dirs.append(d)
        except PermissionError:
            pass
        dirs.sort(key=lambda x: x.name.lower())
        zips = list_zip_files(current_dir)

        items = []
        items.append(("..  (up one level)", ".."))
        for drv in drives:
            items.append((f"[DRV] {drv}", Path(drv + "\\")))
        for d in dirs:
            items.append((f"[DIR] {d.name}", d))
        for z, mtime in zips:
            dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            items.append((f"{z.name}  ({dt})", z))

        title = f"Current folder: {current_dir}"
        shortcuts = {
            'u': ("up one level", lambda: ".." if current_dir.parent != current_dir else None),
            'r': ("root", lambda: Path(current_dir.drive + '\\') if os.name == 'nt' else Path('/')),
            'h': ("home", lambda: Path.home()),
            'dl': ("Downloads", lambda: get_downloads_folder() if get_downloads_folder().exists() else None),
        }

        selected = scroll_select(items, title, shortcuts)
        if selected is None:
            return None
        if selected == "..":
            parent = current_dir.parent
            if parent != current_dir:
                current_dir = parent
                continue
            else:
                warn("Already at the root.")
                pause()
                continue
        if isinstance(selected, Path):
            if selected.is_dir():
                current_dir = selected
                continue
            else:
                return selected
        if isinstance(selected, str) and len(selected) == 2 and selected[1] == ':':
            current_dir = Path(selected + "\\")
            continue

# ==================== COMPARE ZIP WITH LIVE ====================
def extract_zip(zip_path):
    temp_dir = Path(tempfile.mkdtemp(prefix="zip_update_"))
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(temp_dir)
    return temp_dir

def get_common_prefix(paths):
    if not paths:
        return None
    split_paths = [Path(p).parts for p in paths]
    min_len = min(len(p) for p in split_paths)
    if min_len == 0:
        return None
    common = []
    for i in range(min_len):
        first = split_paths[0][i]
        if all(p[i] == first for p in split_paths):
            common.append(first)
        else:
            break
    if not common:
        return None
    if len(common) == 1 and all(len(p) >= 2 for p in split_paths):
        return Path(common[0])
    return None

def compare_files(zip_root, live_root):
    changed = []
    new_files = []
    missing_in_zip = []

    zip_files = set()
    for root, dirs, files in os.walk(zip_root):
        rel_root = Path(root).relative_to(zip_root)
        for f in files:
            rel_path = rel_root / f
            zip_files.add(str(rel_path))

    prefix = get_common_prefix(list(zip_files))
    if prefix:
        info(f"Stripping common top-level directory: '{prefix}'")
        stripped_to_original = {}
        for p in zip_files:
            p_path = Path(p)
            if p_path.parts[0] == prefix.name:
                stripped = str(p_path.relative_to(prefix))
                stripped_to_original[stripped] = p
        for stripped, original in stripped_to_original.items():
            zip_file = zip_root / original
            live_file = live_root / stripped
            if stripped == SCRIPT_NAME or stripped == ".gitignore":
                continue
            if not live_file.exists():
                changed.append(stripped)
                new_files.append(stripped)
            else:
                zip_hash = get_file_hash(zip_file)
                live_hash = get_file_hash(live_file)
                if zip_hash != live_hash:
                    changed.append(stripped)
        stripped_set = set(stripped_to_original.keys())
        for root, dirs, files in os.walk(live_root):
            rel_root = Path(root).relative_to(live_root)
            if ".git" in rel_root.parts:
                continue
            for f in files:
                rel_path = str(rel_root / f)
                if rel_path == SCRIPT_NAME or rel_path == ".gitignore":
                    continue
                if rel_path not in stripped_set:
                    missing_in_zip.append(rel_path)
    else:
        for rel_path in zip_files:
            zip_file = zip_root / rel_path
            live_file = live_root / rel_path
            if rel_path == SCRIPT_NAME or rel_path == ".gitignore":
                continue
            if not live_file.exists():
                changed.append(rel_path)
                new_files.append(rel_path)
            else:
                zip_hash = get_file_hash(zip_file)
                live_hash = get_file_hash(live_file)
                if zip_hash != live_hash:
                    changed.append(rel_path)
        for root, dirs, files in os.walk(live_root):
            rel_root = Path(root).relative_to(live_root)
            if ".git" in rel_root.parts:
                continue
            for f in files:
                rel_path = str(rel_root / f)
                if rel_path == SCRIPT_NAME or rel_path == ".gitignore":
                    continue
                if rel_path not in zip_files:
                    missing_in_zip.append(rel_path)

    return changed, new_files, missing_in_zip

# ==================== INTERACTIVE SELECTION WITH SCROLLING ====================
def select_files_to_update(changed, new_files, missing):
    if not changed:
        info("No files differ from the ZIP. Nothing to update.")
        pause()
        return []

    items = []
    for rel in changed:
        status = "[NEW]" if rel in new_files else "[MODIFIED]"
        display = f"{status}  {rel}"
        items.append((display, rel))

    title = f"FILES TO UPDATE  (Total: {len(changed)})"
    if missing:
        title += f"  [Note: {len(missing)} files in live folder not in ZIP]"

    selected_rel_paths = multi_select(items, title)
    if selected_rel_paths is None:
        return []
    if not selected_rel_paths:
        info("No files selected.")
        return []
    
    print(f"\n  You selected {len(selected_rel_paths)} file(s).")
    for s in selected_rel_paths:
        print(f"    - {s}")
    confirm = input("\n  Proceed with update? (Y/N): ").strip().lower()
    if confirm == 'y':
        return selected_rel_paths
    else:
        info("Selection cancelled.")
        return []

# ==================== PERFORM UPDATE ====================
def perform_update(zip_root, live_root, selected_files, create_backups=True):
    backup_paths = []
    zip_files = []
    for root, dirs, files in os.walk(zip_root):
        rel_root = Path(root).relative_to(zip_root)
        for f in files:
            zip_files.append(str(rel_root / f))
    prefix = get_common_prefix(zip_files) if zip_files else None

    for rel_path in selected_files:
        if prefix:
            orig_path = prefix / rel_path
            src = zip_root / orig_path
        else:
            src = zip_root / rel_path
        dst = live_root / rel_path

        if not src.exists():
            warn(f"Source file not found: {src}. Skipping.")
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)

        if create_backups and dst.exists():
            bak_path = dst.with_suffix(dst.suffix + ".bak")
            shutil.copy2(dst, bak_path)
            backup_paths.append(bak_path)

        try:
            shutil.copy2(src, dst)
            ok(f"Updated: {rel_path}")
        except Exception as e:
            err(f"Failed to update {rel_path}: {e}")

    return backup_paths

# ==================== MAIN ====================
def main():
    zip_path = select_zip_file()
    if zip_path is None:
        print("\n  Exited by user.")
        sys.exit(0)

    # Restore normal terminal mode after raw input
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()

    header()
    print(f"  Selected ZIP: {zip_path}")
    print("  Extracting...")
    try:
        temp_dir = extract_zip(zip_path)
    except Exception as e:
        err(f"Failed to extract ZIP: {e}")
        pause_error()
        sys.exit(1)

    ok("Extraction complete.")

    changed, new_files, missing = compare_files(temp_dir, LIVE_ROOT)

    if not changed:
        info("No differences found. Nothing to update.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        pause()
        return

    selected = select_files_to_update(changed, new_files, missing)
    if not selected:
        info("No files selected. Exiting.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        pause()
        return

    header()
    print("  UPDATING FILES...")
    print("  ---------------------------------------------\n")
    backup_paths = perform_update(temp_dir, LIVE_ROOT, selected, create_backups=True)

    shutil.rmtree(temp_dir, ignore_errors=True)

    if backup_paths:
        print(f"\n  Created {len(backup_paths)} backup files with .bak extension.")
        choice = input("  Delete these backup files now? (Y/N): ").strip().lower()
        if choice == 'y':
            for bak in backup_paths:
                try:
                    bak.unlink()
                    info(f"Deleted: {bak}")
                except Exception as e:
                    warn(f"Could not delete {bak}: {e}")
        else:
            info("Backup files kept. You can delete them manually later.")

    ok(f"Update complete. {len(selected)} file(s) overwritten.")

    vmanager = LIVE_ROOT / "version_manager.py"
    if vmanager.exists():
        print("\n  A version manager script (version_manager.py) was found.")
        choice = input("  Do you want to run it now to save a version of these changes? (Y/N): ").strip().lower()
        if choice == 'y':
            try:
                subprocess.run([sys.executable, str(vmanager)], cwd=str(LIVE_ROOT))
            except Exception as e:
                err(f"Could not launch version manager: {e}")
                pause_error()
    else:
        info("No version_manager.py found in this folder. You can save changes manually.")

    pause()
    print("\n  Done.")
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  👋 Exited by user.")
        sys.exit(0)