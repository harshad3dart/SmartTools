import bpy

# Global history stack for local view modifiers and hidden objects
# Each entry is a dict: {"hidden_objects": [name1, ...], "toggled_modifiers": [(obj_name, mod_name, state), ...]}
m3_local_view_history = []

class M3_OT_focus(bpy.types.Operator):
    bl_idname = "m3.focus"
    bl_label = "Focus on Selection"
    bl_description = "Focus on selection, ignoring spatial modifiers (Mirror, Array, Solidify, Bevel)"
    bl_options = {'REGISTER', 'UNDO'}

    local_view: bpy.props.BoolProperty(name="Local View", default=False)
    view_selected: bpy.props.BoolProperty(name="View Selected", default=True)
    ignore_mirrors: bpy.props.BoolProperty(name="Ignore Mirrors", default=True)
    ignore_arrays: bpy.props.BoolProperty(name="Ignore Arrays", default=True)
    
    def draw(self, context):
        layout = self.layout
        col = layout.column()
        
        # Draw the checkboxes exactly as seen in the MACHIN3tools redo panel
        col.prop(self, "local_view")
        col.prop(self, "view_selected")
        col.prop(self, "ignore_mirrors")
        col.prop(self, "ignore_arrays")

    def execute(self, context):
        if not context.selected_objects:
            bpy.ops.view3d.view_all()
            return {'FINISHED'}

        # Execute local view if checked in the redo panel
        if self.local_view:
            bpy.ops.view3d.localview()
            return {'FINISHED'}

        modifiers_state = []
        if context.mode == 'OBJECT':
            for obj in context.selected_objects:
                for mod in obj.modifiers:
                    if (mod.type == 'MIRROR' and self.ignore_mirrors) or (mod.type == 'ARRAY' and self.ignore_arrays) or (mod.type in {'SOLIDIFY', 'BEVEL'}):
                        if mod.show_viewport:
                            modifiers_state.append((mod, True))
                            mod.show_viewport = False

        if self.view_selected:
            bpy.ops.view3d.view_selected()
            
            # Add padding to limit zoom in perspective view
            if context.space_data.type == 'VIEW_3D' and context.space_data.region_3d.is_perspective:
                context.space_data.region_3d.view_distance *= 1.2

        for mod, state in modifiers_state:
            mod.show_viewport = state

        return {'FINISHED'}

class M3_OT_local_view(bpy.types.Operator):
    bl_idname = "m3.local_view"
    bl_label = "Local View"
    bl_description = "Multi-level isolation stack. Stepping down disables spatial modifiers, stepping up restores them."
    bl_options = {'REGISTER', 'UNDO'}

    invert: bpy.props.BoolProperty(
        name="Invert",
        default=False
    )
    
    ignore_modifiers: bpy.props.BoolProperty(
        name="Ignore Modifiers",
        description="Temporarily disable spatial modifiers during local view",
        default=True
    )
    
    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "ignore_modifiers")

    def execute(self, context):
        global m3_local_view_history
        view = context.space_data

        if view.type != 'VIEW_3D':
            return {'CANCELLED'}

        is_local_view = view.local_view is not None
        selected_objs = context.selected_objects
        
        # Invert logic
        if self.invert:
            bpy.ops.object.select_all(action='INVERT')
            selected_objs = context.selected_objects
            # If we inverted, we are explicitly stepping IN

        # Determine step direction
        visible_objs = [obj for obj in context.visible_objects if obj.type not in {'LIGHT', 'CAMERA'}]
        
        stepping_out = False
        if not selected_objs and not self.invert:
            stepping_out = True
        elif is_local_view and len(selected_objs) >= len(visible_objs) and not self.invert:
            stepping_out = True

        if stepping_out:
            if m3_local_view_history:
                last_level = m3_local_view_history.pop()
                
                # 1. Restore hidden objects in this local view depth
                for obj_name in last_level.get("hidden_objects", []):
                    if obj_name in bpy.data.objects:
                        bpy.data.objects[obj_name].local_view_set(view, True)
                        
                # 2. Restore modifiers
                for obj_name, mod_name, state in last_level.get("toggled_modifiers", []):
                    if obj_name in bpy.data.objects:
                        obj = bpy.data.objects[obj_name]
                        if mod_name in obj.modifiers:
                            obj.modifiers[mod_name].show_viewport = state
                
                # 3. If we've popped the last level, exit native local view entirely
                if not m3_local_view_history and view.local_view:
                    bpy.ops.view3d.localview(frame_selected=False)
            else:
                # Fallback: if history is empty but we are in local view, exit.
                if view.local_view:
                    bpy.ops.view3d.localview(frame_selected=False)
        else:
            # We are stepping IN
            level_data = {"hidden_objects": [], "toggled_modifiers": []}
            
            # Disable and record spatial modifiers on the selection if requested
            if self.ignore_modifiers:
                for obj in selected_objs:
                    for mod in obj.modifiers:
                        if mod.type in {'MIRROR', 'ARRAY', 'SOLIDIFY', 'BEVEL'} and mod.show_viewport:
                            level_data["toggled_modifiers"].append((obj.name, mod.name, True))
                            mod.show_viewport = False

            if not is_local_view:
                # Base level: enter native local view
                bpy.ops.view3d.localview(frame_selected=False)
            else:
                # Deeper level: hide unselected objects manually from this local view
                unselected_visible = [obj for obj in context.visible_objects if not obj.select_get()]
                for obj in unselected_visible:
                    obj.local_view_set(view, False)
                    level_data["hidden_objects"].append(obj.name)
            
            m3_local_view_history.append(level_data)
            
            # Frame the selection
            bpy.ops.view3d.view_selected()
            
            # Add padding to limit zoom in perspective view
            if view.type == 'VIEW_3D' and view.region_3d.is_perspective:
                view.region_3d.view_distance *= 1.2

        return {'FINISHED'}

classes = (
    M3_OT_focus,
    M3_OT_local_view,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
