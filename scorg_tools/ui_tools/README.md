<pre>
           ░██           ░██                          ░██            
                         ░██                          ░██            
░██    ░██ ░██        ░████████  ░███████   ░███████  ░██  ░███████  
░██    ░██ ░██           ░██    ░██    ░██ ░██    ░██ ░██ ░██        
░██    ░██ ░██           ░██    ░██    ░██ ░██    ░██ ░██  ░███████  
░██   ░███ ░██           ░██    ░██    ░██ ░██    ░██ ░██        ░██ 
 ░█████░██ ░██ ░██████    ░████  ░███████   ░███████  ░██  ░███████  
</pre>

# ui_tools
ui_tools is a lightweight Python library for Blender add-ons, providing a custom popup system to create interactive user interfaces such as progress bars, text inputs, buttons, and informational messages. It allows developers to build flexible, themed UI components that integrate seamlessly with Blender's design, enabling add-ons to offer better user experiences for tasks like data import, processing feedback, or configuration dialogs without being limited to standard Blender panels.

The library works by utilizing Blender's BLF module for accurate text rendering and measurement,combined with space-specific draw handlers for real-time display in areas like the 3D Viewport. It employs modal operators for handling user interactions and events, ensuring responsive and interruptible popups. For multi-threading support, ui_tools enables developers to write background operations that run concurrently with the UI, providing real-time feedback through progress bars for long-running tasks; updates from background threads are throttled to maintain performance, while popup initialization and display occur on the main thread to adhere to Blender's UI threading rules, allowing add-ons to perform intensive computations without freezing the interface.

## Features

- 🎨 **Custom Popups** - Create beautiful, draggable popups that don't vanish randomly
- 📝 **Text Input** - Multi-line text input with selection support
- 🔘 **Auto-Layout** - Automatic text wrapping and height adjustment
- ⌨️ **Keyboard Shortcuts** - Enter for OK, Escape for Cancel
- 🎯 **Easy Integration** - Drop into any existing Blender addon with minimal setup

## Installation

### Copy into your addon

1. Copy the `ui_tools` folder into your addon directory:
   ```
   my_addon/
   ├── __init__.py
   ├── ui_tools/         ← Copy this folder here
   │   ├── __init__.py
   │   ├── operators.py
   │   └── ui_system.py
   └── ... (your other files)
   ```

2. In your addon's `__init__.py`, add:
   ```python
   def register():
       from . import ui_tools  # Import INSIDE the function
       ui_tools.register()
       # ... your addon registration code ...
   
   def unregister():
       # ... your addon unregistration code ...
       from . import ui_tools  # Import INSIDE the function
       ui_tools.unregister()
   ```
   
   **Important**: Import `ui_tools` **inside** your `register()` and `unregister()` functions,
   not at the module level, to avoid circular imports.

3. In your operators/modules, import as needed:
   ```python
   # Import the ui_tools module inside functions
   def my_function():
       from . import ui_tools
       
       # Now use it with the ui_tools prefix
       popup = ui_tools.Popup("My Popup")
       popup.add_widget(ui_tools.Label("Hello"))
       ui_tools.show_popup(popup)
   ```

That's it! You can now use `ui_tools` in your addon.

## Usage

### Simple Example
A basic popup with a message. An OK button is added automatically.

```python
def simple_popup_example(context):
    from . import ui_tools
    
    ui_tools.Popup("Hello", "This is a simple message!").show()
```

### Complex Example
Advanced example with text input, multiple buttons, and shortcuts.

```python
def complex_popup_example(context):
    from . import ui_tools
    
    popup = ui_tools.Popup("Enter Your Name")
    
    # Label with long text (will wrap automatically)
    popup.add.label(
        "Please enter your information below. "
        "This text will automatically wrap to fit the popup width."
    )
    
    # Text input - keep as variable to access the text later
    text_input = popup.add.text_input("Type here...")
    
    # Row for buttons
    row = popup.add.row()
    
    def on_ok():
        user_text = text_input.text  # Access the input text
        print(f"User entered: {user_text}")
        popup.finished = True
        
    def on_cancel():
        popup.cancelled = True
        
    row.add.button("OK", callback=on_ok)
    row.add.button("Cancel", callback=on_cancel)
    
    popup.on_enter = on_ok
    popup.on_cancel = on_cancel
    
    popup.show()
```

### Calling from an Operator

```python
import bpy

class MY_OT_show_popup(bpy.types.Operator):
    bl_idname = "myaddon.show_popup"
    bl_label = "Show Popup"
    
    def execute(self, context):
        from . import ui_tools
        
        ui_tools.Popup("My Popup", "Hello from my addon!").show()
        return {'FINISHED'}
```

## API Reference

### Progress Bar (Basic)
Display a progress bar. Useful for showing values or percentages.

```python
def progress_bar_example(context):
    from . import ui_tools
    popup = ui_tools.Popup("Status")
    # current=50, max_value=100, text="Loading..."
    progress = ui_tools.ProgressBar(50, 100, "Loading...", show_percentage=True)
    popup.add_widget(progress)
    
    # You can update it later:
    # progress.update(75, 100, "Almost done...")    
    popup.show()
```

You can also use a simple oneliner to show a progress bar:
```python
def progress_bar_example(context):
    from . import ui_tools
    ui_tools.progress_bar_popup("my_task", 50, 100, "Loading...")
```

### Threading & Progress (Advanced)
Run heavy tasks in the background while updating a progress bar.

```python
def threaded_progress_example(context):
    from . import ui_tools
    import time
    
    # 1. Initialize progress bar from main thread (IMPORTANT!)
    ui_tools.progress_bar_popup("my_task", 0, 100, "Initializing...")
    
    # 2. Start Thread Manager
    tm = ui_tools.ThreadManager()
    tm.start()
    
    # 3. Define Background Task
    def background_task():
        try:
            for i in range(1, 101):
                # Update progress from background thread
                ui_tools.progress_bar_popup("my_task", i, 100, f"Processing item {i}...")
                
                # Simulate work - add your code here
                time.sleep(0.05)
            
            # When finished (reaches 100%), close button appears automatically
            ui_tools.progress_bar_popup("my_task", 100, 100, "Done!")
            
        except Exception as e:
            print(f"Error: {e}")
    
    # 4. Submit Task
    tm.submit(background_task)
```

### Multi-threaded Batch Processing
Process multiple items in parallel using the thread pool.

```python
def batch_processing_example(context):
    from . import ui_tools
    import time
    import random
    
    # 1. Create Popup
    popup = ui_tools.Popup("Batch Processing", prevent_close=True)
    
    # 2. Add Progress Bar
    progress = ui_tools.ProgressBar(text="Processing items...")
    popup.add_widget(progress)
    
    # 3. Add Status Label
    status_label = ui_tools.Label("Ready to start...")
    popup.add_widget(status_label)
    
    popup.show()
    
    # 4. Start Thread Manager
    tm = ui_tools.ThreadManager()  # Defaults to CPU count or 4 workers
    
    # 5. Define Worker Function
    def process_item(item_id):
        # Simulate work with random duration - Your code goes here
        time.sleep(random.uniform(0.5, 3.0))
        print(f"Finished item: {item_id}")
        return f"item {item_id}"
        
    # 6. Define Items to Process
    items = list(range(30))
    
    # 7. Process Batch
    # Correct argument order: func, items, progress_callback
    futures = tm.process_batch(
        process_item, 
        items, 
        progress_callback=lambda current, total: progress.update(
            current, total, f"Processed {current}/{total}"
        )
    )
    
    # 8. Update Label on Completion of each item
    def on_item_done(future):
        try:
            result = future.result()
            status_label.update(f"Last finished: {result}")
        except Exception as e:
            print(f"Task failed: {e}")
            
    for f in futures:
        f.add_done_callback(on_item_done)
    
    # 9. Handle Completion (Optional)
    def on_all_done(future):
        # This runs when the *last* submitted task finishes
        if all(f.done() for f in futures):
            popup.prevent_close = False
            progress.update(100, 100, "All Done!")
            status_label.update("Batch processing complete.")
            
    # Attach completion check to all futures
    for f in futures:
        f.add_done_callback(on_all_done)
```

### Cancellable Threaded Task
Run a long task with a cancel button and prevent_close.

```python
def cancellable_threaded_example(context):
    from . import ui_tools
    import time
    
    # 1. Create Popup with prevent_close=True
    # blocking=True prevents interacting with the viewport while running
    popup = ui_tools.Popup("Processing...", prevent_close=True, blocking=True)
    
    # 2. Add Progress Bar
    progress = ui_tools.ProgressBar(text="Initializing...")
    popup.add_widget(progress)
    
    # 3. Add a Cancel Button
    def on_cancel():
        popup.cancelled = True  # Signal cancellation
        
    # Keep reference to button to change it later
    cancel_btn = ui_tools.Button("Cancel", callback=on_cancel)
    popup.add_widget(cancel_btn)
    
    popup.show()
    
    # 4. Start Thread Manager
    tm = ui_tools.ThreadManager()
    tm.start()
    
    # 5. Define Background Task
    def background_task():
        try:
            for i in range(101):
                # Check for cancellation
                if popup.cancelled:
                    print("Task cancelled by user")
                    return
                    
                # Update progress (thread-safe)
                progress.update(i, 100, f"Processing item {i}...")
                
                # Simulate work
                time.sleep(0.05)
                
            # Finish
            progress.update(100, 100, "Done!")
            time.sleep(0.5)
            
            # Allow closing
            popup.prevent_close = False
            
            # Change Cancel button to Close
            cancel_btn.text = "Close"
            cancel_btn.callback = lambda: setattr(popup, 'finished', True)
            
            # Trigger redraw to show button change
            progress.update(100, 100, "Done!") 
            
        except Exception as e:
            print(f"Error: {e}")
            popup.prevent_close = False

    # 6. Submit Task
    tm.submit(background_task)
```

### Popup
```python
Popup(title, label=None, width=None, height=None, prevent_close=False, blocking=False)
```
- `title`: Popup window title
- `label`: Optional message text
- `prevent_close`: If True, prevents closing via Enter/Esc (useful for progress bars)
- `blocking`: If True, prevents interacting with the window behind the popup (navigation, clicks)
- `width`, `height`: Optional fixed size (defaults to auto-sizing)
- Properties:
  - `on_enter`: Callback for Enter key
  - `on_cancel`: Callback for Escape key
  - `finished`: Set to `True` to close (returns FINISHED)
  - `cancelled`: Set to `True` to cancel (returns CANCELLED)

### Label
```python
Label(text)
```
- Displays text with automatic wrapping
- Use `label.update(new_text)` to dynamically update the text

### Button
```python
Button(text, callback=None)
```
- `callback`: Function to call when clicked

### TextInput
```python
TextInput(text="")
```
- Multi-line text input with selection support
- Press Enter to insert newlines

### Row
```python
Row()
```
- Container for horizontal layout (e.g., buttons)

### ThreadManager
```python
ThreadManager(max_workers=None)
```
- `max_workers`: Number of worker threads (defaults to CPU count or 4)
- Methods:
  - `start()`: Start the thread manager (optional, auto-starts on first use)
  - `submit(func, *args)`: Submit a single task
  - `process_batch(func, items, progress_callback=None)`: Process multiple items in parallel
    - `func`: Worker function that takes one item as argument
    - `items`: List of items to process
    - `progress_callback`: Optional callback with signature `callback(current, total)`
    - Returns: List of futures
  - `stop()`: Stop the thread manager and wait for all tasks

## Tips

- **Dragging**: Click and drag the popup background to move it
- **Keyboard Shortcuts**: Set `popup.on_enter` and `popup.on_cancel` for Enter/Esc support
- **Auto-sizing**: Leave `width` and `height` as `None` for automatic sizing
- **Text Wrapping**: Long text in Labels automatically wraps
- **Auto OK Button**: If you don't add any buttons, an "OK" button is added automatically
- **Thread Safety**: Use `progress.update()` from background threads, it's designed to be thread-safe

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.