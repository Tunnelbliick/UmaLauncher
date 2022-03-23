import pystray
import asyncio
import os
import threading
from PIL import Image
import time
import win32api
import win32gui
import pywintypes
from pypresence import Presence
from elevate import elevate
from PIL import Image
import pyautogui
from screenstate import ScreenState
import nordvpn_connect as nord

elevate()

gaem = None
gaem_got = False

dmm = None
dmm_got = False

scaling_thread = None
stop_threads = False

icon = None

first_orientation = True
was_portrait = True

prev_height = 0


client_id = 954453106765225995
last_screen = time.time()
last_rpc_update = time.time()
rpc = Presence(client_id)
rpc.connect()
screen_state = ScreenState()
rpc_next = {"details": "Launching game..."}


# VPN
vpn_settings = nord.initialize_vpn("Japan")


def _get_dmm(hwnd, lParam):
    global dmm
    if win32gui.IsWindowVisible(hwnd):
        if "DMM GAME PLAYER" in win32gui.GetWindowText(hwnd):
            dmm = hwnd


def get_dmm():
    global dmm_got
    win32gui.EnumWindows(_get_dmm, None)
    if dmm:
        dmm_got = True


def _get_game(hwnd, lParam):
    global gaem
    if win32gui.IsWindowVisible(hwnd):
        if win32gui.GetWindowText(hwnd) == "umamusume":
            gaem = hwnd


def get_game():
    global gaem
    global gaem_got
    global prev_height
    win32gui.EnumWindows(_get_game, None)
    if gaem:
        gaem_got = True
        cur_gaem_rect = win32gui.GetWindowRect(gaem)
        prev_height = cur_gaem_rect[3] - cur_gaem_rect[1]


def get_workspace():
    global gaem
    if gaem:
        monitor = win32api.MonitorFromWindow(gaem)
        return win32api.GetMonitorInfo(monitor).get("Work") if monitor else None
    else:
        return None

def start_async(icon):
    asyncio.run(main())


def on_clicked(icon, item):
    global stop_threads
    stop_threads = True
    icon.stop()


def is_portrait() -> bool:
    global gaem
    cur_gaem_rect = win32gui.GetWindowRect(gaem)
    cur_height = cur_gaem_rect[3] - cur_gaem_rect[1]
    cur_width = cur_gaem_rect[2] - cur_gaem_rect[0]
    return cur_height > cur_width


def scale_height():
    global gaem
    global was_portrait
    global first_orientation
    global prev_height

    workspace = get_workspace()
    if workspace:
        jank_resize = False
        cur_gaem_rect = win32gui.GetWindowRect(gaem)
        cur_height = cur_gaem_rect[3] - cur_gaem_rect[1]
        cur_width = cur_gaem_rect[2] - cur_gaem_rect[0]
        if prev_height - cur_height > 250:
            jank_resize = True

        jank_offset = 7
        workspace_height = workspace[3] - workspace[1]
        workspace_width = workspace[2] - workspace[0]
        scaled_height = workspace_height + jank_offset
        scale_factor = scaled_height / cur_height
        scaled_width = cur_width * scale_factor

        if scaled_width > workspace_width:
            scale_factor = workspace_width / scaled_width
            scaled_height = scaled_height * scale_factor
            scaled_width = workspace_width

        scaled_size = (round(scaled_width), round(scaled_height))
        win32gui.MoveWindow(gaem, cur_gaem_rect[0], workspace[1], scaled_size[0], scaled_size[1], True)

        # Determine if orientation changed.
        prev_portrait = is_portrait()
        if first_orientation or jank_resize or prev_portrait != was_portrait:
            new_left = round((workspace_width / 2) - (scaled_width / 2))
            win32gui.MoveWindow(gaem, new_left, workspace[1], scaled_size[0], scaled_size[1], True)
            first_orientation = False
        was_portrait = prev_portrait
        new_gaem_rect = win32gui.GetWindowRect(gaem)
        cur_height = new_gaem_rect[3] - new_gaem_rect[1]
        prev_height = cur_height
    

def get_screenshot():
    global gaem
    # win32gui.SetForegroundWindow(gaem)
    x, y, x1, y1 = win32gui.GetClientRect(gaem)
    x, y = win32gui.ClientToScreen(gaem, (x, y))
    x1, y1 = win32gui.ClientToScreen(gaem, (x1 - x, y1 - y))
    return pyautogui.screenshot(region=(x, y, x1, y1)).convert("RGB")


def do_presence(debug: bool = False):
    global gaem
    global rpc
    global rpc_next
    global screen_state
    
    # Get screenshot
    try:
        img = get_screenshot()
    except OSError:
        print("Couldn't get screenshot")
        return
    if not img:
        return
    if debug:
        img.save("screenshot.png", "PNG")

    screen_state.update(img, debug)

    if screen_state.has_state():
        rpc_next = screen_state.get_state()


def main():
    global dmm
    global dmm_got
    global gaem
    global gaem_got
    global portrait_topleft
    global landscape_topleft
    global stop_threads
    global icon
    global last_screen
    global rpc
    global rpc_next
    global last_rpc_update
    global vpn_settings
    dmm_closed = False
    dmm_ignored = False

    get_dmm()
    get_game()

    if not gaem and not dmm:
        nord.rotate_VPN(vpn_settings)
        time.sleep(5)  # Connection jank, so wait a little longer
        os.system("Start dmmgameplayer://")

    if gaem:
        dmm_ignored = True
        do_presence(True)

    while True:
        time.sleep(0.1)

        if stop_threads:
            nord.close_vpn_connection(vpn_settings)
            break

        if not dmm and not dmm_ignored:
            get_dmm()
        
        if dmm_got and not dmm_ignored:
            # Check if it changed window.
            if not win32gui.IsWindow(dmm):
                get_dmm()
                if not dmm:
                    # DMM Player was open and is now closed.
                    print("Disconnect VPN because DMM was closed.")
                    dmm_closed = True
                    nord.close_vpn_connection(vpn_settings)
        
        if dmm_got and not dmm and not gaem:
            print("break here")
            break

        if not gaem:
            if gaem_got:
                # Game was found before, but no more.
                get_game()
                if not gaem:
                    break
            else:
                get_game()
            
        if gaem:
            if not dmm_ignored and dmm_got and not dmm_closed:
                # Game was launched via DMM.
                print("Automatically shutting down VPN")
                dmm_closed = True
                nord.close_vpn_connection(vpn_settings)
            try:
                if win32gui.IsWindow(gaem):
                    # Do stuff
                    scale_height()
                    if time.time() - last_screen >= 1:
                        # Take a screenshot every second
                        last_screen = time.time()
                        do_presence(False)
                    if time.time() - last_rpc_update >= 15:
                        # Update rich presence every 15 seconds
                        last_rpc_update = time.time()
                        rpc_next["large_image"] = "umaicon"
                        rpc_next["large_text"] = "It's Special Week!"
                        rpc.update(**rpc_next)
                else:
                    # Game window closed
                    print("considered closed")
                    gaem = None
            except pywintypes.error as e:
                # Game window probaby closed
                print(e)
                gaem = None
    if icon:
        icon.stop()
    return None


icon = pystray.Icon(
    'Uma Launcher',
    Image.open("favicon.ico"),
    menu=pystray.Menu(
        pystray.MenuItem(
            "Close",
            on_clicked
        ))
    )

scaling_thread = threading.Thread(target=main, daemon=True)
scaling_thread.start()

icon.run()

rpc.clear()
rpc.close()