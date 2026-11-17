import bpy
import bmesh

class M3_OT_origin_to_selection(bpy.types.Operator):
    bl_idname = "m3.origin_to_selection"
    bl_label = "Origin to Selection / Active"
    bl_description = "Set object origin to selected geometry, or to the active object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            # Save current cursor location
            saved_cursor_loc = context.scene.cursor.location.copy()
            
            # Snap cursor to selected
            bpy.ops.view3d.snap_cursor_to_selected()
            
            # Change to object mode to set origin to cursor
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
            
            # Restore to edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Restore cursor location
            context.scene.cursor.location = saved_cursor_loc
            
        elif context.mode == 'OBJECT':
            # Origin to Active
            active_obj = context.active_object
            if active_obj:
                saved_cursor_loc = context.scene.cursor.location.copy()
                context.scene.cursor.location = active_obj.location
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
                context.scene.cursor.location = saved_cursor_loc
            else:
                bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
                
        return {'FINISHED'}

class M3_OT_cursor_to_selection_aligned(bpy.types.Operator):
    bl_idname = "m3.cursor_to_selection_aligned"
    bl_label = "Cursor to Selection (Aligned)"
    bl_description = "Snap 3D cursor to selection and align rotation\nALT: Snap location without rotating"
    bl_options = {'REGISTER', 'UNDO'}

    use_rotation: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        self.use_rotation = not event.alt
        return self.execute(context)

    def execute(self, context):
        # 1. Snap location
        bpy.ops.view3d.snap_cursor_to_selected()
        
        # 2. Handle rotation
        if self.use_rotation:
            if context.mode == 'EDIT_MESH':
                try:
                    # Create a temporary custom orientation from selection
                    bpy.ops.transform.create_orientation(name="TempAlign", use=True, overwrite=True)
                    
                    # Get the matrix of the new active orientation
                    orient_slot = context.scene.transform_orientation_slots[0]
                    if orient_slot.custom_orientation and orient_slot.custom_orientation.name == "TempAlign":
                        matrix = orient_slot.custom_orientation.matrix.copy()
                        
                        # Apply the rotation to the 3D Cursor
                        context.scene.cursor.rotation_mode = 'XYZ'
                        context.scene.cursor.rotation_euler = matrix.to_euler()
                        
                    # Delete the temporary orientation
                    bpy.ops.transform.delete_orientation()
                except Exception as e:
                    print(f"M3 Recreation: Could not align cursor rotation. {e}")
        else:
            # Reset cursor rotation to 0,0,0 if ALT is held
            context.scene.cursor.rotation_euler = (0.0, 0.0, 0.0)

        return {'FINISHED'}

class M3_MT_cursor_origin_pie(bpy.types.Menu):
    bl_idname = "M3_MT_cursor_origin_pie"
    bl_label = "Cursor and Origin"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        # Dynamic text based on mode
        sel_text = "to Selected"
        sel_icon = 'CURSOR'
        face_icon = 'FACESEL'
        
        if context.mode == 'EDIT_MESH':
            mode = context.tool_settings.mesh_select_mode
            if mode[0]:
                sel_text = "to Vert"
                face_icon = 'VERTEXSEL'
            elif mode[1]:
                sel_text = "to Edge"
                face_icon = 'EDGESEL'
            elif mode[2]:
                sel_text = "to Face"
                face_icon = 'FACESEL'

        # 1. Left (Cursor to Selection)
        pie.operator("m3.cursor_to_selection_aligned", text=sel_text, icon='CURSOR')
        
        # 2. Right (Selection to Cursor)
        pie.operator("view3d.snap_selected_to_cursor", text="to Cursor", icon='RESTRICT_SELECT_OFF').use_offset = False
        
        # 3. Bottom (Object Origin)
        col = pie.column(align=True)
        
        # Center align the label
        label_row = col.row()
        label_row.alignment = 'CENTER'
        label_row.label(text="Object Origin")
        
        row = col.row(align=True)
        row.operator("object.origin_set", text="to Cursor", icon='DOT').type = 'ORIGIN_CURSOR'
        
        if context.mode == 'OBJECT':
            row.operator("object.origin_set", text="to Geometry", icon='MESH_DATA').type = 'ORIGIN_GEOMETRY'
            # Second row for to Active (Centered and narrower)
            row2 = col.row()
            row2.alignment = 'CENTER'
            row2.operator("m3.origin_to_selection", text="to Active", icon='PIVOT_ACTIVE')
        elif context.mode == 'EDIT_MESH':
            row.operator("m3.origin_to_selection", text=sel_text, icon=face_icon)
        else:
            row.operator("object.origin_set", text="to Geometry", icon='MESH_DATA').type = 'ORIGIN_GEOMETRY'

        # 4. Top (Separator)
        pie.separator()

        # 5. Top-Left (Cursor to Origin)
        pie.operator("view3d.snap_cursor_to_center", text="to Origin", icon='PIVOT_CURSOR')
        
        # 6. Top-Right (Selection to Cursor Offset)
        pie.operator("view3d.snap_selected_to_cursor", text="to Cursor, Offset", icon='RESTRICT_SELECT_OFF').use_offset = True

        # 7. Bottom-Left
        pie.separator()
        
        # 8. Bottom-Right
        pie.separator()

classes = (
    M3_OT_origin_to_selection,
    M3_OT_cursor_to_selection_aligned,
    M3_MT_cursor_origin_pie,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
