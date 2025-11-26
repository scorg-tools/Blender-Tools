import bpy
import gpu
import blf
from . import ui_system

# Global to hold the active popup instance
active_popup = None
draw_handler = None

# Configurable operator prefix (can be set before registration)
OPERATOR_PREFIX = "uitools"

class UITOOLS_OT_custom_popup(bpy.types.Operator):
    bl_idname = "uitools.custom_popup"
    bl_label = "Custom Popup"
    bl_options = {'REGISTER', 'INTERNAL'}

    def __init__(self):
        self.draw_handler = None
        self.space_type = None

    def modal(self, context, event):
        global active_popup
        
        if not active_popup:
            self.remove_handler(context)
            return {'CANCELLED'}

        # Force redraw to keep UI updated
        context.area.tag_redraw()

        if event.type == 'TIMER':
            return {'PASS_THROUGH'}

        # Pass event to popup
        handled = active_popup.handle_event(event, context)
        
        # Check if popup wants to close
        if active_popup.finished:
            self.remove_handler(context)
            return {'FINISHED'}
            
        if active_popup.cancelled:
            self.remove_handler(context)
            return {'CANCELLED'}

        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            return {'PASS_THROUGH'} 
            
        # Pass through navigation events if not handled
        # This allows rotating/panning the viewport while popup is open
        # ONLY if blocking is False
        if not handled and not active_popup.blocking:
            if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} or \
               (event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and not active_popup.is_inside(event.mouse_region_x, event.mouse_region_y)):
                return {'PASS_THROUGH'}
            
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        global active_popup
        if not active_popup:
            self.report({'ERROR'}, "No active popup definition")
            return {'CANCELLED'}

        active_popup.update_layout(context)
        
        # Add draw handler to the current space
        self.space = context.space_data
        self.draw_handler = self.space.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL'
        )
        
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw() # Request initial redraw
        return {'RUNNING_MODAL'}

    def draw_callback(self, context):
        global active_popup
        if active_popup:
            active_popup.draw(context)

    def remove_handler(self, context):
        if self.draw_handler and self.space:
            self.space.draw_handler_remove(self.draw_handler, 'WINDOW')
            self.draw_handler = None
            self.space = None
        context.area.tag_redraw()

def show_popup(popup_instance):
    """
    Display a popup.
    
    Args:
        popup_instance: A Popup instance to display
    """
    global active_popup
    active_popup = popup_instance
    bpy.ops.uitools.custom_popup('INVOKE_DEFAULT')
    
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
