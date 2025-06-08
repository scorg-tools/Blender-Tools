import bpy
import threading
import time
from scdatatools.sc import StarCitizen
from scdatatools.sc.localization import SCLocalization

# Global variables for UI update throttling
_last_ui_update_time = 0.0
_ui_update_interval = 1.0 # seconds

# Global variables for addon state
dcb = None
p4k = None
button_labels = []
ship_loaded = None
item_loaded = None
sc = None
localizer = None
_loading_thread = None # Global to hold the loading thread instance

def p4k_load_monitor(msg, progress, total):
    global _last_ui_update_time, _loading_thread
    current_time = time.time()

    # Convert progress to percentage
    percentage = (progress / total) * 100 if total > 0 else 0

    # Update internal state of the loading thread, not UI directly
    if _loading_thread:
        _loading_thread.current_message = msg
        _loading_thread.current_progress = percentage

    # This function itself doesn't force a redraw. The timer on the main thread will.
    # We still throttle updates to the thread's internal state to avoid excessive work.
    if current_time - _last_ui_update_time > _ui_update_interval or percentage == 0.0 or percentage >= 99.9:
        _last_ui_update_time = current_time


class LoadP4KThread(threading.Thread):
    def __init__(self, p4k_path, addon_prefs):
        threading.Thread.__init__(self)
        self.p4k_path = p4k_path
        self.addon_prefs = addon_prefs
        self.success = False
        self.error_message = ""
        self.current_message = "" # New attribute to store message from monitor
        self.current_progress = 0.0 # New attribute to store progress from monitor

    def run(self):
        global dcb, p4k, localizer, sc
        try:
            # The actual blocking call to load StarCitizen
            sc = StarCitizen(self.p4k_path, p4k_load_monitor=p4k_load_monitor)
            dcb = sc.datacore
            p4k = sc.p4k
            localizer = sc.localization
            self.success = True
        except Exception as e:
            self.error_message = str(e)
            self.success = False
        finally:
            # Final update of internal state on thread completion
            if self.success:
                self.current_message = "Data.p4k Loaded!"
                self.current_progress = 100.0
            else:
                self.current_message = f"Failed to load: {self.error_message}"
                self.current_progress = 0.0
            # The check_load_status timer will pick up these final values


def check_load_status():
    global _loading_thread, p4k

    if bpy.context: # Ensure context is available for UI updates
        prefs = bpy.context.preferences.addons[__package__].preferences

        if _loading_thread and _loading_thread.is_alive():
            # Thread is still running, update UI from thread's internal state
            prefs.p4k_load_message = _loading_thread.current_message
            prefs.p4k_load_progress = _loading_thread.current_progress
            # Force a redraw of the UI
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            return _ui_update_interval # Keep the timer active
        else:
            # Thread has finished or was never started
            if _loading_thread: # If the thread existed and finished
                # Ensure final state is reflected in UI preferences
                prefs.p4k_load_message = _loading_thread.current_message
                prefs.p4k_load_progress = _loading_thread.current_progress
                if not _loading_thread.success:
                    p4k = None # If load failed, ensure p4k is None
                # Force a final redraw
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
            
            # Unregister the timer as the loading is complete
            if bpy.app.timers.is_registered(check_load_status):
                bpy.app.timers.unregister(check_load_status)
            _loading_thread = None # Clear the reference to the finished thread
            return None # Return None to unregister the timer
    return None # If context is not available, stop the timer

def clear_vars():
    global dcb, p4k, button_labels, ship_loaded, item_loaded, sc, localizer, _loading_thread
    dcb = None
    p4k = None
    button_labels = []
    ship_loaded = None
    item_loaded = None
    sc = None
    localizer = None
    _loading_thread = None # Ensure thread reference is cleared
