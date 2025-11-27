"""
UI Tools - Custom Popup System for Blender Addons

A lightweight library for creating custom popups with text input, buttons, and auto-layout.
"""

import time

def register(operator_prefix="uitools"):
    """
    Register the UI Tools operators.
    
    Args:
        operator_prefix: The prefix to use for operator IDs (default: "uitools")
    """
    from . import operators
    operators.OPERATOR_PREFIX = operator_prefix
    operators.register()

def unregister():
    """Unregister the UI Tools operators."""
    from . import operators
    operators.unregister()

def show_popup(popup_instance):
    """Show a popup instance."""
    from .operators import show_popup as _show_popup
    _show_popup(popup_instance)

# Global state for the shared progress popup
_shared_progress_state = {
    'popup': None,
    'bars': {},  # Map of progress_id -> ProgressBar widget
    'finished_ids': set(),
    'last_update': 0
}

def progress_bar_popup(progress_id, current, max_value, text="", title="Progress", show_percentage=True, auto_close=True):
    """
    Simplified API for showing progress bars in a single shared popup.
    
    Multiple progress bars (with different IDs) will be stacked in the same popup.
    The popup automatically closes when ALL active progress bars are finished.
    
    Args:
        progress_id: Unique identifier for this progress bar
        current: Current progress value
        max_value: Maximum value
        text: Optional text to display
        title: Popup title (only used when creating the popup)
        show_percentage: Whether to show percentage
        auto_close: Whether to auto-close the popup when ALL bars are done (default: True)
    """
    global _shared_progress_state
    
    from .ui_system import Popup, ProgressBar
    import threading
    
    # 1. Create shared popup if it doesn't exist or was closed
    popup = _shared_progress_state['popup']
    is_new_popup = False
    
    # Only create popup if on main thread
    if threading.current_thread() is threading.main_thread():
        if popup is None or popup.finished or popup.cancelled:
            popup = Popup(title, prevent_close=True, blocking=False)
            is_new_popup = True
            _shared_progress_state['popup'] = popup
            _shared_progress_state['bars'] = {}
            _shared_progress_state['finished_ids'] = set()
    
    # If no popup exists and we're on a background thread, return silently
    # User must call this function from main thread first to initialize
    if popup is None:
        return
    
    # 2. Create or update progress bar for this ID
    bars = _shared_progress_state['bars']
    
    if progress_id not in bars:
        # Remove any existing close button since we're adding a new incomplete bar (only on main thread)
        if threading.current_thread() is threading.main_thread():
            from .ui_system import Button
            popup.children = [w for w in popup.children if not (isinstance(w, Button) and w.text == "Close")]
            popup.prevent_close = True
        
        # Remove from finished_ids if present (in case of restart)
        _shared_progress_state['finished_ids'].discard(progress_id)
        
        # Create new progress bar
        progress_bar = ProgressBar(current, max_value, text, show_percentage=show_percentage)
        popup.add_widget(progress_bar)
        
        # Force layout update to accommodate new widget
        if hasattr(popup, 'layout_children'):
            popup.layout_children()
            
        bars[progress_id] = progress_bar
        
        # Show popup now that it has content (if new and on main thread)
        if is_new_popup:
            popup.show()
        
        # Force redraw on creation
        if hasattr(progress_bar, 'update'):
            progress_bar.update(current, max_value, text, force_redraw=True)
    else:
        # Update existing, throttle redraws to 4 times per second
        current_time = time.time()
        force_redraw = current_time - _shared_progress_state['last_update'] >= 0.25
        if force_redraw:
            _shared_progress_state['last_update'] = current_time
        bars[progress_id].update(current, max_value, text, force_redraw=force_redraw)
    
    # 3. Handle completion
    if current >= max_value:
        _shared_progress_state['finished_ids'].add(progress_id)
        
        # Check if ALL bars are finished
        all_finished = len(_shared_progress_state['finished_ids']) == len(bars)
        
        if all_finished and auto_close and threading.current_thread() is threading.main_thread():
            # Enable closing and add Close button
            popup.prevent_close = False
            
            # Check if we already added a close button (check Button widgets only)
            from .ui_system import Button
            has_close_btn = any(isinstance(w, Button) and w.text == "Close" for w in popup.children)
            if not has_close_btn:
                popup.add_close_button("Close")

def close_progress_bar_popup(progress_id=None):
    """
    Manually close the shared progress popup.
    
    Args:
        progress_id: If provided, only marks this specific ID as finished.
                     If None, closes the entire popup immediately.
    """
    global _shared_progress_state
    
    popup = _shared_progress_state['popup']
    if popup and not popup.finished:
        if progress_id is None:
            # Force close everything
            popup.finished = True
            _shared_progress_state['popup'] = None
            _shared_progress_state['bars'] = {}
        elif progress_id in _shared_progress_state['bars']:
            # Mark specific bar as finished
            _shared_progress_state['finished_ids'].add(progress_id)
            
            # Check if all finished
            if len(_shared_progress_state['finished_ids']) == len(_shared_progress_state['bars']):
                popup.prevent_close = False
                from .ui_system import Button
                has_close_btn = any(isinstance(w, Button) and w.text == "Close" for w in popup.children)
                if not has_close_btn:
                    popup.add_close_button("Close")

# Lazy imports using __getattr__ (Python 3.7+)
def __getattr__(name):
    """Lazy load ui_system classes on demand."""
    if name in ('Popup', 'Label', 'Button', 'TextInput', 'Row', 'ProgressBar'):
        from . import ui_system
        return getattr(ui_system, name)
    elif name == 'ThreadManager':
        from . import threading
        return getattr(threading, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = ['register', 'unregister', 'show_popup', 'progress_bar_popup', 'close_progress_bar_popup', 'Popup', 'Label', 'Button', 'TextInput', 'Row', 'ProgressBar', 'ThreadManager']
