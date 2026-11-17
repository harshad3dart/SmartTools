import bpy
from mathutils import Vector

class M3_OT_smart_cam(bpy.types.Operator):
    bl_idname = "m3.smart_cam"
    bl_label = "Smart Cam"
    bl_description = "Create camera from view or set active camera"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        view = context.space_data
        if view.type != 'VIEW_3D':
            return {'CANCELLED'}
        r3d = view.region_3d

        # 1. If we have a selected camera, make it active and look through it
        sel_cams = [obj for obj in context.selected_objects if obj.type == 'CAMERA']
        if sel_cams:
            cam = sel_cams[0]
            context.scene.camera = cam
            r3d.view_perspective = 'CAMERA'
            return {'FINISHED'}

        cams_in_scene = [obj for obj in context.scene.objects if obj.type == 'CAMERA']

        # 2. If there are cameras in the scene, and we have an active camera
        if cams_in_scene and context.scene.camera:
            if r3d.view_perspective != 'CAMERA':
                # Switch to camera view
                r3d.view_perspective = 'CAMERA'
            else:
                # If already in camera view, align it to current view
                bpy.ops.view3d.camera_to_view()
            return {'FINISHED'}

        # 3. If no camera in scene, create a camera
        bpy.ops.object.camera_add(enter_editmode=False)
        new_cam = context.active_object
        context.scene.camera = new_cam
        
        # Match lens to viewport
        new_cam.data.lens = view.lens

        # Perfectly align camera framing to the viewport (this automatically switches to camera view)
        bpy.ops.view3d.camera_to_view()

        return {'FINISHED'}

class M3_OT_next_cam(bpy.types.Operator):
    bl_idname = "m3.next_cam"
    bl_label = "Next Cam"
    bl_description = "Switch to next camera"

    def execute(self, context):
        cams = [obj for obj in context.scene.objects if obj.type == 'CAMERA']
        if not cams:
            return {'CANCELLED'}
        
        active_cam = context.scene.camera
        if active_cam in cams:
            idx = cams.index(active_cam)
            next_idx = (idx + 1) % len(cams)
        else:
            next_idx = 0
            
        context.scene.camera = cams[next_idx]
        
        view = context.space_data
        if view.type == 'VIEW_3D':
            view.region_3d.view_perspective = 'CAMERA'
            
        return {'FINISHED'}

class M3_OT_prev_cam(bpy.types.Operator):
    bl_idname = "m3.prev_cam"
    bl_label = "Previous Cam"
    bl_description = "Switch to previous camera"

    def execute(self, context):
        cams = [obj for obj in context.scene.objects if obj.type == 'CAMERA']
        if not cams:
            return {'CANCELLED'}
        
        active_cam = context.scene.camera
        if active_cam in cams:
            idx = cams.index(active_cam)
            prev_idx = (idx - 1) % len(cams)
        else:
            prev_idx = 0
            
        context.scene.camera = cams[prev_idx]
        
        view = context.space_data
        if view.type == 'VIEW_3D':
            view.region_3d.view_perspective = 'CAMERA'
            
        return {'FINISHED'}

class M3_OT_toggle_persp(bpy.types.Operator):
    bl_idname = "m3.toggle_persp"
    bl_label = "Toggle Perspective"
    bl_description = "Toggle Perspective/Orthographic"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        r3d = context.space_data.region_3d
        if r3d.view_perspective == 'PERSP':
            r3d.view_perspective = 'ORTHO'
        elif r3d.view_perspective == 'ORTHO':
            r3d.view_perspective = 'PERSP'
        return {'FINISHED'}

class M3_OT_lock_to_active(bpy.types.Operator):
    bl_idname = "m3.lock_to_active"
    bl_label = "Lock to Active Object"
    bl_description = "Toggle locking view to the active object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        view = context.space_data
        obj = context.active_object
        
        if view.lock_object:
            # If already locked, unlock it
            view.lock_object = None
        elif obj:
            # Lock to active
            view.lock_object = obj
            
        return {'FINISHED'}

class M3_MT_views_pie(bpy.types.Menu):
    bl_idname = "M3_MT_views_pie"
    bl_label = "Views"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        view = context.space_data
        r3d = view.region_3d if view else None

        # 1. LEFT
        pie.operator("view3d.view_axis", text="Left", icon='TRIA_LEFT').type = 'LEFT'
        
        # 2. RIGHT
        pie.operator("view3d.view_axis", text="Right", icon='TRIA_RIGHT').type = 'RIGHT'
        
        # 3. BOTTOM (Front / Back)
        col = pie.column()
        col.operator("view3d.view_axis", text="Front", icon='VIEWZOOM').type = 'FRONT'
        col.operator("view3d.view_axis", text="Back", icon='VIEWZOOM').type = 'BACK'
        
        # 4. TOP (Top / Bottom)
        col = pie.column()
        col.operator("view3d.view_axis", text="Top", icon='TRIA_UP').type = 'TOP'
        col.operator("view3d.view_axis", text="Bottom", icon='TRIA_DOWN').type = 'BOTTOM'

        # 5. TOP-LEFT (Cameras)
        col = pie.column(align=True)
        col.operator("m3.smart_cam", text="Smart Cam", icon='CAMERA_DATA')
        
        row = col.row(align=True)
        row.operator("m3.prev_cam", text="", icon='TRIA_LEFT')
        if context.scene.camera:
            row.prop(context.scene, "camera", text="")
        else:
            row.label(text="No Camera")
        row.operator("m3.next_cam", text="", icon='TRIA_RIGHT')
        
        col.separator()
        if view:
            col.prop(view, "lock_camera", text="Lock Camera to View")

        # 6. TOP-RIGHT (Perspective/Orthographic and Lens)
        col = pie.column(align=True)
        if r3d:
            if r3d.view_perspective == 'PERSP':
                col.operator("m3.toggle_persp", text="Perspective", icon='VIEW_PERSPECTIVE')
            elif r3d.view_perspective == 'ORTHO':
                col.operator("m3.toggle_persp", text="Orthographic", icon='VIEW_ORTHO')
            else:
                col.label(text="Camera View", icon='CAMERA_DATA')
        if view:
            col.prop(view, "lens", text="Lens")

        # 7. BOTTOM-LEFT (Viewport Isolation & Focus)
        col = pie.column(align=True)
        col.operator("view3d.localview", text="Local View", icon='STICKY_UVS_ISOLATE')
        if view:
            lock_text = "Unlock Object" if view.lock_object else "Lock to Active"
            lock_icon = 'LOCKED' if view.lock_object else 'UNLOCKED'
            col.operator("m3.lock_to_active", text=lock_text, icon=lock_icon)
            
        col.operator("view3d.view_selected", text="Frame Selected", icon='VIEWZOOM')
        col.operator("view3d.view_center_cursor", text="Frame Cursor", icon='CURSOR')

        # 8. BOTTOM-RIGHT (Navigation Style)
        col = pie.column(align=True)
        # Handle Blender 5.1 preference paths safely
        prefs = context.preferences
        nav_prefs = getattr(prefs, "view", getattr(prefs, "inputs", None))
        
        if nav_prefs:
            if hasattr(nav_prefs, "view_rotate_method"):
                col.prop(nav_prefs, "view_rotate_method", expand=True)
            if hasattr(nav_prefs, "use_rotate_around_active"):
                col.prop(nav_prefs, "use_rotate_around_active", text="Orbit Selection")

classes = (
    M3_OT_smart_cam,
    M3_OT_next_cam,
    M3_OT_prev_cam,
    M3_OT_toggle_persp,
    M3_OT_lock_to_active,
    M3_MT_views_pie,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
