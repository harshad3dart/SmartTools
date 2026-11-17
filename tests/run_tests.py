"""
Headless test suite for the SmartTools Save Pie.

Run:
    blender-5.1 --background --factory-startup --python tests/run_tests.py

Results are written to tests/test_results.json so the exit code does not
matter. A disposable extension repository is registered only in this process's
factory preferences. Installed extensions and saved preferences are never touched.
"""

import bpy
import ast
import importlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import time
import traceback

DEV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_MODULE = "smarttools_tests"
MODULE = f"bl_ext.{REPO_MODULE}.SmartToolAddon"
RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results.json")

results = []


def check(name, condition, detail=""):
    ok = bool(condition)
    results.append({"name": name, "ok": ok, "detail": str(detail)})
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  -> {detail}"))


def section(title):
    print(f"\n=== {title} ===")


def addon_module(name):
    return importlib.import_module(f"{MODULE}.{name}")


SKIP_DIRS = {"__pycache__", ".git", "tests", "Builds"}
test_repository = None
test_directory = None


def install():
    """Enable a private copy; never inspect, move, or replace a real install."""
    global test_repository, test_directory
    if not bpy.app.background or "--factory-startup" not in sys.argv:
        raise RuntimeError("Tests require --background --factory-startup")
    repositories = bpy.context.preferences.extensions.repos
    if any(repo.module == REPO_MODULE for repo in repositories):
        raise RuntimeError(f"Test repository already exists: {REPO_MODULE}")
    test_directory = tempfile.TemporaryDirectory(prefix="smarttools_extensions_")
    shutil.copytree(
        DEV_DIR, os.path.join(test_directory.name, "SmartToolAddon"),
        ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.zip"),
    )
    test_repository = repositories.new(
        name="SmartTools disposable tests",
        module=REPO_MODULE,
        custom_directory=test_directory.name,
    )
    if os.path.normcase(os.path.realpath(test_repository.directory)) != os.path.normcase(
            os.path.realpath(test_directory.name)):
        raise RuntimeError("Blender did not use the disposable repository directory")
    bpy.ops.preferences.addon_enable(module=MODULE)


def uninstall():
    global test_repository, test_directory
    try:
        if test_repository is not None:
            if MODULE in bpy.context.preferences.addons:
                bpy.ops.preferences.addon_disable(module=MODULE)
            bpy.context.preferences.extensions.repos.remove(test_repository)
            test_repository = None
    finally:
        if test_directory is not None:
            test_directory.cleanup()
            test_directory = None


# ---------------------------------------------------------------------------
# pie draw probe
# ---------------------------------------------------------------------------

class FakeOperatorProperties:
    def __init__(self, idname):
        self._idname = idname
        category, operator = idname.split(".", 1)
        rna = getattr(getattr(bpy.ops, category), operator).get_rna_type()
        # UILayout.operator() returns RNA properties with Blender defaults, not
        # an empty object. In particular, export selection flags default false.
        for prop in rna.properties:
            if prop.type == 'BOOLEAN' and not prop.is_array:
                setattr(self, prop.identifier, prop.default)


# Every props object handed out by FakeLayout.operator(), so tests can assert
# on the values the draw code sets on them.
OPERATOR_RESULTS = []


class FakeLayout:
    """Records every UI call so the pie draw code can be exercised headless."""

    def __init__(self, log=None, path="root", kind="root", kwargs=None):
        self.log = log if log is not None else []
        self.path = path
        self.children = []
        self.kind = kind
        self.kwargs = kwargs or {}
        self.align = self.kwargs.get("align", False)
        self.alignment = 'EXPAND'
        self.ui_units_x = 0.0
        self.ui_units_y = 0.0
        self.scale_x = 1.0
        self.scale_y = 1.0

    def _child(self, kind, **kwargs):
        entry = f"{self.path}.{kind}({kwargs})" if kwargs else f"{self.path}.{kind}()"
        return self._record(entry, kind, kwargs)

    def _record(self, entry, kind="", kwargs=None):
        self.log.append(entry)
        child = FakeLayout(self.log, entry, kind, kwargs)
        self.children.append(child)
        return child

    def box(self, **kwargs):
        return self._child("box", **kwargs)

    def column(self, **kwargs):
        return self._child("column", **kwargs)

    def row(self, **kwargs):
        return self._child("row", **kwargs)

    def split(self, **kwargs):
        return self._child("split", **kwargs)

    def separator(self, **kwargs):
        self._child("separator", **kwargs)

    def menu_pie(self):
        return self

    def label(self, text="", icon='NONE', **kwargs):
        self._record(f"{self.path}.label({text!r}, icon={icon})")
        check_icon(icon)

    def operator(self, idname, text="", text_ctxt="", translate=True, icon='NONE',
                 emboss=True, depress=False, icon_value=0, search_weight=0.0, **extra):
        # Mirrors UILayout.operator(): anything else is a TypeError in Blender.
        if extra:
            raise AssertionError(
                f"UILayout.operator() got invalid keyword argument(s): {sorted(extra)}")

        self._record(f"{self.path}.operator({idname}, {text!r}, icon={icon})",
                     "operator", {"idname": idname, "text": text})
        check_icon(icon)
        check_operator(idname)
        props = FakeOperatorProperties(idname)
        props._kwargs = {"text": text, "icon": icon, "depress": depress}
        OPERATOR_RESULTS.append(props)
        return props

    def prop(self, data, prop, **kwargs):
        self.log.append(f"{self.path}.prop({prop})")
        if not hasattr(data, prop):
            raise AssertionError(f"{type(data).__name__} has no property {prop!r}")


VALID_ICONS = set(
    bpy.types.UILayout.bl_rna.functions['prop'].parameters['icon'].enum_items.keys()
)


def check_icon(icon):
    if icon not in VALID_ICONS:
        raise AssertionError(f"unknown icon {icon!r}")


def check_operator(idname):
    try:
        mod, name = idname.split(".", 1)
    except ValueError:
        raise AssertionError(f"malformed operator idname {idname!r}")

    op_module = getattr(bpy.ops, mod, None)
    if op_module is None or not hasattr(op_module, name):
        raise AssertionError(f"unknown operator {idname!r}")


def draw_pie(layout):
    pie_save = addon_module("pie_save")
    menu = pie_save.M3_MT_save_pie
    OPERATOR_RESULTS.clear()

    # draw() reads self.layout and calls the menu's own helpers, so borrow
    # those onto a plain stand-in (instantiating an RNA class is not allowed).
    class StandIn:
        pass

    for name, value in vars(menu).items():
        if name != "draw" and callable(value):
            setattr(StandIn, name, value)

    stand_in = StandIn()
    stand_in.layout = layout
    menu.draw(stand_in, bpy.context)
    return layout


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_registration():
    section("registration")

    check("addon enabled", MODULE in bpy.context.preferences.addons)
    check("menu class", hasattr(bpy.types, "M3_MT_save_pie"))

    for op in ("new_file", "open_file", "save_file", "save_as", "incremental_save",
               "revert_file", "open_most_recent", "open_folder", "load_previous",
               "load_next", "autosave_toggle", "purge_orphans", "reload_libraries",
               "clean_out_blend"):
        check(f"operator m3.{op}",
              hasattr(bpy.types, f"M3_OT_{op}") and hasattr(bpy.ops.m3, op))


def test_preferences():
    section("preferences")

    prefs = bpy.context.preferences.addons[MODULE].preferences

    check("activate_save_pie default", prefs.activate_save_pie is True)
    check("autosave_enabled default", prefs.autosave_enabled is False)
    check("autosave_interval default", prefs.autosave_interval == 30, prefs.autosave_interval)
    check("autosave_limit default", prefs.autosave_limit == 20, prefs.autosave_limit)
    check("autosave_mode default", prefs.autosave_mode == 'EXTERNAL', prefs.autosave_mode)
    check("autosave_pre_undo default", prefs.autosave_pre_undo is True)
    check("autosave_pre_redo default", prefs.autosave_pre_redo is False)
    check("autosave_hud default", prefs.autosave_hud is True)
    check("autosave_folder default empty", prefs.autosave_folder == "")
    check("existing tools still default on",
          prefs.activate_focus and prefs.activate_views_pie and prefs.activate_cursor_origin_pie)


def test_keymap():
    section("keymap")

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.get('3D View')
    check("3D View addon keymap exists", km is not None)

    if not km:
        return

    matches = [kmi for kmi in km.keymap_items
               if kmi.idname == "wm.call_menu_pie"
               and getattr(kmi.properties, "name", None) == "M3_MT_save_pie"]

    check("save pie keymap item found", len(matches) == 1, len(matches))

    if matches:
        kmi = matches[0]
        check("shortcut is CTRL+S",
              kmi.type == 'S' and kmi.ctrl and not kmi.alt and not kmi.shift,
              f"type={kmi.type} ctrl={kmi.ctrl}")

    # the other pies must still be bound
    for menu in ("M3_MT_views_pie", "M3_MT_cursor_origin_pie"):
        found = [kmi for kmi in km.keymap_items
                 if kmi.idname == "wm.call_menu_pie"
                 and getattr(kmi.properties, "name", None) == menu]
        check(f"{menu} still bound", len(found) >= 1, len(found))


def test_timer_sync():
    section("auto save timer")

    pie_save = addon_module("pie_save")
    prefs = bpy.context.preferences.addons[MODULE].preferences
    timer = pie_save.autosave_timer

    check("timer off by default", not bpy.app.timers.is_registered(timer))

    prefs.autosave_enabled = True
    check("timer on after enabling", bpy.app.timers.is_registered(timer))

    prefs.autosave_enabled = False
    check("timer off after disabling", not bpy.app.timers.is_registered(timer))

    prefs.autosave_enabled = True
    prefs.autosave_interval = 999
    check("timer registered after interval change", bpy.app.timers.is_registered(timer))
    prefs.autosave_enabled = False
    check("timer off again", not bpy.app.timers.is_registered(timer))


def test_incremental_paths():
    section("incremental path helpers")

    pie_save = addon_module("pie_save")

    primary, sub = pie_save.get_incremented_paths("/tmp/scene.blend")
    check("first increment", os.path.basename(primary) == "scene_001.blend", primary)
    check("first sub increment", os.path.basename(sub) == "scene_01.blend", sub)

    primary, sub = pie_save.get_incremented_paths("/tmp/scene_007.blend")
    check("padded increment", os.path.basename(primary) == "scene_008.blend", primary)

    tmp = tempfile.mkdtemp()
    try:
        existing = os.path.join(tmp, "scene_001.blend")
        open(existing, "w").close()
        bumped = pie_save.next_free(existing)
        check("next_free bumps", os.path.basename(bumped) == "scene_002.blend", bumped)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    check("is_backup detects .blend1", pie_save.is_backup("/tmp/scene.blend1"))
    check("is_backup rejects .blend", not pie_save.is_backup("/tmp/scene.blend"))


def test_blend_navigation():
    section("load previous / next")

    pie_save = addon_module("pie_save")

    tmp = tempfile.mkdtemp()
    try:
        for name in ("a.blend", "b.blend", "c.blend"):
            open(os.path.join(tmp, name), "w").close()

        current = os.path.join(tmp, "b.blend")
        check("previous", pie_save.previous_blend(current) == os.path.join(tmp, "a.blend"),
              pie_save.previous_blend(current))
        check("next", pie_save.next_blend(current) == os.path.join(tmp, "c.blend"),
              pie_save.next_blend(current))
        check("previous at start", pie_save.previous_blend(os.path.join(tmp, "a.blend")) is None)
        check("next at end", pie_save.next_blend(os.path.join(tmp, "c.blend")) is None)

        backup = os.path.join(tmp, "b.blend1")
        open(backup, "w").close()
        check("backup counts as previous", pie_save.previous_blend(current) == backup,
              pie_save.previous_blend(current))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_save_ops(tmp):
    section("save operators")

    prefs = bpy.context.preferences.addons[MODULE].preferences
    prefs.autosave_hud = False

    blend = os.path.join(tmp, "scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    check("saved base file", bpy.data.filepath == blend, bpy.data.filepath)

    bpy.ops.m3.save_file()
    check("save keeps path", bpy.data.filepath == blend, bpy.data.filepath)

    bpy.ops.m3.incremental_save()
    check("incremental 001", os.path.exists(os.path.join(tmp, "scene_001.blend")))
    check("incremental becomes current",
          bpy.data.filepath.endswith("scene_001.blend"), bpy.data.filepath)

    bpy.ops.m3.incremental_save()
    check("incremental 002", os.path.exists(os.path.join(tmp, "scene_002.blend")))

    bpy.ops.m3.incremental_save(sub=True)
    check("sub incremental", os.path.exists(os.path.join(tmp, "scene_002_01.blend")),
          sorted(os.listdir(tmp)))


def test_autosave(tmp):
    section("auto save")

    pie_save = addon_module("pie_save")
    prefs = bpy.context.preferences.addons[MODULE].preferences

    folder = os.path.join(tmp, "autosave")
    prefs.autosave_folder = folder
    prefs.autosave_mode = 'EXTERNAL'
    prefs.autosave_limit = 20
    prefs.autosave_hud = False
    prefs.autosave_enabled = True

    current_before = bpy.data.filepath
    check("external autosave runs", pie_save.do_autosave())

    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    check("autosave created a copy", len(files) == 1, files)
    check("autosave filename is windows safe", files and ":" not in files[0], files)
    check("current file untouched by copy",
          bpy.data.filepath == current_before, f"{bpy.data.filepath} vs {current_before}")

    pie_save.do_autosave()
    files = sorted(os.listdir(folder))
    check("second autosave creates another file", len(files) == 2, files)

    prefs.autosave_limit = 1
    pie_save.do_autosave()
    files = sorted(os.listdir(folder))
    check("file limit enforced", len(files) == 1, files)

    # pre undo / pre redo
    prefs.autosave_limit = 20
    before = len(os.listdir(folder))
    prefs.autosave_pre_undo = True
    pie_save.undo_pre_handler()
    check("pre-undo saves", len(os.listdir(folder)) > before,
          os.listdir(folder) if os.path.isdir(folder) else "missing")

    before = len(os.listdir(folder))
    prefs.autosave_pre_redo = False
    pie_save.redo_pre_handler()
    check("pre-redo skipped when disabled", len(os.listdir(folder)) == before)

    # self saving
    prefs.autosave_mode = 'SELF'
    current = bpy.data.filepath
    mtime_before = os.path.getmtime(current)
    time.sleep(0.05)

    check("self autosave runs", pie_save.do_autosave())
    check("self save keeps the current file", bpy.data.filepath == current, bpy.data.filepath)
    check("self save wrote to disk", os.path.getmtime(current) > mtime_before,
          f"{os.path.getmtime(current)} vs {mtime_before}")

    prefs.autosave_mode = 'EXTERNAL'

    # HUD must never blow up, even without a window
    prefs.autosave_hud = True
    try:
        pie_save.hud_show("test")
        pie_save.hud_clear()
        check("hud does not raise", True)
    except Exception:
        check("hud does not raise", False, traceback.format_exc())


def test_pie_draw():
    section("pie draw")

    pie_save = addon_module("pie_save")
    real_is_dirty = pie_save.is_dirty

    # --- clean file -------------------------------------------------------
    pie_save.is_dirty = lambda: False

    layout = FakeLayout()
    try:
        draw_pie(layout)
        check("pie draws without error", True)
    except Exception:
        check("pie draws without error", False, traceback.format_exc())
        return
    finally:
        pie_save.is_dirty = real_is_dirty

    check("pie has 8 slots", len(layout.children) == 8, [c.path for c in layout.children])
    expected_slots = (
        ("LEFT", "m3.open_file"),
        ("RIGHT", "m3.save_file"),
        ("BOTTOM", "m3.save_as"),
        ("TOP", "panel"),
        ("TOP LEFT", "separator"),
        ("TOP RIGHT", "separator"),
        ("BOTTOM LEFT", "m3.new_file"),
        ("BOTTOM RIGHT", "m3.incremental_save"),
    )
    actual_slots = [
        child.kwargs.get("idname") if child.kind == "operator"
        else "separator" if child.kind == "separator"
        else "panel" if child.kind in {"row", "column", "box"} else child.kind
        for child in layout.children
    ]
    check("exact Blender pie slot order",
          actual_slots == [value for _, value in expected_slots], actual_slots)
    for index, (position, expected) in enumerate(expected_slots):
        actual = actual_slots[index] if index < len(actual_slots) else None
        check(f"{position} slot is {expected}", actual == expected, actual)

    joined = "\n".join(layout.log)
    for expected in ("m3.open_file", "m3.save_as", "m3.save_file", "m3.new_file",
                     "m3.incremental_save", "wm.call_menu", "m3.open_most_recent",
                     "m3.revert_file", "m3.autosave_toggle", "m3.load_previous",
                     "m3.load_next", "wm.append", "wm.link", "m3.purge_orphans",
                     "m3.clean_out_blend", "autosave_interval", "autosave_pre_undo"):
        check(f"pie contains {expected}", expected in joined)

    ids = [props._idname for props in OPERATOR_RESULTS]
    check("OBJ import uses wm.obj_import", ids.count("wm.obj_import") == 1, ids)
    check("OBJ export uses wm.obj_export", ids.count("wm.obj_export") == 1, ids)
    check("no legacy OBJ operators",
          not {"import_scene.obj", "export_scene.obj"}.intersection(ids), ids)
    check("no STL rows or operators drawn", "stl" not in joined.lower(), joined)
    # Check definitions too: unavailable operators must not hide stale STL rows.
    strings = [
        node.value.lower()
        for node in ast.walk(ast.parse(inspect.getsource(pie_save)))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    stl_strings = [
        value for value in strings
        if value == "stl" or value.endswith(".stl") or value.startswith("wm.stl_")
    ]
    check("no STL format or operator definitions", not stl_strings, stl_strings)
    if len(layout.children) > 3:
        panel = layout.children[3]
        check("TOP panel is a compact unaligned row",
              panel.kind == "row" and not panel.align and panel.ui_units_x == 38,
              f"{panel.kind}, align={panel.align}, width={panel.ui_units_x}")
        columns = [child for child in panel.children if child.kind == "column"]
        check("TOP panel uses symmetric 13/12/13 column widths",
              [child.ui_units_x for child in columns] == [13, 12, 13],
              [child.ui_units_x for child in columns])
        check("TOP panel contains import/export controls",
              any("wm.obj_import" in line for line in layout.log
                  if line.startswith(panel.path)), panel.path)

    navigation = FakeLayout()
    pie_save.M3_MT_save_pie.draw_center_column_bottom(None, navigation)
    check("Previous and Next use equal-width halves",
          navigation.children[0].kind == "split"
          and navigation.children[0].kwargs.get("factor") == 0.5)

    labels = [l for l in layout.log if ".label(" in l or ".operator(" in l]
    check("clean file shows no star", not [l for l in labels if "*" in l],
          [l for l in labels if "*" in l])

    # --- dirty file -------------------------------------------------------
    # Blender only tracks is_dirty in an interactive session, so the flag is
    # substituted here to prove the unsaved indicator is wired up correctly.
    pie_save.is_dirty = lambda: True

    layout = FakeLayout()
    try:
        draw_pie(layout)
        labels = [l for l in layout.log if ".label(" in l or ".operator(" in l]

        check("dirty file shows star on Save",
              any("Save*" in l for l in labels), [l for l in labels if "Save" in l])
        check("dirty file shows star on Save As",
              any("Save As...*" in l for l in labels),
              [l for l in labels if "Save As" in l])
        check("dirty file shows star on Incremental",
              any("Incremental Save*" in l for l in labels),
              [l for l in labels if "Incremental" in l])
        check("dirty file star count is 3", sum(l.count("*") for l in labels) == 3,
              [l for l in labels if "*" in l])
    except Exception:
        check("dirty file star labels", False, traceback.format_exc())
    finally:
        pie_save.is_dirty = real_is_dirty


EXPORT_PREFIXES = ("export_scene.", "export_mesh.", "wm.usd_export", "wm.obj_export")
EXPORT_SELECTION_PROPS = ("use_selection", "export_selected_objects", "selected_objects_only",
                          "selected_only")


def test_export_selection():
    section("export selection props")

    # --- nothing selected -------------------------------------------------
    bpy.ops.object.select_all(action='DESELECT')
    check("nothing selected", not bpy.context.selected_objects)

    layout = FakeLayout()
    draw_pie(layout)
    exports = [p for p in OPERATOR_RESULTS if p._idname.startswith(EXPORT_PREFIXES)]
    check("an export button was drawn", len(exports) >= 1, len(exports))
    obj_exports = [p for p in exports if p._idname == "wm.obj_export"]
    check("modern OBJ exporter checked without selection", len(obj_exports) == 1)
    for props in obj_exports:
        check("OBJ export_selected_objects false without selection",
              getattr(props, "export_selected_objects", None) is False, vars(props))

    flagged = [p._idname for p in exports
               if any(getattr(p, prop, False) for prop in EXPORT_SELECTION_PROPS)]
    check("no selection -> no exporter restricted", not flagged, flagged)
    for props in exports:
        category, operator = props._idname.split(".", 1)
        rna = getattr(getattr(bpy.ops, category), operator).get_rna_type()
        expected = next((name for name in EXPORT_SELECTION_PROPS
                         if name in rna.properties), None)
        if expected is not None:
            check(f"{props._idname} export includes all without selection",
                  getattr(props, expected, None) is False,
                  f"want {expected}=False, have {vars(props)}")

    # --- something selected ----------------------------------------------
    if not bpy.context.selected_objects:
        bpy.ops.mesh.primitive_cube_add()
    check("object selected", bool(bpy.context.selected_objects))

    layout = FakeLayout()
    draw_pie(layout)
    exports = [p for p in OPERATOR_RESULTS if p._idname.startswith(EXPORT_PREFIXES)]
    obj_exports = [p for p in exports if p._idname == "wm.obj_export"]
    check("modern OBJ exporter checked with selection", len(obj_exports) == 1)
    for props in obj_exports:
        check("OBJ export_selected_objects true with selection",
              getattr(props, "export_selected_objects", None) is True, vars(props))

    restricted = 0
    for props in exports:
        category, operator = props._idname.split(".", 1)
        rna = getattr(getattr(bpy.ops, category), operator).get_rna_type()
        expected = None
        if rna:
            expected = next((name for name in EXPORT_SELECTION_PROPS
                             if name in rna.properties), None)
        if expected is None:
            continue

        check(f"{props._idname} export limited to selection",
              getattr(props, expected, False) is True,
              f"want {expected}, have {vars(props)}")
        restricted += 1

    check("at least one exporter takes a selection flag", restricted >= 1, restricted)


def test_toggle_operator():
    section("toggle operator")

    prefs = bpy.context.preferences.addons[MODULE].preferences
    prefs.autosave_enabled = False

    bpy.ops.m3.autosave_toggle()
    check("toggle enables", prefs.autosave_enabled is True)

    bpy.ops.m3.autosave_toggle()
    check("toggle disables", prefs.autosave_enabled is False)


def test_disable_enable():
    section("disable / re-enable")

    pie_save = addon_module("pie_save")

    bpy.ops.preferences.addon_disable(module=MODULE)
    check("menu removed on disable", not hasattr(bpy.types, "M3_MT_save_pie"))
    check("timer removed on disable", not bpy.app.timers.is_registered(pie_save.autosave_timer))
    check("handlers removed on disable",
          pie_save.undo_pre_handler not in bpy.app.handlers.undo_pre)

    bpy.ops.preferences.addon_enable(module=MODULE)
    check("menu restored on enable", hasattr(bpy.types, "M3_MT_save_pie"))
    check("handlers restored on enable",
          pie_save.undo_pre_handler in bpy.app.handlers.undo_pre)


def main():
    tmp = tempfile.mkdtemp(prefix="smarttools_test_")

    try:
        install()
        test_registration()
        test_preferences()
        test_keymap()
        test_timer_sync()
        test_incremental_paths()
        test_blend_navigation()
        test_save_ops(tmp)
        test_autosave(tmp)
        test_pie_draw()
        test_export_selection()
        test_toggle_operator()
        test_disable_enable()
    except Exception:
        traceback.print_exc()
        results.append({"name": "suite crashed", "ok": False, "detail": traceback.format_exc()})
    finally:
        try:
            uninstall()
        except Exception:
            traceback.print_exc()
            check("disposable repository cleanup", False, traceback.format_exc())

        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "failed": len(failed), "results": results}, f, indent=2)

    print(f"\n{passed}/{len(results)} checks passed")
    for r in failed:
        print(f"  FAILED: {r['name']} -> {r['detail']}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
