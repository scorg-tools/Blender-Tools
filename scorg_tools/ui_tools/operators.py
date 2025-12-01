import bpy
import gpu
import blf
from . import ui_system

# Global to hold the active popup instance
active_popup = None
draw_handler = None

# Global popup queue for sequential display
popup_queue = []

# Flag to indicate if a popup is currently being shown
is_showing_popup = False

# Configurable operator prefix (can be set before registration)
OPERATOR_PREFIX = "uitools"

class UITOOLS_OT_custom_popup(bpy.types.Operator):
    bl_idname = "uitools.custom_popup"
    bl_label = "Custom Popup"
    bl_options = {'REGISTER'}

    def __init__(self):
        self.draw_handler = None
        self.space_type = None
        self.active_popup = None

    def modal(self, context, event):
        global active_popup, is_showing_popup
        if not self.active_popup:
            self.remove_handler(context)
            return {'CANCELLED'}

        # Check if popup wants to close
        if self.active_popup.finished:
            active_popup = None  # Clear the global active popup
            is_showing_popup = False
            self.remove_handler(context)
            return {'FINISHED'}
            
        if self.active_popup.cancelled:
            active_popup = None  # Clear the global active popup
            is_showing_popup = False
            self.remove_handler(context)
            return {'CANCELLED'}

        # Force redraw to keep UI updated
        if self.area:
            self.area.tag_redraw()
        else:
            # Fallback if no area stored
            if context.area:
                context.area.tag_redraw()
            else:
                # Find an area to redraw when context.area is None
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
                            break
                    else:
                        continue
                    break

        if event.type == 'TIMER':
            return {'PASS_THROUGH'}

        # Pass event to popup
        # Convert mouse coordinates to window coordinates for proper interaction
        if context.region:
            mouse_x = context.region.x + event.mouse_region_x
            mouse_y = context.region.y + event.mouse_region_y
        else:
            # Fallback when region is not available (use window coordinates directly)
            mouse_x = event.mouse_x
            mouse_y = event.mouse_y
        
        handled = self.active_popup.handle_event(event, context, mouse_x, mouse_y)

        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            return {'PASS_THROUGH'} 
            
        # Pass through navigation events if not handled
        # This allows rotating/panning the viewport while popup is open
        # ONLY if blocking is False
        if not handled and not self.active_popup.blocking:
            if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} or \
               (event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and not self.active_popup.is_inside(event.mouse_region_x, event.mouse_region_y)):
                return {'PASS_THROUGH'}
            
        # Check if popup finished/cancelled during event handling
        if active_popup.finished:
            active_popup = None  # Clear the global active popup
            is_showing_popup = False
            self.remove_handler(context)
            return {'FINISHED'}
        if active_popup.cancelled:
            active_popup = None  # Clear the global active popup
            is_showing_popup = False
            self.remove_handler(context)
            return {'CANCELLED'}
            
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        global active_popup
        if not active_popup:
            self.report({'ERROR'}, "No active popup definition")
            return {'CANCELLED'}
        
        self.active_popup = active_popup

        try:
            active_popup.update_layout(context)
            
            # Add draw handler to the current space
            self.space = context.space_data
            self.area = context.area  # Store the original area
            self.popup_region = context.region  # Store the region for drawing
            
            # Always use VIEW_3D for consistent popup display
            self.space = None
            self.area = None
            
            # Find VIEW_3D
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        self.space = area.spaces[0]
                        self.area = area
                        break
                if self.space:
                    break
            
            if self.area:
                active_popup.target_region = self.area.regions[-1]
            
            if self.space is None:
                self.report({'ERROR'}, "No VIEW_3D area available for popup")
                return {'CANCELLED'}
            

            
            # Ensure we have an area for redraw
            if self.area is None and self.space is not None:
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.spaces and area.spaces[0] == self.space:
                            self.area = area
                            break
                    if self.area:
                        break
            
            self.draw_handler = self.space.draw_handler_add(
                self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
            )
            
            context.window_manager.modal_handler_add(self)
            if context.area:
                context.area.tag_redraw() # Request initial redraw
            
            # Update layout with the appropriate region
            layout_context = context
            self.layout_region = context.region  # Store the region used for layout
            if self.area and self.area != context.area and self.area.regions:
                # Create a modified context with the correct region for layout
                layout_context = type('Context', (), {})()
                for attr in dir(context):
                    if not attr.startswith('_'):
                        setattr(layout_context, attr, getattr(context, attr))
                layout_context.region = self.area.regions[-1]
                self.layout_region = layout_context.region  # Store the actual region used
            self.active_popup.update_layout(layout_context)
            
            return {'RUNNING_MODAL'}
        except Exception as e:
            print(f"Failed to show popup: {e}")
            return {'CANCELLED'}

    def draw_callback(self, context):
        if self.active_popup:
            # Layout is set once in invoke, no need to update every frame
            self.active_popup.draw(context)
            self.active_popup.draw(context)

    def remove_handler(self, context):
        if self.draw_handler and self.space:
            self.space.draw_handler_remove(self.draw_handler, 'WINDOW')
            self.draw_handler = None
            self.space = None
        if self.area:
            self.area.tag_redraw()
        else:
            # Fallback if no area stored
            if context.area:
                context.area.tag_redraw()
        
        # Check if there are queued popups and show the next one
        if popup_queue:
            next_popup = popup_queue.pop(0)
            # Call show_popup directly to show the next popup
            show_popup(next_popup)

def show_popup(popup_instance):
    """
    Display a popup.
    
    Args:
        popup_instance: A Popup instance to display
    """
    global active_popup, is_showing_popup
    
    is_showing_popup = True
    active_popup = popup_instance
    try:
        bpy.ops.uitools.custom_popup('INVOKE_DEFAULT')
    except Exception as e:
        print(f"Failed to show popup: {e}")
    
    # Force immediate redraw to ensure popup appears before any blocking code
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except:
        pass

classes = (
    UITOOLS_OT_custom_popup,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
