import bpy
import blf
import os
import re
import time
import tempfile

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def get_prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError, TypeError):
        return None

def op_exists(idname):
    # bpy.ops can create wrappers for unregistered operators too.
    return op_rna(idname) is not None

def op_rna(idname):
    try:
        mod, name = idname.split(".", 1)
        return getattr(getattr(bpy.ops, mod), name).get_rna_type()
    except Exception:
        return None

def is_backup(path):
    return bool(path) and re.search(r"\.blend\d+$", path) is not None

def is_dirty():
    """True when the current file has unsaved changes.

    Blender only tracks this in an interactive session, so it stays a tiny
    seam that tests can replace.
    """
    return bpy.data.is_dirty

EXPORT_SELECTION_PROPS = (
    "use_selection",
    "export_selected_objects",
    "selected_objects_only",
    "use_selected_objects",
)

def apply_export_selection(operator, idname, context):
    """Point an export operator at the selection, when it supports that.

    Operator properties go on the object UILayout.operator() returns - they are
    never keyword arguments of UILayout.operator() itself.
    """
    if not context.selected_objects:
        return

    rna = op_rna(idname)
    if rna is None:
        return

    for prop in EXPORT_SELECTION_PROPS:
        if prop in rna.properties:
            setattr(operator, prop, True)
            return

def add_path_to_recent_files(path):
    recent_path = bpy.utils.user_resource('CONFIG', path="recent-files.txt")
    try:
        with open(recent_path, "r+", encoding="utf-8", errors="replace") as f:
            content = f.read()
            f.seek(0, 0)
            f.write(path.rstrip('\r\n') + '\n' + content)
    except (OSError, IOError):
        pass

def recent_files():
    recent_path = bpy.utils.user_resource('CONFIG', path="recent-files.txt")
    try:
        with open(recent_path, encoding="utf-8", errors="replace") as f:
            return [l.strip() for l in f.read().splitlines() if l.strip()]
    except (OSError, IOError):
        return []

def get_incremented_paths(currentblend):
    """
    scene.blend      -> scene_001.blend    (+ scene_01.blend as sub-increment)
    scene_001.blend  -> scene_002.blend    (+ scene_001_01.blend)
    """
    path = os.path.dirname(currentblend)
    filename = os.path.basename(currentblend)

    mo = re.match(r"(.+)\.blend\d*$", filename)
    if not mo:
        return None, None

    name = mo.group(1)
    mo = re.match(r"(.*?)(\d+)$", name)

    if mo:
        basename, numberstr = mo.group(1), mo.group(2)
    else:
        basename, numberstr = name + "_", "000"

    number = int(numberstr) + 1
    incrstr = str(number).zfill(len(numberstr))

    return os.path.join(path, basename + incrstr + ".blend"), os.path.join(path, name + "_01.blend")

def next_free(path):
    """Bump the trailing number until the path is unused."""
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    mo = re.match(r"(.*?)(\d+)$", base)

    if mo:
        stem, digits = mo.group(1), mo.group(2)
        number = int(digits) + 1
        while True:
            candidate = f"{stem}{str(number).zfill(len(digits))}{ext}"
            if not os.path.exists(candidate):
                return candidate
            number += 1

    number = 2
    while True:
        candidate = f"{base}_{number}{ext}"
        if not os.path.exists(candidate):
            return candidate
        number += 1

def blend_files(folder):
    try:
        return sorted(f for f in os.listdir(folder) if f.endswith(".blend"))
    except OSError:
        return []

def previous_blend(current):
    folder, name = os.path.dirname(current), os.path.basename(current)

    # backup files (.blend1, .blend2) are previous versions of the current file
    for i in range(1, 10):
        backup = f"{name}{i}"
        if os.path.exists(os.path.join(folder, backup)):
            return os.path.join(folder, backup)

    files = blend_files(folder)
    if name in files:
        index = files.index(name)
        if index > 0:
            return os.path.join(folder, files[index - 1])
    return None

def next_blend(current):
    folder, name = os.path.dirname(current), os.path.basename(current)

    files = blend_files(folder)
    if name in files:
        index = files.index(name)
        if index < len(files) - 1:
            return os.path.join(folder, files[index + 1])
    return None

# ---------------------------------------------------------------------------
# auto save
# ---------------------------------------------------------------------------

autosave_state = {"last": 0.0}

def autosave_folder():
    prefs = get_prefs()
    folder = (prefs.autosave_folder if prefs else "") or ""
    folder = folder.strip()

    if folder:
        folder = bpy.path.abspath(folder)
    else:
        folder = os.path.join(tempfile.gettempdir(), "SmartTools_AutoSave")

    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = tempfile.gettempdir()

    return folder

def prune_autosaves(folder, limit):
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".blend")]
        files.sort(key=os.path.getmtime)

        while len(files) > limit:
            try:
                os.remove(files.pop(0))
            except OSError:
                break
    except OSError:
        pass

def do_autosave():
    prefs = get_prefs()
    if not prefs or not prefs.autosave_enabled or not prefs.activate_save_pie:
        return False

    try:
        if prefs.autosave_mode == 'SELF':
            if not bpy.data.filepath or is_backup(bpy.data.filepath):
                return False

            bpy.ops.wm.save_mainfile()
            label = os.path.basename(bpy.data.filepath)
        else:
            folder = autosave_folder()

            if bpy.data.filepath and not is_backup(bpy.data.filepath):
                stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
            else:
                stem = "untitled"

            stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            savepath = os.path.join(folder, f"{stem}_{stamp}.blend")
            number = 1

            while os.path.exists(savepath):
                number += 1
                savepath = os.path.join(folder, f"{stem}_{stamp}_{number}.blend")

            bpy.ops.wm.save_as_mainfile(filepath=savepath, copy=True)
            label = os.path.basename(savepath)

            prune_autosaves(folder, max(1, prefs.autosave_limit))

        if prefs.autosave_hud:
            hud_show(f"Auto Saved: {label}")

        print(f"{time.strftime('%H:%M:%S')} | Auto Saved: {label}")
        return True

    except Exception as e:
        print(f"SmartTools: Auto Save failed - {e}")
        return False

def sync_autosave_timer():
    """Start or stop the auto save timer to match the preferences."""
    prefs = get_prefs()
    active = bool(prefs and prefs.autosave_enabled and prefs.activate_save_pie)
    registered = bpy.app.timers.is_registered(autosave_timer)

    if active and not registered:
        autosave_state["last"] = time.time()
        bpy.app.timers.register(autosave_timer, first_interval=1.0)
    elif not active and registered:
        bpy.app.timers.unregister(autosave_timer)

def autosave_timer():
    prefs = get_prefs()
    if not prefs or not prefs.autosave_enabled or not prefs.activate_save_pie:
        return None

    interval = max(1, int(prefs.autosave_interval))

    if time.time() - autosave_state["last"] >= interval:
        autosave_state["last"] = time.time()
        do_autosave()

    return 1.0

@bpy.app.handlers.persistent
def load_pre_handler(*args):
    hud_clear()

@bpy.app.handlers.persistent
def undo_pre_handler(*args):
    prefs = get_prefs()
    if prefs and prefs.autosave_enabled and prefs.autosave_pre_undo:
        do_autosave()

@bpy.app.handlers.persistent
def redo_pre_handler(*args):
    prefs = get_prefs()
    if prefs and prefs.autosave_enabled and prefs.autosave_pre_redo:
        do_autosave()

@bpy.app.handlers.persistent
def load_post_handler(*args):
    hud_clear()
    sync_autosave_timer()

# ---------------------------------------------------------------------------
# fading HUD
# ---------------------------------------------------------------------------

hud_state = {"text": "", "start": 0.0, "duration": 1.6, "handle": None}

def hud_show(text, duration=1.6):
    prefs = get_prefs()
    if prefs is not None and not prefs.autosave_hud:
        return

    hud_clear()
    hud_state["text"] = text
    hud_state["start"] = time.time()
    hud_state["duration"] = duration

    try:
        hud_state["handle"] = bpy.types.SpaceView3D.draw_handler_add(
            hud_draw, (), 'WINDOW', 'POST_PIXEL')
    except Exception:
        hud_state["handle"] = None
        return

    if not bpy.app.timers.is_registered(hud_tick):
        bpy.app.timers.register(hud_tick, first_interval=0.05)

def hud_draw():
    try:
        region = bpy.context.region
        if region is None:
            return

        elapsed = time.time() - hud_state["start"]
        if elapsed >= hud_state["duration"]:
            return

        alpha = 1.0 - (elapsed / hud_state["duration"])
        font = 0
        text = hud_state["text"]

        blf.size(font, 15)
        blf.color(font, 1.0, 1.0, 1.0, alpha)

        width, height = blf.dimensions(font, text)
        blf.position(font, (region.width - width) / 2, region.height * 0.06, 0)
        blf.draw(font, text)

    except Exception:
        pass

def hud_tick():
    if time.time() - hud_state["start"] >= hud_state["duration"]:
        hud_clear()
        return None

    try:
        wm = bpy.context.window_manager
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            region.tag_redraw()
    except Exception:
        pass

    return 0.05

def hud_clear():
    handle = hud_state.get("handle")
    if handle is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
        except Exception:
            pass
        hud_state["handle"] = None

    if bpy.app.timers.is_registered(hud_tick):
        bpy.app.timers.unregister(hud_tick)

# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------

class M3_OT_new_file(bpy.types.Operator):
    bl_idname = "m3.new_file"
    bl_label = "Current file has unsaved changes. Start a new file anyway?"
    bl_description = "Start a new .blend file"

    def invoke(self, context, event):
        if is_dirty():
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        bpy.ops.wm.read_homefile(app_template="", load_ui=True)
        return {'FINISHED'}

class M3_OT_open_file(bpy.types.Operator):
    bl_idname = "m3.open_file"
    bl_label = "Open..."
    bl_description = "Open a .blend file"

    def execute(self, context):
        bpy.ops.wm.open_mainfile('INVOKE_DEFAULT')
        return {'FINISHED'}

class M3_OT_save_file(bpy.types.Operator):
    bl_idname = "m3.save_file"
    bl_label = "Save"
    bl_description = "Save the current .blend file"

    @classmethod
    def poll(cls, context):
        return not is_backup(bpy.data.filepath)

    @classmethod
    def description(cls, context, properties):
        if bpy.data.filepath:
            return f"Save {bpy.data.filepath}"
        return "Save unsaved file as..."

    def execute(self, context):
        if bpy.data.filepath:
            bpy.ops.wm.save_mainfile()
            self.report({'INFO'}, f'Saved "{os.path.basename(bpy.data.filepath)}"')
        else:
            bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')

        return {'FINISHED'}

class M3_OT_save_as(bpy.types.Operator):
    bl_idname = "m3.save_as"
    bl_label = "Save As..."
    bl_description = "Save the .blend file under a new name\nALT: Save a copy, keeping the current file open"

    copy: bpy.props.BoolProperty(name="Copy", default=False)

    @classmethod
    def poll(cls, context):
        return not is_backup(bpy.data.filepath)

    def invoke(self, context, event):
        self.copy = event.alt
        return self.execute(context)

    def execute(self, context):
        bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT', copy=self.copy)
        return {'FINISHED'}

class M3_OT_incremental_save(bpy.types.Operator):
    bl_idname = "m3.incremental_save"
    bl_label = "Incremental Save"
    bl_description = "Save to the next free _001, _002, ... version\nALT: Save a sub-increment"

    sub: bpy.props.BoolProperty(name="Sub-Increment", default=False)

    @classmethod
    def poll(cls, context):
        return not is_backup(bpy.data.filepath)

    def invoke(self, context, event):
        self.sub = event.alt
        return self.execute(context)

    def execute(self, context):
        if not bpy.data.filepath:
            bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
            return {'FINISHED'}

        primary, sub = get_incremented_paths(bpy.data.filepath)
        if not primary:
            self.report({'ERROR'}, "Could not increment the current file name")
            return {'CANCELLED'}

        savepath = next_free(sub if self.sub else primary)

        bpy.ops.wm.save_as_mainfile(filepath=savepath)
        add_path_to_recent_files(savepath)

        self.report({'INFO'}, f"Incrementally saved to {os.path.basename(savepath)}")
        return {'FINISHED'}

class M3_OT_revert_file(bpy.types.Operator):
    bl_idname = "m3.revert_file"
    bl_label = "Revert to the last saved state?"
    bl_description = "Revert the .blend file to its last saved state"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def invoke(self, context, event):
        if is_dirty():
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        bpy.ops.wm.revert_mainfile()
        return {'FINISHED'}

class M3_OT_open_most_recent(bpy.types.Operator):
    bl_idname = "m3.open_most_recent"
    bl_label = "Most Recent"
    bl_description = "Open the most recently used .blend file"

    def execute(self, context):
        for path in recent_files():
            if os.path.exists(path) and not path.endswith((".blend1", ".blend2")):
                bpy.ops.wm.open_mainfile(filepath=path, load_ui=True)
                add_path_to_recent_files(path)
                self.report({'INFO'}, f'Opened "{os.path.basename(path)}"')
                return {'FINISHED'}

        self.report({'WARNING'}, "No recent .blend file found")
        return {'CANCELLED'}

class M3_OT_open_folder(bpy.types.Operator):
    bl_idname = "m3.open_folder"
    bl_label = "Open Folder"
    bl_description = "Open the current .blend file's folder\nALT: Open the Auto Save folder"

    target: bpy.props.EnumProperty(
        name="Folder",
        items=[
            ('CURRENT', "Current", "The current .blend file's folder"),
            ('AUTOSAVE', "Auto Save", "The Auto Save folder"),
        ],
        default='CURRENT',
    )

    def invoke(self, context, event):
        if event.alt:
            target = 'AUTOSAVE'
        else:
            target = self.target

        if target == 'AUTOSAVE':
            folder = autosave_folder()
        elif bpy.data.filepath:
            folder = os.path.dirname(bpy.data.filepath)
        else:
            folder = autosave_folder()

        if not os.path.isdir(folder):
            self.report({'WARNING'}, f"Folder does not exist: {folder}")
            return {'CANCELLED'}

        bpy.ops.wm.path_open(filepath=folder)
        return {'FINISHED'}

class M3_OT_load_previous(bpy.types.Operator):
    bl_idname = "m3.load_previous"
    bl_label = "Load previous .blend in this folder?"
    bl_description = "Load the previous .blend file in the current folder\nALT: Load without the UI"

    filepath: bpy.props.StringProperty(name="Filepath")
    load_ui: bpy.props.BoolProperty(name="Load UI", default=True)

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def invoke(self, context, event):
        self.load_ui = not event.alt

        path = previous_blend(bpy.data.filepath)
        if not path:
            self.report({'WARNING'}, "Reached the first file in this folder")
            return {'CANCELLED'}

        self.filepath = path

        if is_dirty():
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        add_path_to_recent_files(self.filepath)
        bpy.ops.wm.open_mainfile(filepath=self.filepath, load_ui=self.load_ui)
        self.report({'INFO'}, f'Loaded "{os.path.basename(self.filepath)}"')
        return {'FINISHED'}

class M3_OT_load_next(bpy.types.Operator):
    bl_idname = "m3.load_next"
    bl_label = "Load next .blend in this folder?"
    bl_description = "Load the next .blend file in the current folder\nALT: Load without the UI"

    filepath: bpy.props.StringProperty(name="Filepath")
    load_ui: bpy.props.BoolProperty(name="Load UI", default=True)

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def invoke(self, context, event):
        self.load_ui = not event.alt

        path = next_blend(bpy.data.filepath)
        if not path:
            self.report({'WARNING'}, "Reached the last file in this folder")
            return {'CANCELLED'}

        self.filepath = path

        if is_dirty():
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        add_path_to_recent_files(self.filepath)
        bpy.ops.wm.open_mainfile(filepath=self.filepath, load_ui=self.load_ui)
        self.report({'INFO'}, f'Loaded "{os.path.basename(self.filepath)}"')
        return {'FINISHED'}

class M3_OT_autosave_toggle(bpy.types.Operator):
    bl_idname = "m3.autosave_toggle"
    bl_label = "Auto Save"
    bl_description = "Toggle time based Auto Saving"

    def execute(self, context):
        prefs = get_prefs()
        if not prefs:
            return {'CANCELLED'}

        prefs.autosave_enabled = not prefs.autosave_enabled
        self.report({'INFO'}, f"Auto Save {'enabled' if prefs.autosave_enabled else 'disabled'}")
        return {'FINISHED'}

class M3_OT_purge_orphans(bpy.types.Operator):
    bl_idname = "m3.purge_orphans"
    bl_label = "Purge Orphans"
    bl_description = "Purge unused data blocks\nALT: Purge recursively"

    def invoke(self, context, event):
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=event.alt)
        return {'FINISHED'}

class M3_OT_reload_libraries(bpy.types.Operator):
    bl_idname = "m3.reload_libraries"
    bl_label = "Reload Linked Libraries"
    bl_description = "Reload all linked libraries"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.libraries)

    def execute(self, context):
        for library in bpy.data.libraries:
            library.reload()

        count = len(bpy.data.libraries)
        self.report({'INFO'}, f"Reloaded {count} {'Library' if count == 1 else 'Libraries'}")
        return {'FINISHED'}

class M3_OT_clean_out_blend(bpy.types.Operator):
    bl_idname = "m3.clean_out_blend"
    bl_label = "Clean out the entire .blend file?"
    bl_description = "Remove all objects, materials, images and collections, then purge orphans"

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.objects or bpy.data.materials or bpy.data.images or bpy.data.collections)

    def draw(self, context):
        self.layout.label(text="This will remove everything in the current .blend file!", icon='ERROR')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        for mat in list(bpy.data.materials):
            bpy.data.materials.remove(mat, do_unlink=True)

        for img in list(bpy.data.images):
            bpy.data.images.remove(img, do_unlink=True)

        for collection in list(bpy.data.collections):
            bpy.data.collections.remove(collection, do_unlink=True)

        for _ in range(5):
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True)

        view = getattr(context, "space_data", None)
        if view and getattr(view, "type", None) == 'VIEW_3D' and view.local_view:
            bpy.ops.view3d.localview(frame_selected=False)

        self.report({'INFO'}, "Cleaned out .blend file")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
# pie
# ---------------------------------------------------------------------------

class M3_MT_save_pie(bpy.types.Menu):
    bl_idname = "M3_MT_save_pie"
    bl_label = "Save, Open, Append"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        star = "*" if is_dirty() else ""

        # 1 - LEFT
        pie.operator("m3.open_file", text="Open...", icon='FILE_FOLDER')

        # 2 - RIGHT
        pie.operator("m3.save_file", text=f"Save{star}", icon='FILE_TICK')

        # 3 - BOTTOM
        pie.operator("m3.save_as", text=f"Save As...{star}", icon='FILE_TICK')

        # 4 - TOP
        box = pie.row(align=False)
        box.ui_units_x = 38

        left = box.column(align=True)
        # Equal side widths keep the middle column over the pie's origin.
        left.ui_units_x = 13
        self.draw_left_column(context, left.box())

        column = box.column(align=True)
        column.ui_units_x = 12

        top = column.box()
        self.draw_center_column_top(context, top)

        if bpy.data.filepath:
            bottom = column.box()
            self.draw_center_column_bottom(bottom)

        right = box.column(align=True)
        right.ui_units_x = 13
        self.draw_right_column(context, right.box())

        # 5 - TOP - LEFT
        pie.separator()

        # 6 - TOP - RIGHT
        pie.separator()

        # 7 - BOTTOM - LEFT
        pie.operator("m3.new_file", text="New", icon='FILE_NEW')

        # 8 - BOTTOM - RIGHT
        pie.operator("m3.incremental_save", text=f"Incremental Save{star}", icon='FILE_REFRESH')

    def draw_left_column(self, context, layout):
        column = layout.column(align=True)

        row = column.split(factor=0.5, align=True)
        row.operator("m3.open_most_recent", text="Most Recent", icon='FILE_FOLDER')
        row.operator("wm.call_menu", text="All Recent", icon='FILE_FOLDER').name = "TOPBAR_MT_file_open_recent"

        row = column.split(factor=0.5, align=True)
        row.operator("m3.open_folder", text="Open Current", icon='FILE_FOLDER')
        row.operator("m3.open_folder", text="Open Temp", icon='FILE_FOLDER').target = 'AUTOSAVE'

        prefs = get_prefs()
        if not prefs:
            return

        row = column.split(factor=0.5, align=True)
        row.operator("m3.revert_file", text="Revert", icon='FILE_BACKUP')
        row.operator("m3.autosave_toggle", text="Auto Save",
                     icon='CHECKBOX_HLT' if prefs.autosave_enabled else 'CHECKBOX_DEHLT',
                     depress=prefs.autosave_enabled)

        row = column.split(factor=0.32, align=True)
        row.prop(prefs, "autosave_interval", text="")
        toggles = row.row(align=True)
        toggles.prop(prefs, "autosave_pre_undo", text="Undo")
        toggles.prop(prefs, "autosave_pre_redo", text="Redo")

    def draw_center_column_top(self, context, layout):
        column = layout.column(align=True)

        obj_import = "wm.obj_import" if op_exists("wm.obj_import") else "import_scene.obj"
        obj_export = "wm.obj_export" if op_exists("wm.obj_export") else "export_scene.obj"
        formats = [
            ("OBJ", obj_import, obj_export),
            ("FBX", "import_scene.fbx", "export_scene.fbx"),
            ("glTF", "import_scene.gltf", "export_scene.gltf"),
            ("USD", "wm.usd_import", "wm.usd_export"),
        ]

        for label, import_op, export_op in formats:
            if not op_exists(import_op) and not op_exists(export_op):
                continue

            row = column.split(factor=0.25, align=True)
            row.label(text=label)

            cells = row.split(factor=0.5, align=True)
            if op_exists(import_op):
                cells.operator(import_op, text="Import", icon='IMPORT')
            else:
                cells.separator()
            if op_exists(export_op):
                cell = cells.operator(export_op, text="Export", icon='EXPORT')
                apply_export_selection(cell, export_op, context)
            else:
                cells.separator()

    def draw_center_column_bottom(self, layout):
        row = layout.split(factor=0.5, align=True)
        row.scale_y = 1.2
        row.operator("m3.load_previous", text="Previous", icon='FILE_BACKUP')
        row.operator("m3.load_next", text="Next", icon='FILE_REFRESH')

    def draw_right_column(self, context, layout):
        column = layout.column(align=True)

        row = column.row(align=True)
        row.operator("wm.append", text="Append", icon='APPEND_BLEND')
        row.operator("wm.link", text="Link", icon='LINK_BLEND')
        row.operator("m3.purge_orphans", text="Purge", icon='ORPHAN_DATA')

        row = column.split(factor=0.5, align=True)
        row.operator("wm.call_menu", text="External Data", icon='PACKAGE').name = "TOPBAR_MT_file_external_data"
        row.operator("m3.clean_out_blend", text="Clean out .blend", icon='ERROR')

        if bpy.data.libraries:
            row = column.row(align=True)
            count = len(bpy.data.libraries)
            row.operator("m3.reload_libraries",
                         text=f"Reload {'Library' if count == 1 else 'Libraries'}",
                         icon='FILE_REFRESH')

classes = (
    M3_OT_new_file,
    M3_OT_open_file,
    M3_OT_save_file,
    M3_OT_save_as,
    M3_OT_incremental_save,
    M3_OT_revert_file,
    M3_OT_open_most_recent,
    M3_OT_open_folder,
    M3_OT_load_previous,
    M3_OT_load_next,
    M3_OT_autosave_toggle,
    M3_OT_purge_orphans,
    M3_OT_reload_libraries,
    M3_OT_clean_out_blend,
    M3_MT_save_pie,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    for handler_list, handler in (
        (bpy.app.handlers.load_pre, load_pre_handler),
        (bpy.app.handlers.load_post, load_post_handler),
        (bpy.app.handlers.undo_pre, undo_pre_handler),
        (bpy.app.handlers.redo_pre, redo_pre_handler),
    ):
        if handler not in handler_list:
            handler_list.append(handler)

    sync_autosave_timer()

def unregister():
    if bpy.app.timers.is_registered(autosave_timer):
        bpy.app.timers.unregister(autosave_timer)

    hud_clear()

    for handler_list, handler in (
        (bpy.app.handlers.load_pre, load_pre_handler),
        (bpy.app.handlers.load_post, load_post_handler),
        (bpy.app.handlers.undo_pre, undo_pre_handler),
        (bpy.app.handlers.redo_pre, redo_pre_handler),
    ):
        if handler in handler_list:
            handler_list.remove(handler)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
