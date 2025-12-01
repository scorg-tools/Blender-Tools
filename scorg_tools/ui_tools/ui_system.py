import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import blf
import textwrap
import re

def get_ui_scale():
    # Default to 1.0 if context is not available (e.g. during registration)
    try:
        return bpy.context.preferences.view.ui_scale
    except:
        return 1.0

def get_theme_font_size():
    try:
        # Try to get the font size from user preferences
        # Note: This path might vary slightly between Blender versions, but this is standard for 3.x+
        return bpy.context.preferences.ui_styles[0].widget.points
    except:
        return 11 # Default fallback

def get_theme_color(path_func):
    try:
        # path_func should be a lambda that takes 'theme' and returns the color
        theme = bpy.context.preferences.themes[0]
        color = path_func(theme)
        # Ensure RGBA
        if len(color) == 3:
            return (*color, 1.0)
        return color
    except:
        return (0.2, 0.2, 0.2, 1.0) # Fallback

class Widget:
    def __init__(self, x=0, y=0, width=100, height=20, parent=None):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.parent = parent
        self.hover = False
        self.focused = False
        self.children = [] # For container widgets like Row

    def update_layout(self):
        # Allow widgets to update their own layout (e.g. Row)
        pass

    @property
    def scaled_width(self):
        return int(self.width * get_ui_scale())

    @property
    def scaled_height(self):
        return int(self.height * get_ui_scale())

    @property
    def global_x(self):
        if self.parent is None:
            # Root widget (popup) - x is already in region coordinates
            return self.x
        else:
            # Child widget - x is relative to parent, needs scaling
            scale = get_ui_scale()
            return self.parent.global_x + int(self.x * scale)

    @property
    def global_y(self):
        if self.parent is None:
            # Root widget (popup) - y is already in region coordinates
            return self.y
        else:
            # Child widget - y is relative to parent, needs scaling
            scale = get_ui_scale()
            parent_y = self.parent.global_y
            # For popup children, position relative to popup top
            if self.parent and isinstance(self.parent, Popup):
                if not self.parent.is_scrollable:
                    parent_y += self.parent.title_height - int(self.parent.margin * scale)
            return int(self.y * scale) + parent_y

    def is_inside(self, x, y):
        gx = self.global_x
        gy = self.global_y
        return gx <= x <= gx + self.scaled_width and gy <= y <= gy + self.scaled_height

    def draw(self):
        pass

    def handle_event(self, event, mouse_x=None, mouse_y=None):
        return False

class Label(Widget):
    def __init__(self, text, font_size=None, color=(1, 1, 1, 1), parent=None, x=0, y=0, width=100, height=20):
        super().__init__(x, y, width, height, parent)
        self.text = text
        # Apply UI scale
        ui_scale = bpy.context.preferences.view.ui_scale
        
        if font_size is None:
            font_size = get_theme_font_size()
            
        # Increase multiplier
        self.font_size = int(font_size * 1.8 * ui_scale)
        self.color = color
        self.font_id = 0
        self.lines = []
        self.line_height = 0
        self.last_available_width = width # Default fallback

    def update(self, text):
        """
        Update label text. Thread-safe.
        """
        self.text = text
        # Re-calculate layout if we have width info
        if self.last_available_width:
            self.update_layout_custom(self.last_available_width)
        else:
            self.lines = [] # Fallback to unwrapped
            
        # Trigger redraw safely
        def trigger_redraw():
            try:
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        area.tag_redraw()
            except:
                pass
        
        try:
            trigger_redraw()
        except:
            bpy.app.timers.register(trigger_redraw)

    def update_layout_custom(self, available_width):
        self.last_available_width = available_width
        # Wrap text to fit available width
        # We need to use BLF to measure text width
        blf.size(self.font_id, self.font_size, 72)
        
        ui_scale = get_ui_scale()
        pixel_width = available_width * ui_scale
        
        self.lines = []
        
        # Split by existing newlines first
        paragraphs = self.text.split('\n')
        
        for p in paragraphs:
            if not p:
                self.lines.append("")
                continue
                
            words = p.split(' ')
            current_line = []
            current_width = 0
            space_width = blf.dimensions(self.font_id, " ")[0]
            
            for word in words:
                word_width = blf.dimensions(self.font_id, word)[0]
                
                if word_width > pixel_width:
                    # Split long word into chunks that fit
                    chunks = []
                    start = 0
                    while start < len(word):
                        end = start + 1
                        while end <= len(word) and blf.dimensions(self.font_id, word[start:end])[0] <= pixel_width:
                            end += 1
                        end -= 1
                        if end == start:
                            end = start + 1  # At least one char
                        chunks.append(word[start:end])
                        start = end
                    
                    # Treat chunks as words
                    for chunk in chunks:
                        chunk_width = blf.dimensions(self.font_id, chunk)[0]
                        if current_line and (current_width + space_width + chunk_width) > pixel_width:
                            self.lines.append(" ".join(current_line))
                            current_line = [chunk]
                            current_width = chunk_width
                        else:
                            if current_line:
                                current_width += space_width
                            current_line.append(chunk)
                            current_width += chunk_width
                else:
                    # Normal word
                    if current_line and (current_width + space_width + word_width) > pixel_width:
                        self.lines.append(" ".join(current_line))
                        current_line = [word]
                        current_width = word_width
                    else:
                        if current_line:
                            current_width += space_width
                        current_line.append(word)
                        current_width += word_width
            
            if current_line:
                self.lines.append(" ".join(current_line))
        
        # Calculate height
        self.line_height = blf.dimensions(self.font_id, "Hg")[1] * 1.5
        # Height in pixels
        total_pixel_height = len(self.lines) * self.line_height
        
        # Convert back to unscaled height for the widget property
        self.height = int(total_pixel_height / ui_scale) + 10 # Add some padding

    def draw(self):
        blf.size(self.font_id, self.font_size, 72)
        blf.color(self.font_id, *self.color)
        
        # Use pre-calculated lines if available, otherwise fallback
        lines_to_draw = self.lines if self.lines else self.text.split('\n')
        
        # Recalculate line height just in case (or use stored)
        line_height = self.line_height if self.line_height > 0 else blf.dimensions(self.font_id, "Hg")[1] * 1.5
        
        current_y = self.global_y + self.scaled_height - line_height # Start from top
        
        for line in lines_to_draw:
            blf.position(self.font_id, self.global_x, current_y, 0)
            blf.draw(self.font_id, line)
            current_y -= line_height

class Button(Widget):
    def __init__(self, text, callback=None, parent=None, x=0, y=0, width=100, height=30):
        super().__init__(x, y, width, height, parent)
        self.text = text
        self.callback = callback
        self.bg_color = get_theme_color(lambda t: t.user_interface.wcol_regular.inner)
        self.hover_color = get_theme_color(lambda t: t.user_interface.wcol_regular.inner_sel)
        self.active_color = get_theme_color(lambda t: t.user_interface.wcol_regular.item)
        self.text_color = get_theme_color(lambda t: t.user_interface.wcol_regular.text)
        self.active = False
        self.padding = 10
        self.font_size_mult = 1.8

    def update_layout_custom(self, available_width):
        # Calculate height based on text
        ui_scale = get_ui_scale()
        base_font_size = get_theme_font_size()
        font_size = int(base_font_size * self.font_size_mult * ui_scale)
        
        blf.size(0, font_size, 72)
        text_dims = blf.dimensions(0, self.text)
        text_height = text_dims[1]
        
        # Add padding (top + bottom)
        # We want enough padding for visual comfort
        vertical_padding = 12 * ui_scale 
        total_height = text_height + (vertical_padding * 2)
        
        # Update height (unscaled)
        self.height = int(total_height / ui_scale)

    def draw(self):
        # Determine color based on state
        if self.active and self.hover:
            color = self.active_color
        elif self.hover:
            color = self.hover_color
        else:
            color = self.bg_color
            
        draw_rect(self.global_x, self.global_y, self.scaled_width, self.scaled_height, color)
        
        # Draw text centered
        ui_scale = get_ui_scale()
        base_font_size = get_theme_font_size()
        font_size = int(base_font_size * self.font_size_mult * ui_scale) 
        blf.size(0, font_size, 72)
        text_width, text_height = blf.dimensions(0, self.text)
        
        text_x = self.global_x + (self.scaled_width - text_width) / 2
        
        # Vertical Centering
        # blf.position sets the BASELINE.
        # To center vertically, we need: CenterY - (TextHeight / 2) + Adjustment
        # TextHeight from dimensions() is usually Ascent + Descent (or close to it).
        # A good approximation for baseline from center is: CenterY - (CapHeight / 2)
        # But we don't have CapHeight easily.
        # Usually, (Height / 2) - Descent is good.
        # Let's try centering the bounding box:
        # Bounding Box Bottom = CenterY - (Height / 2)
        # But we draw at Baseline. Baseline is Bounding Box Bottom + Descent.
        # A simple heuristic that often works better:
        # text_y = center_y - (text_height * 0.3) 
        
        center_y = self.global_y + (self.scaled_height / 2)
        text_y = center_y - (text_height / 3) # Shift down slightly less than half height
        
        blf.color(0, *self.text_color)
        blf.position(0, text_x, text_y, 0)
        blf.draw(0, self.text)

    def handle_event(self, event, mouse_x=None, mouse_y=None):
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if self.hover:
                    self.active = True
                    return True
            elif event.value == 'RELEASE':
                was_active = self.active
                self.active = False
                if was_active and self.hover:
                    if self.callback:
                        self.callback()
                    else:
                        # Auto-close logic for standard buttons
                        if self.text.lower() in ["ok", "okay", "close"]:
                            # Traverse up to find the Popup
                            p = self.parent
                            while p:
                                if type(p).__name__ == 'Popup':
                                    p.finished = True
                                    break
                                p = p.parent
                    return True
                return was_active # Consume event if we were active
        return False

class TextInput(Widget):
    def __init__(self, text="", parent=None, x=0, y=0, width=100, height=30):
        super().__init__(x, y, width, height, parent)
        self.text = text
        # Use theme colors
        self.bg_color = get_theme_color(lambda t: t.user_interface.wcol_text.inner)
        self.focus_color = get_theme_color(lambda t: t.user_interface.wcol_text.inner)
        self.text_color = get_theme_color(lambda t: t.user_interface.wcol_text.text)
        self.selection_color = get_theme_color(lambda t: t.user_interface.wcol_text.item)
        
        self.cursor_pos = len(text)
        self.selection_start = None # Start index of selection
        self.selection_end = None   # End index of selection
        self.is_selecting = False
        
        ui_scale = bpy.context.preferences.view.ui_scale
        base_font_size = get_theme_font_size()
        self.font_size = int(base_font_size * 1.8 * ui_scale)
        self.line_height = int(self.font_size * 1.5)
        self.lines = [] # List of (text, start_index, end_index)
        self.padding = 10 # Increased padding

    def update_layout_custom(self, available_width):
        # Wrap text and calculate height
        blf.size(0, self.font_size, 72)
        ui_scale = get_ui_scale()
        
        # Effective width for text
        text_area_width = (available_width * ui_scale) - (2 * self.padding * ui_scale)
        
        self.lines = []
        
        # We need to handle existing newlines in self.text
        paragraphs = self.text.split('\n')
        
        current_index = 0
        
        for i, p in enumerate(paragraphs):
            # If not the first paragraph, we passed a newline
            if i > 0:
                current_index += 1 # for the \n character
            
            # Wrap this paragraph
            # Split by spaces but keep delimiters to preserve exact indices
            words = re.split(r'(\s+)', p)
            
            current_line_tokens = []
            current_line_width = 0
            line_start_index = current_index
            
            for token in words:
                if not token: continue
                
                token_width = blf.dimensions(0, token)[0]
                
                # If token itself is too wide, break it into chunks
                if token_width > text_area_width:
                    # Break into character chunks that fit
                    chunks = []
                    start = 0
                    while start < len(token):
                        end = start + 1
                        while end <= len(token) and blf.dimensions(0, token[start:end])[0] <= text_area_width:
                            end += 1
                        end -= 1
                        if end == start:
                            end = start + 1  # At least one char
                        chunks.append(token[start:end])
                        start = end
                    
                    # Process each chunk
                    for chunk in chunks:
                        chunk_width = blf.dimensions(0, chunk)[0]
                        if current_line_tokens and (current_line_width + chunk_width) > text_area_width:
                            # Finish current line
                            line_text = "".join(current_line_tokens)
                            self.lines.append({
                                'text': line_text,
                                'start': line_start_index,
                                'end': line_start_index + len(line_text)
                            })
                            
                            # Start new line
                            current_line_tokens = [chunk]
                            current_line_width = chunk_width
                            line_start_index += len(line_text)
                        else:
                            current_line_tokens.append(chunk)
                            current_line_width += chunk_width
                elif current_line_tokens and (current_line_width + token_width) > text_area_width:
                    # Finish current line
                    line_text = "".join(current_line_tokens)
                    self.lines.append({
                        'text': line_text,
                        'start': line_start_index,
                        'end': line_start_index + len(line_text)
                    })
                    
                    # Start new line
                    current_line_tokens = [token]
                    current_line_width = token_width
                    line_start_index += len(line_text)
                else:
                    current_line_tokens.append(token)
                    current_line_width += token_width
            
            # Finish last line of paragraph
            if current_line_tokens:
                line_text = "".join(current_line_tokens)
                self.lines.append({
                    'text': line_text,
                    'start': line_start_index,
                    'end': line_start_index + len(line_text)
                })
            elif not p:
                 # Empty paragraph (e.g. double newline)
                 self.lines.append({'text': "", 'start': current_index, 'end': current_index})

            current_index += len(p)

        # Calculate height
        num_lines = len(self.lines) if self.lines else 1
        total_pixel_height = (num_lines * self.line_height) + (2 * self.padding * ui_scale)
        self.height = int(total_pixel_height / ui_scale)

    def draw(self):
        # Draw background
        draw_rect(self.global_x, self.global_y, self.scaled_width, self.scaled_height, self.bg_color)
        
        # Draw border if focused
        if self.focused:
            draw_rect_border(self.global_x, self.global_y, self.scaled_width, self.scaled_height, (0.3, 0.5, 0.8, 1.0), 1)

        ui_scale = get_ui_scale()
        blf.size(0, self.font_size, 72)
        
        # Enable BLF clipping to prevent text overflow  
        # BLF clipping works in the current coordinate space (unlike GPU scissor)
        blf.enable(0, blf.CLIPPING)
        clip_xmin = self.global_x
        clip_ymin = self.global_y
        clip_xmax = self.global_x + self.scaled_width
        clip_ymax = self.global_y + self.scaled_height
        blf.clipping(0, clip_xmin, clip_ymin, clip_xmax, clip_ymax)
        
        # Adjust vertical offset to lift text up
        # Using a smaller padding subtraction or explicitly calculating baseline
        current_y = self.global_y + self.scaled_height - self.line_height - (2 * ui_scale) 
        
        # Use self.lines if available (calculated in update_layout_custom), otherwise fallback
        lines_to_draw = self.lines if self.lines else [{'text': self.text, 'start': 0, 'end': len(self.text)}]
        
        # Handle Selection Range
        sel_min = 0
        sel_max = 0
        has_selection = False
        if self.selection_start is not None and self.selection_end is not None and self.selection_start != self.selection_end:
            sel_min = min(self.selection_start, self.selection_end)
            sel_max = max(self.selection_start, self.selection_end)
            has_selection = True

        
        for line in lines_to_draw:
            text_x = self.global_x + (self.padding * ui_scale)
            
            # Draw Selection Highlight
            if has_selection:
                # Check intersection
                line_start = line['start']
                line_end = line['end']
                
                if sel_max > line_start and sel_min < line_end:
                    # Calculate intersection range relative to line
                    start_char_idx = max(0, sel_min - line_start)
                    end_char_idx = min(len(line['text']), sel_max - line_start)
                    
                    # Calculate geometry
                    text_before = line['text'][:start_char_idx]
                    text_selected = line['text'][start_char_idx:end_char_idx]
                    
                    x_offset = blf.dimensions(0, text_before)[0]
                    sel_width = blf.dimensions(0, text_selected)[0]
                    
                    # Get actual text height for proper highlight sizing
                    text_height = blf.dimensions(0, "Hg")[1]  # Use tall chars with descenders
                    
                    # Draw selection highlight - align with text baseline
                    # The selection should start slightly below current_y to cover the full text height
                    selection_y = current_y - (4 * ui_scale)  # Adjust downward to cover descenders
                    draw_rect(text_x + x_offset, selection_y, sel_width, text_height + (4 * ui_scale), self.selection_color)

            # Draw text
            blf.color(0, *self.text_color)
            blf.position(0, text_x, current_y, 0)
            blf.draw(0, line['text'])
            
            # Draw cursor if focused and in this line
            if self.focused and line['start'] <= self.cursor_pos <= line['end']:
                # Calculate cursor x offset
                cursor_char_index = self.cursor_pos - line['start']
                text_before_cursor = line['text'][:cursor_char_index]
                cursor_x_offset = blf.dimensions(0, text_before_cursor)[0]
                
                cursor_x = text_x + cursor_x_offset
                # Draw cursor slightly taller than line height for visibility
                draw_rect(cursor_x, current_y - (2 * ui_scale), 2 * ui_scale, self.line_height, self.text_color)
            
            current_y -= self.line_height
        
        # Disable BLF clipping
        blf.disable(0, blf.CLIPPING)


    def handle_event(self, event, mouse_x=None, mouse_y=None):
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if self.hover:
                    self.focused = True
                    self.is_selecting = True
                    
                    # Calculate cursor position from click
                    click_x = mouse_x if mouse_x is not None else event.mouse_region_x
                    click_y = mouse_y if mouse_y is not None else event.mouse_region_y
                    pos = self._get_cursor_pos_from_mouse(click_x, click_y)
                    self.cursor_pos = pos
                    self.selection_start = pos
                    self.selection_end = pos
                    return True
                else:
                    self.focused = False
                    self.is_selecting = False
                    self.selection_start = None
                    self.selection_end = None
            
            elif event.value == 'RELEASE':
                if self.is_selecting:
                    self.is_selecting = False
                    return True # Consume release ONLY if we were selecting
                return False
        
        if event.type == 'MOUSEMOVE' and self.is_selecting:
            click_x = mouse_x if mouse_x is not None else event.mouse_region_x
            click_y = mouse_y if mouse_y is not None else event.mouse_region_y
            pos = self._get_cursor_pos_from_mouse(click_x, click_y)
            self.cursor_pos = pos
            self.selection_end = pos
            return True

        if not self.focused:
            return False

        if event.value == 'PRESS':
            text_changed = False
            
            # Handle deletion of selection
            if self.selection_start is not None and self.selection_end is not None and self.selection_start != self.selection_end:
                 if event.type in ('BACK_SPACE', 'DEL') or event.unicode:
                    # Delete selection
                    sel_min = min(self.selection_start, self.selection_end)
                    sel_max = max(self.selection_start, self.selection_end)
                    self.text = self.text[:sel_min] + self.text[sel_max:]
                    self.cursor_pos = sel_min
                    self.selection_start = None
                    self.selection_end = None
                    text_changed = True
                    
                    if event.type in ('BACK_SPACE', 'DEL'):
                        # Already handled deletion
                        pass
                    elif event.unicode:
                        # Insert new char
                        self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                        self.cursor_pos += 1
            
            elif event.type == 'ESC':
                self.focused = False
                return False
            
            elif event.type == 'RET':
                self.text = self.text[:self.cursor_pos] + '\n' + self.text[self.cursor_pos:]
                self.cursor_pos += 1
                text_changed = True
            
            elif event.type == 'BACK_SPACE':
                if self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
                    text_changed = True
                
            elif event.type == 'DEL':
                if self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
                    text_changed = True

            elif event.type == 'LEFT_ARROW':
                if self.cursor_pos > 0:
                    self.cursor_pos -= 1
                    # Clear selection on move
                    self.selection_start = None
                    self.selection_end = None
                return True
            
            elif event.type == 'RIGHT_ARROW':
                if self.cursor_pos < len(self.text):
                    self.cursor_pos += 1
                    # Clear selection on move
                    self.selection_start = None
                    self.selection_end = None
                return True
                
            elif event.unicode:
                self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                self.cursor_pos += 1
                text_changed = True
            
            if text_changed:
                # Trigger layout update on parent
                if self.parent and hasattr(self.parent, 'layout_children'):
                    self.parent.layout_children()
                return True
                
        return False

    def _get_cursor_pos_from_mouse(self, click_x, click_y):
        ui_scale = get_ui_scale()
        # Find line
        # Top Y is global_y + scaled_height
        top_y = self.global_y + self.scaled_height - (self.padding * ui_scale)
        
        relative_y = top_y - click_y
        # Ensure line_height is valid
        if self.line_height > 0:
            line_index = int(relative_y // self.line_height)
        else:
            line_index = 0
        
        if 0 <= line_index < len(self.lines):
            line = self.lines[line_index]
            # Find char index in line
            text_start_x = self.global_x + (self.padding * ui_scale)
            relative_x = click_x - text_start_x
            
            # Iterate chars to find closest
            best_index = 0
            min_dist = float('inf')
            
            blf.size(0, self.font_size, 72)
            
            for i in range(len(line['text']) + 1):
                w = blf.dimensions(0, line['text'][:i])[0]
                dist = abs(w - relative_x)
                if dist < min_dist:
                    min_dist = dist
                    best_index = i
                else:
                    break 
            
            return line['start'] + best_index
        elif line_index < 0:
            return 0
        else:
            return len(self.text)

class Row(Widget):
    def __init__(self):
        super().__init__(0, 0, 100, 30)
        self.children = []
        self.spacing = 10
        
        # Helper for adding widgets
        self.add = WidgetBuilder(self)

    def add_widget(self, widget):
        widget.parent = self
        self.children.append(widget)

    def update_layout(self):
        # Distribute width equally among children
        if not self.children:
            return
            
        count = len(self.children)
        # Total width available is self.width
        # Total padding needed is (count - 1) * padding
        total_padding = (count - 1) * self.spacing
        available_width = self.width - total_padding
        child_width = available_width // count
        
        # First pass: Update children layout to determine their desired height
        max_height = 0
        for child in self.children:
            child.width = child_width
            # If child has custom layout logic (like Button now), let it calculate height
            if hasattr(child, 'update_layout_custom'):
                child.update_layout_custom(child_width)
            else:
                child.update_layout()
            
            max_height = max(max_height, child.height)
        
        # Use max height for the row if not explicitly set (or if we want to expand)
        # For now, let's expand the row to fit the tallest child
        if max_height > self.height:
            self.height = max_height

        current_x = 0
        for child in self.children:
            child.x = current_x
            child.y = 0 # Relative to Row
            child.width = child_width
            # Force all children to match row height (stretch)
            child.height = self.height
            
            current_x += child_width + self.spacing

    def draw(self):
        # Row itself doesn't draw anything, just its children
        for child in self.children:
            child.draw()

    def handle_event(self, event, mouse_x=None, mouse_y=None):
        # Use provided window coordinates or convert from event
        if mouse_x is None or mouse_y is None:
            mouse_x = event.mouse_region_x
            mouse_y = event.mouse_region_y
        
        if mouse_x != -1:
            self.last_mouse_x = mouse_x
            self.last_mouse_y = mouse_y
        elif hasattr(self, 'last_mouse_x'):
            mouse_x = self.last_mouse_x
            mouse_y = self.last_mouse_y

        for child in self.children:
            # Update hover for children
            child.hover = child.is_inside(mouse_x, mouse_y)
            if child.handle_event(event, mouse_x=mouse_x, mouse_y=mouse_y):
                return True
        return False

class ProgressBar(Widget):
    def __init__(self, current=0.0, max_value=100.0, text="", show_percentage=True, show_values=False, parent=None, x=0, y=0, width=100, height=30):
        super().__init__(x, y, width, height, parent)
        self.current = current
        self.max_value = max_value
        self.text = text
        self.show_percentage = show_percentage
        self.show_values = show_values
        
        self.bg_color = get_theme_color(lambda t: t.user_interface.wcol_progress.inner)
        self.fill_color = get_theme_color(lambda t: t.user_interface.wcol_progress.item)
        self.text_color = get_theme_color(lambda t: t.user_interface.wcol_progress.text)
        self.padding = 5
        self.font_size_mult = 1.5
        self.last_update_time = 0
        self.update_interval = 0.2 # Throttle redraws

    def update(self, current, max_value=None, text=None, force_redraw=False):
        """
        Update progress bar state. Thread-safe.
        Args:
            force_redraw: If True, forces an immediate UI redraw (useful for blocking scripts).
        """
        import time
        self.current = current
        if max_value is not None:
            self.max_value = max_value
        if text is not None:
            self.text = text
            
        # Throttle redraws
        now = time.time()
        if now - self.last_update_time > self.update_interval or self.current >= self.max_value or force_redraw:
            self.last_update_time = now
            
            # Trigger redraw safely
            def trigger_redraw():
                try:
                    # Standard tag_redraw first to mark areas as dirty
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            area.tag_redraw()
                    # Force immediate redraw to prevent UI freezing during intensive tasks
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except:
                    pass
            
            try:
                trigger_redraw()
            except:
                # Fallback for threads where context is missing
                bpy.app.timers.register(trigger_redraw)

    def update_layout_custom(self, available_width):
        ui_scale = get_ui_scale()
        # Fixed height for now
        self.height = int(30 * ui_scale)

    def draw(self):
        # Draw background
        draw_rect(self.global_x, self.global_y, self.scaled_width, self.scaled_height, self.bg_color)
        
        # Draw fill
        if self.max_value > 0:
            percentage = max(0.0, min(1.0, self.current / self.max_value))
        else:
            percentage = 0.0
            
        fill_width = int(self.scaled_width * percentage)
        if fill_width > 0:
            draw_rect(self.global_x, self.global_y, fill_width, self.scaled_height, self.fill_color)
            
        # Draw border
        draw_rect_border(self.global_x, self.global_y, self.scaled_width, self.scaled_height, (0.4, 0.4, 0.4, 1.0), 1)
        
        # Draw Text
        display_text = self.text
        if self.show_percentage:
            display_text += f" {int(percentage * 100)}%"
        if self.show_values:
            display_text += f" ({self.current}/{self.max_value})"
            
        if display_text:
            ui_scale = get_ui_scale()
            base_font_size = get_theme_font_size()
            font_size = int(base_font_size * self.font_size_mult * ui_scale)
            
            blf.size(0, font_size, 72)
            text_width, text_height = blf.dimensions(0, display_text)
            
            # Add padding for text area
            text_padding = int(10 * ui_scale)
            available_width = self.scaled_width - (2 * text_padding)
            
            # Check if text overflows and truncate if necessary
            if text_width > available_width:
                # Truncate from the start to fit the available width
                for i in range(len(display_text) + 1):
                    truncated_text = display_text[i:]
                    tw, th = blf.dimensions(0, truncated_text)
                    if tw <= available_width:
                        display_text = truncated_text
                        text_width = tw
                        break
                # Right-align the truncated text
                text_x = self.global_x + self.scaled_width - text_padding - text_width
            else:
                # Center text normally
                text_x = self.global_x + (self.scaled_width - text_width) / 2
                
            center_y = self.global_y + (self.scaled_height / 2)
            text_y = center_y - (text_height / 3)
            
            blf.color(0, *self.text_color)
            blf.position(0, text_x, text_y, 0)
            blf.draw(0, display_text)

class Scrollbar(Widget):
    def __init__(self, orientation='vertical', width=16, parent=None):
        super().__init__(0, 0, width, 100, parent)
        self.orientation = orientation  # 'vertical' or 'horizontal'
        self.scroll_offset = 0
        self.max_scroll = 0
        self.thumb_size = 40
        self.min_thumb_size = 40
        self.thumb_position = 0
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_start_offset = 0
        self.on_scroll = None  # Callback for scroll changes
        
        # Theme colors
        self.track_color = get_theme_color(lambda t: t.user_interface.wcol_scroll.item)
        self.thumb_color = get_theme_color(lambda t: t.user_interface.wcol_scroll.slider)
        self.hover_thumb_color = get_theme_color(lambda t: (*t.user_interface.wcol_scroll.slider[:3], 0.8))  # Slightly transparent

    def set_scroll_info(self, scroll_offset, max_scroll, visible_size):
        self.scroll_offset = scroll_offset
        self.max_scroll = max_scroll
        if max_scroll > 0:
            self.thumb_size = max(self.min_thumb_size, (visible_size / (visible_size + max_scroll)) * self.height)
            self.thumb_position = (scroll_offset / max_scroll) * (self.height - self.thumb_size)
        else:
            self.thumb_size = self.height
            self.thumb_position = 0

    def draw(self):
        ui_scale = get_ui_scale()
        scaled_width = self.scaled_width
        scaled_height = self.scaled_height
        scaled_thumb_size = int(self.thumb_size * ui_scale)
        scaled_thumb_pos = int(self.thumb_position * ui_scale)
        
        # Draw track
        draw_rect(self.global_x, self.global_y, scaled_width, scaled_height, self.track_color)
        
        # Draw thumb
        thumb_color = self.hover_thumb_color if self.hover else self.thumb_color
        if self.orientation == 'vertical':
            # Draw from top (Y-up coordinate system)
            draw_rect(self.global_x, self.global_y + scaled_height - scaled_thumb_size - scaled_thumb_pos, scaled_width, scaled_thumb_size, thumb_color)
        else:
            draw_rect(self.global_x + scaled_thumb_pos, self.global_y, scaled_thumb_size, scaled_height, thumb_color)

    def is_inside_thumb(self, mouse_x, mouse_y):
        ui_scale = get_ui_scale()
        scaled_thumb_size = int(self.thumb_size * ui_scale)
        scaled_thumb_pos = int(self.thumb_position * ui_scale)
        scaled_height = self.scaled_height
        scaled_width = self.scaled_width
        
        if self.orientation == 'vertical':
            thumb_y = self.global_y + scaled_height - scaled_thumb_size - scaled_thumb_pos
            return (self.global_x <= mouse_x <= self.global_x + scaled_width and
                    thumb_y <= mouse_y <= thumb_y + scaled_thumb_size)
        else:
            return (self.global_x + scaled_thumb_pos <= mouse_x <= self.global_x + scaled_thumb_pos + scaled_thumb_size and
                    self.global_y <= mouse_y <= self.global_y + scaled_height)

    def handle_event(self, event, mouse_x=None, mouse_y=None):
        if mouse_x is None or mouse_y is None:
            return False
            
        # Update hover
        self.hover = self.is_inside(mouse_x, mouse_y)
        ui_scale = get_ui_scale()
        
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if self.is_inside_thumb(mouse_x, mouse_y):
                    self.is_dragging = True
                    self.drag_start_x = mouse_x
                    self.drag_start_y = mouse_y
                    self.drag_start_offset = self.scroll_offset
                    return True
                elif self.is_inside(mouse_x, mouse_y):
                    # Click on track - jump to position
                    if self.orientation == 'vertical':
                        # Calculate position from top (in pixels)
                        click_y_from_top_px = (self.global_y + self.scaled_height) - mouse_y
                        click_y_from_top = click_y_from_top_px / ui_scale
                        
                        # Center thumb on click
                        new_thumb_pos = max(0, min(click_y_from_top - self.thumb_size / 2, self.height - self.thumb_size))
                        new_offset = (new_thumb_pos / (self.height - self.thumb_size)) * self.max_scroll if self.height > self.thumb_size else 0
                    else:
                        click_pos_px = mouse_x - self.global_x
                        click_pos = click_pos_px / ui_scale
                        new_thumb_pos = max(0, min(click_pos - self.thumb_size / 2, self.width - self.thumb_size))
                        new_offset = (new_thumb_pos / (self.width - self.thumb_size)) * self.max_scroll if self.width > self.thumb_size else 0
                    
                    if self.on_scroll:
                        self.on_scroll(new_offset)
                    return True
            elif event.value == 'RELEASE':
                was_dragging = self.is_dragging
                self.is_dragging = False
                return was_dragging
        
        elif event.type == 'MOUSEMOVE' and self.is_dragging:
            if self.orientation == 'vertical':
                delta_px = self.drag_start_y - mouse_y
                delta = delta_px / ui_scale
                
                initial_thumb_pos = (self.drag_start_offset / self.max_scroll) * (self.height - self.thumb_size) if self.max_scroll > 0 else 0
                # Add delta because Y is up, thumb moves down as pos increases
                new_thumb_pos = max(0, min(initial_thumb_pos + delta, self.height - self.thumb_size))
                new_offset = (new_thumb_pos / (self.height - self.thumb_size)) * self.max_scroll if (self.height - self.thumb_size) > 0 else 0
            else:
                delta_px = mouse_x - self.drag_start_x
                delta = delta_px / ui_scale
                
                track_size = self.width - self.thumb_size
                if track_size > 0:
                    new_thumb_pos = max(0, min(self.drag_start_offset / self.max_scroll * track_size + delta, track_size))
                    new_offset = (new_thumb_pos / track_size) * self.max_scroll
                else:
                    new_offset = 0
            
            if self.on_scroll:
                self.on_scroll(new_offset)
            return True
        
        return False

class WidgetBuilder:
    def __init__(self, parent):
        self.parent = parent
    
    def label(self, text):
        self.parent.add_widget(Label(text))
        return self.parent
        
    def button(self, text, callback=None):
        self.parent.add_widget(Button(text, callback))
        return self.parent
        
    def text_input(self, text=""):
        widget = TextInput(text)
        self.parent.add_widget(widget)
        return widget # Return widget for text access
        
    def row(self):
        widget = Row()
        self.parent.add_widget(widget)
        return widget

class Popup(Widget):
    def __init__(self, title, label=None, width=None, height=None, prevent_close=False, blocking=False):
        # Center on screen (will be updated in draw or init)
        # For now, assume some defaults, operator will set actual position
        super().__init__(0, 0, width if width else 400, height if height else 300)
        self.title = title
        self.children = []
        self.bg_color = get_theme_color(lambda t: (*t.user_interface.wcol_menu_back.inner[:3], 0.95))
        self.border_color = get_theme_color(lambda t: t.user_interface.wcol_menu_back.outline)
        self.finished = False
        self.cancelled = False
        self.shown = False
        self.on_enter = None
        self.on_cancel = None
        self.padding = 10
        self.margin = 20
        self.title_height = 40
        self.auto_width = width is None
        self.auto_height = height is None
        self.is_dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self._prevent_close = prevent_close
        self._needs_layout_update = False
        self.blocking = blocking
        
        # Scrolling attributes
        self.scroll_offset = 0
        self.max_scroll = 0
        self.is_scrollable = False
        self.scrollbar = None
        self.content_height = 0
        self.visible_content_height = 0
        
        # Helper for adding widgets
        self.add = WidgetBuilder(self)
        
        # Debugging
        self.debug_clipping = False
        
        # Add label if provided
        if label:
            self.add_widget(Label(label))

    @property
    def prevent_close(self):
        return self._prevent_close
        
    @prevent_close.setter
    def prevent_close(self, value):
        if self._prevent_close != value:
            self._prevent_close = value
            self._needs_layout_update = True

    def add_widget(self, widget):
        widget.parent = self
        self.children.append(widget)
        return self  # Return self for chaining
    
    def show(self):
        """Show this popup (calls show_popup and returns self for chaining)."""
        import threading
        if threading.current_thread() is threading.main_thread():
            from .operators import is_showing_popup, popup_queue
            if is_showing_popup and not self.shown:
                # Queue this popup if another is already showing
                popup_queue.append(self)
                self.shown = True  # Mark as queued
                return self
            if not self.shown:
                from .operators import show_popup
                show_popup(self)
                self.shown = True
        return self

    def add_close_button(self, text="OK"):
        """
        Add a close button to the popup. Useful when prevent_close was True initially.
        
        Args:
            text: Button text (default: "OK")
        """
        def default_ok():
            self.finished = True
        
        close_button = Button(text, callback=default_ok)
        self.add_widget(close_button)
        
        # Set as Enter shortcut if not already set
        if not self.on_enter:
            self.on_enter = default_ok
        
        # Re-layout to recalculate height and positions
        # layout_children() handles height expansion and repositioning automatically
        self.layout_children()
        
        return close_button

    def layout_children(self):
        # Update title_height with scale
        self.title_height = int(45 * get_ui_scale())
        
        # Pass 1: Determine Width
        # If auto-width, we need to calculate max width from children
        # For now, we'll use the provided width or a default
        if self.auto_width:
            self.width = 400 # Default width if not specified
            # Ideally we would expand to fit content, but wrapping requires a known width.
            # So we set a default/min width.

        # Pass 2: Update Children Layout (Text Wrapping)
        # We pass the available width to children so they can wrap/resize
        # Initially assume no scrollbar
        content_width = self.width - (2 * self.margin)
        
        for child in self.children:
            # Update child layout with available width
            if hasattr(child, 'update_layout_custom'):
                child.update_layout_custom(content_width)
            else:
                child.update_layout()

        # Pass 3: Calculate Height and Position
        # Use unscaled title height for calculation
        unscaled_title_height = 45
        total_content_height = unscaled_title_height + self.padding
        total_child_height = 0
        
        for i, child in enumerate(self.children):
            total_content_height += child.height
            total_child_height += child.height
            if i < len(self.children) - 1:
                total_content_height += self.padding
                total_child_height += self.padding
                
        # Add bottom margin
        total_content_height += self.margin
        
        # Store content height for scrolling calculations
        self.content_height = total_child_height
        
        # Determine if scrolling is needed
        max_height = self._get_max_popup_height()
        self.is_scrollable = total_content_height > max_height
        
        if self.is_scrollable:
            # Calculate scaled values
            ui_scale = get_ui_scale()
            scaled_margin = int(self.margin * ui_scale)
            # set scrollbar width
            scrollbar_width = 16

            # Set popup height to maximum allowed (convert pixels to unscaled)
            self.height = int(max_height / ui_scale)
            self.visible_content_height = int((self.scaled_height - self.title_height) / ui_scale)
            
            # Calculate max scroll (initial estimate)
            self.max_scroll = max(0, self.content_height - self.visible_content_height)
            
            # Re-layout children with reduced width for scrollbar and margins
            content_width = self.width - scrollbar_width - 2 * self.margin
            
            # Recalculate height as children might have grown (e.g. text wrapping)
            new_total_child_height = 0
            
            for i, child in enumerate(self.children):
                if hasattr(child, 'update_layout_custom'):
                    child.update_layout_custom(content_width)
                else:
                    child.update_layout()
                
                new_total_child_height += child.height
                if i < len(self.children) - 1:
                    new_total_child_height += self.padding
            
            # Add bottom margin
            new_total_child_height += self.margin

            # Update content height
            self.content_height = new_total_child_height
            
            # Update max scroll with new height
            self.max_scroll = max(0, self.content_height - self.visible_content_height)
            
            # Clamp scroll offset again just in case
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
            
            # Create or update scrollbar
            if self.scrollbar is None:
                self.scrollbar = Scrollbar('vertical', scrollbar_width, self)
                self.scrollbar.on_scroll = self._on_scroll
            self.scrollbar.height = self.visible_content_height
            self.scrollbar.set_scroll_info(self.scroll_offset, self.max_scroll, self.visible_content_height)
            self.scrollbar.x = self.width - self.scrollbar.width
            self.scrollbar.y = 0
        else:
            # No scrolling needed
            self.height = total_content_height if self.auto_height else self.height
            self.scroll_offset = 0
            self.max_scroll = 0
            content_width = self.width - (2 * self.margin)  # No scrollbar
            if self.scrollbar:
                self.scrollbar = None
        
        # Update popup height if auto and not scrollable
        if self.auto_height and not self.is_scrollable:
            # Store old center for expansion
            ui_scale = get_ui_scale()
            old_height_scaled = self.scaled_height
            old_center_y = self.global_y + (old_height_scaled / 2)
            
            self.height = total_content_height
            
            # Recalculate position to keep centered
            new_height_scaled = self.scaled_height
            new_y = old_center_y - (new_height_scaled / 2)
            
            # Clamp to region
            try:
                region = bpy.context.region
                if region:
                    self.height = total_content_height
                    
                    # Recalculate position to keep centered
                    new_height_scaled = self.scaled_height
                    new_y = old_center_y - (new_height_scaled / 2)
                    
                    max_y = region.height - new_height_scaled
                    self.y = int(max(0, min(new_y, max_y))) # Keep in pixels
                else:
                    self.y = int(new_y)
            except:
                self.y = int(new_y)
        
        # Now position children
        # Position relative to content area top, accounting for scroll offset
        # For scrolling, start from visible + scroll_offset to show top content at scroll_offset=0
        start_y = (self.visible_content_height + self.scroll_offset) if self.is_scrollable else total_child_height
        current_y = start_y
        
        for i, child in enumerate(self.children):
            current_y -= child.height
            child.x = self.margin
            child.width = content_width
            child.y = current_y
            
            # Update child layout (e.g. Row) - might need re-update if position changed?
            # Row update_layout distributes width, which we already set.
            # But we call it again just in case.
            child.update_layout()
            
            current_y -= self.padding

    def _get_max_popup_height(self):
        """Get the maximum height for the popup (75% of region height)"""
        try:
            region = getattr(self, 'target_region', None)
            if region:
                return int(region.height * 0.75)
            else:
                # Fallback to window height
                window = bpy.context.window
                if window:
                    return int(window.height * 0.75)
        except:
            pass
        return 600  # Ultimate fallback

    def _on_scroll(self, new_offset):
        """Callback for scrollbar scroll events"""
        self.scroll_offset = max(0, min(new_offset, self.max_scroll))
        self.layout_children()  # Re-layout to update positions

    @property
    def global_x(self):
        # Popup is root, so global_x is just x (which is set in pixels in update_layout)
        return self.x

    @property
    def global_y(self):
        # Popup is root, so global_y is just y (which is set in pixels in update_layout)
        return self.y

    def update_layout(self, context):
        # Store the target region for height calculations
        self.target_region = context.region
        
        # Add default OK button if no buttons exist and prevent_close is False
        has_button = False
        for child in self.children:
            if isinstance(child, Button):
                has_button = True
                break
            # Check in Row widgets too
            if isinstance(child, Row):
                for row_child in child.children:
                    if isinstance(row_child, Button):
                        has_button = True
                        break
        
        # Only add default OK button if none found AND prevent_close is False
        if not has_button and not self.prevent_close:
            def default_ok():
                self.finished = True
            
            default_button = Button("OK", callback=default_ok)
            self.add_widget(default_button)
            
            # Set as Enter shortcut if not already set
            if not self.on_enter:
                self.on_enter = default_ok
        
        # Determine the target region for positioning and height calculations
        region = getattr(self, 'target_region', context.region)
        if region is None:
            # Fallback when called from timer/thread - get the first available region
            try:
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':  # Prefer 3D view
                            region = area.regions[-1]  # Use the last region (main viewport)
                            break
                    if region:
                        break
                # If no 3D view found, use any region
                if region is None:
                    for window in context.window_manager.windows:
                        for area in window.screen.areas:
                            if area.regions:
                                region = area.regions[-1]
                                break
                        if region:
                            break
            except:
                # Ultimate fallback - use default dimensions
                region = None
        
        # Set the final target region
        self.target_region = region
        
        # Now layout children to determine height (uses target_region)
        self.layout_children()
        
        # Center popup in region
        if region:
            # Position popup in window coordinates (add region offset)
            self.x = region.x + (region.width - self.scaled_width) // 2
            self.y = region.y + (region.height - self.scaled_height) // 2
        else:
            # Fallback to center of window if no region available
            if context.window:
                self.x = (context.window.width - self.scaled_width) // 2
                self.y = (context.window.height - self.scaled_height) // 2
            else:
                self.x = 100
                self.y = 100

    def draw(self, context):
        if self._needs_layout_update:
            self.update_layout(context)
            self._needs_layout_update = False
            
        # Adjust for region offset to draw in window coordinates
        gpu.matrix.push()
        if context.region:
            gpu.matrix.translate((-context.region.x, -context.region.y, 0.0))
        
        # Draw background
        bg_color = self.bg_color
        
        draw_rect(self.global_x, self.global_y, self.scaled_width, self.scaled_height, bg_color)
        draw_rect_border(self.global_x, self.global_y, self.scaled_width, self.scaled_height, self.border_color, 2)
        
        # Draw Header
        ui_scale = get_ui_scale()
        base_font_size = get_theme_font_size()
        
        # Header height
        header_height = int(45 * ui_scale)
        header_y = self.global_y + self.scaled_height - header_height
        
        # Header color from theme
        header_color = get_theme_color(lambda t: t.user_interface.wcol_menu.inner)
        
        draw_rect(self.global_x, header_y, self.scaled_width, header_height, header_color)
        
        # Draw Title
        title_size = int(base_font_size * 1.8 * ui_scale) # Same size as body
        blf.size(0, title_size, 72)
        # Title text color should be white as requested
        blf.color(0, 1, 1, 1, 1)
        
        title_width, title_height = blf.dimensions(0, self.title)
        title_x = self.global_x + (self.margin * ui_scale)
        # Center vertically: header center Y minus text height adjustment for baseline
        center_y = header_y + (header_height / 2)
        title_y = center_y - (title_height / 3)
        
        blf.position(0, title_x, title_y, 0)
        blf.draw(0, self.title)
        
        # Draw Children
        if self.is_scrollable:
            # Set scissor test to clip content to popup area below title with margins
            content_y = self.global_y
            content_height = self.scaled_height - header_height
            scaled_margin = int(self.margin * ui_scale)
            scissor_x = int(self.global_x + scaled_margin - context.region.x)
            scissor_y = int(content_y - context.region.y)
            scissor_width = int(self.scaled_width - self.scrollbar.scaled_width - 2 * scaled_margin)
            scissor_height = int(content_height)
            gpu.state.scissor_test_set(True)
            gpu.state.scissor_set(scissor_x, scissor_y, scissor_width, scissor_height)
        
        for child in self.children:
            child.draw()
        
        if self.is_scrollable:
            # Disable scissor test
            gpu.state.scissor_test_set(False)
            
            # Draw scrollbar
            if self.scrollbar:
                self.scrollbar.draw()
        
        gpu.matrix.pop()

    def handle_event(self, event, context, mouse_x=None, mouse_y=None):
        # Use provided window coordinates or convert from event
        if mouse_x is None or mouse_y is None:
            mouse_x = event.mouse_x
            mouse_y = event.mouse_y
        
        # Store last mouse position for when coordinates are invalid
        if mouse_x != -1:
            self.last_mouse_x = mouse_x
            self.last_mouse_y = mouse_y
        elif hasattr(self, 'last_mouse_x'):
            mouse_x = self.last_mouse_x
            mouse_y = self.last_mouse_y

        # Update hover for all children
        for child in self.children:
            child.hover = child.is_inside(mouse_x, mouse_y)
        
        # Update scrollbar hover
        if self.scrollbar:
            self.scrollbar.hover = self.scrollbar.is_inside(mouse_x, mouse_y)

        # Handle mouse wheel scrolling
        if self.is_scrollable and event.type in ('WHEELUPMOUSE', 'WHEELDOWNMOUSE'):
            scroll_amount = 20  # Pixels to scroll per wheel event
            if event.type == 'WHEELDOWNMOUSE':
                # Wheel down -> Scroll down -> Increase offset
                pass 
            else:
                # Wheel up -> Scroll up -> Decrease offset
                scroll_amount = -scroll_amount
            
            new_offset = self.scroll_offset + scroll_amount
            self._on_scroll(new_offset)
            return True

        # Handle dragging
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # Check if clicking header for drag
                ui_scale = get_ui_scale()
                header_height = int(45 * ui_scale)
                header_y = self.global_y + self.scaled_height - header_height
                
                if (self.global_x <= mouse_x <= self.global_x + self.scaled_width and
                    header_y <= mouse_y <= header_y + header_height):
                    self.is_dragging = True
                    self.drag_offset_x = mouse_x - self.global_x
                    self.drag_offset_y = mouse_y - self.global_y
                    return True
            
            elif event.value == 'RELEASE':
                if self.is_dragging:
                    self.is_dragging = False
                    return True
        
        if event.type == 'MOUSEMOVE' and self.is_dragging:
            new_x = mouse_x - self.drag_offset_x
            new_y = mouse_y - self.drag_offset_y
            # Keep within window bounds
            window = context.window
            self.x = max(0, min(new_x, window.width - self.scaled_width))
            self.y = max(0, min(new_y, window.height - self.scaled_height))
            return True

        # Handle scrollbar events
        if self.scrollbar and self.scrollbar.handle_event(event, mouse_x, mouse_y):
            return True

        # Pass event to children
        for child in reversed(self.children):
            if child.handle_event(event, mouse_x=mouse_x, mouse_y=mouse_y):
                return True

        # Consume mouse events if they occur within the popup area
        if event.type in ('LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE') and event.value == 'PRESS':
            if self.is_inside(mouse_x, mouse_y):
                return True

        # Handle Enter key (OK)
        if event.type == 'RET' and event.value == 'PRESS':
            if self.prevent_close:
                return True # Consume event but don't close
                
            if self.on_enter:
                self.on_enter()
                return True

        # Handle ESC key (Cancel)
        if event.type == 'ESC' and event.value == 'PRESS':
            if self.prevent_close:
                return True # Consume event but don't close
                
            if self.on_cancel:
                self.on_cancel()
                return True
            else:
                # Default cancel behavior if no callback
                self.cancelled = True
                return True

        return False


# Drawing Utilities
shader = gpu.shader.from_builtin('UNIFORM_COLOR') if hasattr(gpu.shader, 'from_builtin') else gpu.shader.from_builtin('2D_UNIFORM_COLOR')

def draw_rect(x, y, width, height, color):
    batch = batch_for_shader(shader, 'TRIS', {"pos": [(x, y), (x+width, y), (x+width, y+height), (x, y+height)]}, indices=[(0, 1, 2), (0, 2, 3)])
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

def draw_rect_border(x, y, width, height, color, thickness=1):
    # Simple line drawing for border
    # Top
    draw_rect(x, y + height - thickness, width, thickness, color)
    # Bottom
    draw_rect(x, y, width, thickness, color)
    # Left
    draw_rect(x, y, thickness, height, color)
    # Right
    draw_rect(x + width - thickness, y, thickness, height, color)
