# Removed bl_info, now using blender_manifest.toml

import bpy
from . import preferences
from . import ops_focus
from . import pie_views
from . import pie_cursor_origin
from . import pie_save

modules = (
    preferences,
    ops_focus,
    pie_views,
    pie_cursor_origin,
    pie_save,
)

addon_keymaps = []

def get_prefs():
    return bpy.context.preferences.addons[__package__].preferences

def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
        
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    prefs = get_prefs()
    
    # Focus Tools
    if prefs.activate_focus:
        kmi = km.keymap_items.new("m3.focus", 'F', 'PRESS')
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new("m3.local_view", 'F', 'PRESS', ctrl=True)
        kmi.properties.invert = False
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new("m3.local_view", 'F', 'PRESS', ctrl=True, alt=True)
        kmi.properties.invert = True
        addon_keymaps.append((km, kmi))
        
    # Views Pie
    if prefs.activate_views_pie:
        kmi = km.keymap_items.new("wm.call_menu_pie", 'PAGE_DOWN', 'PRESS')
        kmi.properties.name = "M3_MT_views_pie"
        addon_keymaps.append((km, kmi))
        
        kmi = km.keymap_items.new("wm.call_menu_pie", 'ACCENT_GRAVE', 'PRESS')
        kmi.properties.name = "M3_MT_views_pie"
        addon_keymaps.append((km, kmi))
        
        # Next / Prev Cam
        kmi = km.keymap_items.new("m3.next_cam", 'PAGE_UP', 'PRESS')
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new("m3.prev_cam", 'PAGE_UP', 'PRESS', shift=True)
        addon_keymaps.append((km, kmi))
        
    # Cursor & Origin Pie
    if prefs.activate_cursor_origin_pie:
        kmi = km.keymap_items.new("wm.call_menu_pie", 'S', 'PRESS', shift=True)
        kmi.properties.name = "M3_MT_cursor_origin_pie"
        addon_keymaps.append((km, kmi))

    # Save Pie
    if prefs.activate_save_pie:
        kmi = km.keymap_items.new("wm.call_menu_pie", 'S', 'PRESS', ctrl=True)
        kmi.properties.name = "M3_MT_save_pie"
        addon_keymaps.append((km, kmi))

def unregister_keymaps():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ValueError, ReferenceError):
            pass
    addon_keymaps.clear()

def register():
    for mod in modules:
        mod.register()
    register_keymaps()

def unregister():
    unregister_keymaps()
    for mod in reversed(modules):
        mod.unregister()

if __name__ == "__main__":
    register()
