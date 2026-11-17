import bpy

def update_keymaps(self, context):
    import sys
    if __package__ in sys.modules:
        main_mod = sys.modules[__package__]
        if hasattr(main_mod, 'unregister_keymaps') and hasattr(main_mod, 'register_keymaps'):
            main_mod.unregister_keymaps()
            main_mod.register_keymaps()

def update_autosave(self, context):
    import sys
    if __package__ in sys.modules:
        main_mod = sys.modules[__package__]
        pie_save = getattr(main_mod, 'pie_save', None)
        if pie_save and hasattr(pie_save, 'sync_autosave_timer'):
            pie_save.sync_autosave_timer()

class M3_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    tabs: bpy.props.EnumProperty(
        name="Tabs",
        items=[
            ("GENERAL", "General", ""),
            ("KEYMAPS", "Keymaps", ""),
            ("ABOUT", "About", "")
        ],
        default="GENERAL"
    )

    activate_focus: bpy.props.BoolProperty(
        name="Focus",
        default=True,
        update=update_keymaps
    )
    
    activate_views_pie: bpy.props.BoolProperty(
        name="Views Pie",
        default=True,
        update=update_keymaps
    )
    
    activate_cursor_origin_pie: bpy.props.BoolProperty(
        name="Cursor & Origin Pie",
        default=True,
        update=update_keymaps
    )

    activate_save_pie: bpy.props.BoolProperty(
        name="Save Pie",
        default=True,
        update=update_keymaps
    )

    # Auto Save

    autosave_enabled: bpy.props.BoolProperty(
        name="Auto Save",
        description="Save the file automatically at a fixed interval",
        default=False,
        update=update_autosave
    )

    autosave_interval: bpy.props.IntProperty(
        name="Interval",
        description="Seconds between auto saves",
        default=30,
        min=1,
        soft_max=600,
    )

    autosave_limit: bpy.props.IntProperty(
        name="File Limit",
        description="Maximum number of auto save files kept in the folder",
        default=20,
        min=1,
        soft_max=100,
    )

    autosave_mode: bpy.props.EnumProperty(
        name="Mode",
        description="What gets written when auto saving",
        items=[
            ('EXTERNAL', "Save Copy", "Save a copy, leaving the current file untouched"),
            ('SELF', "Save File", "Save the current file itself"),
        ],
        default='EXTERNAL',
    )

    autosave_folder: bpy.props.StringProperty(
        name="Folder",
        description="Auto save folder. Falls back to the system's temp folder when empty",
        subtype='DIR_PATH',
        default="",
    )

    autosave_pre_undo: bpy.props.BoolProperty(
        name="Save before Undo",
        description="Save before every undo step, useful if Blender crashes while undoing",
        default=True,
    )

    autosave_pre_redo: bpy.props.BoolProperty(
        name="Save before Redo",
        description="Save before every redo step",
        default=False,
    )

    autosave_hud: bpy.props.BoolProperty(
        name="Show HUD",
        description="Show a quick fading message when a file was auto saved",
        default=True,
    )

    def draw(self, context):
        layout = self.layout

        # Tabs Row
        row = layout.row(align=True)
        row.prop(self, "tabs", expand=True)

        layout.separator()

        if self.tabs == "GENERAL":
            self.draw_general(context)
        elif self.tabs == "KEYMAPS":
            self.draw_keymaps(context)
        elif self.tabs == "ABOUT":
            self.draw_about(context)

    def draw_general(self, context):
        layout = self.layout
        split = layout.split(factor=0.33)

        # Left Column: Activate
        col = split.column()
        box = col.box()
        box.label(text="Tools")
        
        row = box.row(align=True)
        row.prop(self, "activate_focus", toggle=True, text="Focus")
        
        box = col.box()
        box.label(text="Pie Menus")
        
        row = box.row(align=True)
        row.prop(self, "activate_views_pie", toggle=True, text="Views Pie")
        
        row = box.row(align=True)
        row.prop(self, "activate_cursor_origin_pie", toggle=True, text="Cursor & Origin Pie")

        row = box.row(align=True)
        row.prop(self, "activate_save_pie", toggle=True, text="Save Pie")

        # Right Column: Settings
        col = split.column()
        box = col.box()
        box.label(text="Settings")

        sub = box.box()
        sub.label(text="Save Pie · Auto Save", icon='FILE_TICK')

        sub.prop(self, "autosave_enabled", text="Enable Auto Saving")

        row = sub.row(align=True)
        row.prop(self, "autosave_interval", text="Interval (s)")
        row.prop(self, "autosave_limit", text="File Limit")

        sub.prop(self, "autosave_mode", expand=True)
        sub.prop(self, "autosave_folder", text="Folder")

        row = sub.row(align=True)
        row.prop(self, "autosave_pre_undo", text="Save before Undo")
        row.prop(self, "autosave_pre_redo", text="Save before Redo")

        sub.prop(self, "autosave_hud", text="Show HUD Message")

    def draw_keymaps(self, context):
        layout = self.layout
        split = layout.split(factor=0.5)

        # Left Column: Tools
        col1 = split.column()
        box1 = col1.box()
        box1.label(text="Tools")

        # Right Column: Pie Menus
        col2 = split.column()
        box2 = col2.box()
        box2.label(text="Pie Menus")

        wm = context.window_manager
        if not wm.keyconfigs.addon and not wm.keyconfigs.user:
            return

        # Our shortcuts are created in the addon keyconfig, but may be rebound
        # in the user keyconfig, so both are scanned. User entries win.
        keymaps = []
        for config_name in ("addon", "user"):
            kc = getattr(wm.keyconfigs, config_name, None)
            if not kc:
                continue
            km = kc.keymaps.get('3D View')
            if km:
                keymaps.append(km)

        if not keymaps:
            return

        # Helper function to draw keymap items
        def draw_kmi(parent, idname, label, properties=None):
            items = {}

            for km in keymaps:
                for kmi in km.keymap_items:
                    if kmi.idname != idname:
                        continue

                    if properties:
                        match = True
                        for k, v in properties.items():
                            if getattr(kmi.properties, k, None) != v:
                                match = False
                                break
                        if not match:
                            continue

                    signature = (kmi.type, kmi.ctrl, kmi.alt, kmi.shift, kmi.oskey,
                                kmi.any, kmi.key_modifier, kmi.map_type)
                    items[signature] = kmi

            for kmi in items.values():
                row = parent.row(align=True)
                row.label(text=label)
                row.prop(kmi, "active", text="")
                row.label(text=kmi.name)
                row.prop(kmi, "map_type", text="")
                row.prop(kmi, "type", text="", full_event=True)

        if self.activate_focus:
            b = box1.box()
            b.label(text="Focus")
            draw_kmi(b, "m3.focus", "View Selected")
            draw_kmi(b, "m3.local_view", "Local View", {"invert": False})
            draw_kmi(b, "m3.local_view", "Local View (Inverted)", {"invert": True})
            
        if self.activate_views_pie:
            b = box2.box()
            b.label(text="Views Pie")
            draw_kmi(b, "wm.call_menu_pie", "in 3D View", {"name": "M3_MT_views_pie"})
            
        if self.activate_cursor_origin_pie:
            b = box2.box()
            b.label(text="Cursor & Origin Pie")
            draw_kmi(b, "wm.call_menu_pie", "in 3D View", {"name": "M3_MT_cursor_origin_pie"})

        if self.activate_save_pie:
            b = box2.box()
            b.label(text="Save Pie")
            draw_kmi(b, "wm.call_menu_pie", "in 3D View", {"name": "M3_MT_save_pie"})

    def draw_about(self, context):
        layout = self.layout
        layout.label(text="SmartTools")
        layout.label(text="Smart viewport focus, local view isolation, pie menus, cursor alignment, and file saving tools.")

classes = (
    M3_AddonPreferences,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
