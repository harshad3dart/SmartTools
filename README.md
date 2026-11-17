# SmartTools

Blender extension for viewport focus, local view isolation, pie menus, cursor/origin alignment, and file-saving tools.

**Version:** 1.0.0 · **Tested with:** Blender 5.1.0

## Install

1. Download **SmartTools_v1_0.zip** from [Releases](https://github.com/harshad3dart/SmartTools/releases).
2. In Blender, open **Edit → Preferences → Add-ons → menu → Install from Disk**.
3. Select the ZIP without extracting it, then enable **SmartTools**.
4. Expand the add-on entry to access **General**, **Keymaps**, and **About**.

Use the release ZIP, not GitHub's automatic **Source code** archive.
Disable older SmartTools or M3 recreation installations before enabling this extension: they share operator identifiers.

## Features

- Focus selected objects and isolate objects in local view.
- Views Pie and camera navigation.
- Cursor & Origin Pie with alignment tools.
- Save Pie: save, save as, incremental versions, recent files, folder access, and previous/next file navigation.
- OBJ, FBX, glTF, and USD import/export, where the corresponding Blender operators are available.
- Append/link, external data tools, orphan purge, and file cleanup.
- Optional interval-based autosaving, save-copy/save-file modes, pre-undo/pre-redo saves, file retention, and a fading HUD.

## Default shortcuts

Shortcuts apply in the **3D View**.

| Shortcut | Action |
| --- | --- |
| F | Focus selection |
| Ctrl+F | Local view |
| Ctrl+Alt+F | Inverted local view |
| Page Down or Accent Grave | Views Pie |
| Page Up / Shift+Page Up | Next / previous camera |
| Shift+S | Cursor & Origin Pie |
| Ctrl+S | Save Pie |

Bindings can be changed in the add-on's **Keymaps** preferences.

## Saving notes

- Auto Save is **disabled by default**. Defaults when enabled: 30-second interval, 20 retained files, Save Copy mode.
- **Use a dedicated, otherwise empty autosave folder.** Retention currently prunes `.blend` files in that folder; do not point it at a project folder containing original work.
- Save File mode overwrites the current file. Keep independent backups.
- **Clean out .blend** removes scene data. Use only on files you intend to clear.

## Development

Run the headless regression suite with Blender 5.1:

```sh
blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py
```

The suite uses a disposable extension repository rather than modifying installed add-ons.
Release verification: **131 checks passed**, extension validation and build passed.

```sh
blender --factory-startup --command extension validate .
blender --factory-startup --command extension build --source-dir . --output-dir Builds
```

## License and reference

The extension manifest declares **GPL-2.0-or-later**.
See the [GNU GPL version 2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html).

The Save Pie workflow was inspired by [MACHIN3tools](https://machin3.io/MACHIN3tools/docs/pie_save/).
SmartTools is not affiliated with or endorsed by MACHIN3tools.
