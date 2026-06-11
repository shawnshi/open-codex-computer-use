import sys
import os
import json
import subprocess
import threading
import logging
import ctypes
import time
from ctypes import wintypes
from pathlib import Path

# ---------- Configuration & Logging ----------
log_file = Path(os.environ.get("USERPROFILE", "C:\\")) / ".gemini" / "mcp_proxy_v3.log"
logging.basicConfig(filename=str(log_file), level=logging.INFO, format="%(asctime)s - %(message)s")

EXE_PATH = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "open-computer-use" / "dist" / "windows" / "amd64" / "open-computer-use.exe"
LOCK_FILE = Path(os.environ.get("USERPROFILE", "C:\\")) / ".gemini" / "open_computer_use_mcp.lock"

last_known_tree_lines = []
target_window_title = ""

# ---------- Sprint 2: DPI Matrix ----------
def get_dpi_scale_factor():
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        hdc = user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except: return 1.0

DPI_SCALE = get_dpi_scale_factor()

# ---------- Sprint 3 (Task 3.1): Focus Guard & Idle Detection ----------
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

def get_idle_time_ms():
    """Returns the number of milliseconds since the last user input (mouse/keyboard)"""
    user32 = ctypes.windll.user32
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis
    return 0

def get_foreground_window_title():
    """Returns the title of the currently focused window"""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def should_block_intrusive_action(app_target_name: str) -> bool:
    """
    Core Sprint 3 Logic:
    If the user has been active in the last 2 seconds (typing/moving mouse),
    AND the foreground window is NOT our target app,
    block the action to prevent focus stealing and "typing into the wrong chat" illusions.
    """
    idle_ms = get_idle_time_ms()
    fg_title = get_foreground_window_title()
    
    # If user is idle for > 2.5 seconds, it's safe to steal focus and execute
    if idle_ms > 2500:
        return False
        
    # If the user is active, but they are actively looking at the Target App, it's safe (pair programming mode)
    if app_target_name and app_target_name.lower() in fg_title.lower():
        return False
        
    # User is active in ANOTHER window. We must block!
    logging.warning(f"Focus Guard Triggered! User is active in '{fg_title}'. Idle time: {idle_ms}ms. Blocking action on '{app_target_name}'.")
    return True

# ---------- Middleware Logic ----------

def filter_uia_tree(tree_text: str) -> str:
    global last_known_tree_lines, target_window_title
    lines = tree_text.split('\n')
    filtered_lines = []
    
    for line in lines:
        lower_line = line.lower()
        if "window: " in lower_line:
            # Extract target window title for Sprint 3
            try:
                target_window_title = line.split('"')[1]
            except: pass
            
        if "secondary actions:" in lower_line or "app=" in lower_line or "window:" in lower_line:
            filtered_lines.append(line)
        elif " window " in lower_line or " title bar " in lower_line or " menu " in lower_line:
            filtered_lines.append(line)
        else:
            if " pane " in lower_line or " group " in lower_line or " separator " in lower_line:
                continue
            filtered_lines.append(line)
            
    last_known_tree_lines = filtered_lines
    return '\n'.join(filtered_lines)

def smart_locator_fallback(original_index: int, target_name: str) -> int:
    if not last_known_tree_lines or not target_name: return original_index
    for line in last_known_tree_lines:
        line_stripped = line.strip()
        if line_stripped.startswith(f"{original_index} "):
            if target_name.lower() in line_stripped.lower():
                return original_index
            else: break
                
    best_match_index = original_index
    min_dist = 9999
    for line in last_known_tree_lines:
        line_stripped = line.strip()
        if target_name.lower() in line_stripped.lower():
            try:
                idx = int(line_stripped.split(' ')[0])
                dist = abs(idx - original_index)
                if dist < min_dist:
                    min_dist = dist; best_match_index = idx
            except: pass
    return best_match_index

def scale_coordinates(params: dict):
    if DPI_SCALE == 1.0: return
    for key in ['x', 'y', 'start_x', 'start_y', 'end_x', 'end_y']:
        if key in params and isinstance(params[key], (int, float)):
            params[key] = int(params[key] * DPI_SCALE)

# ---------- Stdio Pipelines ----------

def process_stdout(proc):
    for line in iter(proc.stdout.readline, b''):
        try:
            msg_str = line.decode('utf-8').strip()
            if not msg_str: continue
            
            msg = json.loads(msg_str)
            if "result" in msg and "content" in msg["result"]:
                for block in msg["result"]["content"]:
                    if block.get("type") == "text" and "Window:" in block.get("text", ""):
                        block["text"] = filter_uia_tree(block["text"])
                        
            sys.stdout.write(json.dumps(msg) + '\n')
            sys.stdout.flush()
        except Exception:
            sys.stdout.buffer.write(line)
            sys.stdout.flush()

def process_stdin(proc):
    global target_window_title
    for line in sys.stdin:
        try:
            msg_str = line.decode('utf-8').strip()
            if msg_str.startswith("{"):
                msg = json.loads(msg_str)
                
                if "method" in msg and msg["method"] == "tools/call":
                    tool_name = msg.get("params", {}).get("name")
                    tool_args = msg.get("params", {}).get("arguments", {})
                    req_id = msg.get("id")
                    
                    # Sprint 3: Focus Guard Interception
                    if tool_name in ["click", "type_text", "press_key", "set_value"]:
                        # Target app could be explicitly passed in args or inferred from last get_app_state
                        app_name = tool_args.get("app", target_window_title)
                        if should_block_intrusive_action(app_name):
                            # Reject the request gracefully back to the Agent
                            reject_msg = {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "isError": True,
                                    "content": [{"type": "text", "text": "Focus Guard Blocked: User is actively typing or using the mouse in another window. Backing off to prevent interference. Please sleep and retry later."}]
                                }
                            }
                            sys.stdout.write(json.dumps(reject_msg) + '\n')
                            sys.stdout.flush()
                            continue # DO NOT forward to .exe
                    
                    # Sprint 2: Smart Locator
                    if tool_name in ["click", "set_value"] and "element_index" in tool_args:
                        target_name = tool_args.pop("element_name_fallback", None)
                        if target_name:
                            tool_args["element_index"] = smart_locator_fallback(tool_args["element_index"], target_name)
                            
                    # Sprint 2: DPI Injection
                    if tool_name in ["click", "drag"]:
                        scale_coordinates(tool_args)
                        
                proc.stdin.write(json.dumps(msg).encode('utf-8') + b'\n')
            else:
                proc.stdin.write(line.encode('utf-8'))
            proc.stdin.flush()
        except Exception as e:
            logging.error(f"Stdin interception error: {e}")
            break

def main():
    if LOCK_FILE.exists():
        try: os.remove(LOCK_FILE)
        except PermissionError:
            sys.exit(1)
            
    try:
        with open(LOCK_FILE, "w") as f: f.write(str(os.getpid()))
        proc = subprocess.Popen([str(EXE_PATH), "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr)
        
        t1 = threading.Thread(target=process_stdout, args=(proc,))
        t2 = threading.Thread(target=process_stdin, args=(proc,))
        t1.start()
        t2.start()
        t1.join()
        
    finally:
        if LOCK_FILE.exists():
            try: os.remove(LOCK_FILE)
            except: pass

if __name__ == "__main__":
    main()
