from bpy_extras.io_utils import ImportHelper
from pathlib import Path
import time
import bpy
import os

bl_info = {
    "name": "Addon Installer|Script Runner",
    "description": "install save reload addons or run scripts just selecting a file",
    "author": "1C0D and from Amaral Krichman's addon",
    # multi selection file added for multi addons installation
    "version": (1, 1, 0),
    "blender": (2, 83, 0),
    "location": "Global/Text Editor",
    "warning": "",
    "wiki_url": "https://github.com/1C0D/Addon-Installer_Script-Runner_BlenderAddon/blob/master/Addon_Installer-Script_Runner.py",
    "category": "Development",
}

# ----------------------------- INSTALLER FROM FILES


class INSTALLER_OT_FileBrowser(bpy.types.Operator, ImportHelper):
    bl_idname = "installer.file_broswer"
    bl_label = "install addon run ext script from files"

    filter_glob: bpy.props.StringProperty(
        default='*.py;*.zip;*.txt',
        options={'HIDDEN'},
        subtype='FILE_PATH'  # to be sure to select a file
    )

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    # https://blender.stackexchange.com/questions/30678/bpy-file-browser-get-selected-file-names

    def execute(self, context):

        print('#'*50)
        p = self.filepath
        dirname = os.path.dirname(self.filepath)
        name = Path(p).stem

        # check if bl_info (Script or not)
        Script = True
        if Path(p).suffix == '.py' or Path(p).suffix == '.txt': 	 # == and not is!
            with open(p, 'r') as f:
                body = f.readlines()
                for line in body:
                    if 'bl_info' in line and not line.startswith("#"):
                        print('addon')
                        Script = False

        if Path(p).suffix == '.zip':
            Script = False

        if Script:
            print('not addon')
            exec(compile(open(p).read(), p, 'exec'))  # run script
            self.report({'INFO'}, "RUN SCRIPT: " + name)
            return {'FINISHED'}

        else:
            for f in self.files:
                p = os.path.join(dirname, f.name)
                name = Path(p).stem

                # disable
                try:
                    bpy.ops.preferences.addon_disable(module=name)
                    time.sleep(0.05)
                except RuntimeError:
                    self.report({'ERROR'}, "ADD-ON ERROR, see in the console")
                    return {'CANCELLED'}

                # remove/install
                bpy.ops.preferences.addon_remove(module=name)
                time.sleep(0.05)
                bpy.ops.preferences.addon_install(filepath=p)
                time.sleep(0.05)

                # enable
                try:
                    bpy.ops.preferences.addon_enable(module=name)
                    time.sleep(0.05)
                except RuntimeError:
                    self.report({'ERROR'}, "ADD-ON ERROR, see in the console")
                    return {'CANCELLED'}

                if len(self.files) < 2:
                    self.report({'INFO'}, "INSTALLED/RELOADED: " + name)
            if len(self.files) > 1:
                self.report({'INFO'}, "MULTI INSTALLED/RELOADED ")

            return {'FINISHED'}


def draw(self, context):

    layout = self.layout
    layout.separator(factor=1.0)
    layout.operator("installer.file_broswer",
                    text="Install-Reload Addon | Run ext Script", icon='FILEBROWSER')

# ----------------------------- INSTALLER FROM TEXT EDITOR


class INSTALLER_OT_TextEditor(bpy.types.Operator):

    bl_idname = "installer.text_editor"
    bl_label = "Install Addon from Text Editor"

    def execute(self, context):

        name = context.space_data.text.name

        text = bpy.context.space_data.text
        addon = False
        for line in text.lines:
            if 'bl_info' in line.body and not line.body.startswith("#"):
                addon = True
        if addon is False:
            self.report({'ERROR'}, "BL_INFO MISSING, NOT AN ADDON")
            return {'CANCELLED'}

        # if a same addon entered twice in text editor name is now addon.py.001
        if not name.endswith('.py'):
            parts = name.split(".")  # will be saved as addon.py
            if len(parts) > 1 and parts[-2] == 'py':
                parts.pop()
                name = ".".join(parts)
            else:
                name += '.py'  # .py missing in text editor name

        addon_path = bpy.utils.user_resource('SCRIPTS', "addons")
        full_path = os.path.join(addon_path, name)

        # save to blender addons folder
        bpy.ops.text.save_as(filepath=full_path)

        # disable
        try:
            bpy.ops.preferences.addon_disable(module=name[:-3])
            time.sleep(0.05)
        except RuntimeError:
            # error in the unregister/register part of the addon
            self.report({'ERROR'}, "ADD-ON ERROR, see in the console")
            return {'CANCELLED'}
        # refresh
        ar = context.screen.areas
        area = next((a for a in ar if a.type == 'PREFERENCES'), None)
        bpy.ops.preferences.addon_refresh({'area': area})
        time.sleep(0.05)
        # enable
        try:
            bpy.ops.preferences.addon_enable(module=name[:-3])
            time.sleep(0.05)
        except RuntimeError:
            self.report({'ERROR'}, "ADD-ON ERROR, see in the console")
            return {'CANCELLED'}

        self.report({'INFO'}, "Installed/Reloaded: " + name)

        return {'FINISHED'}


def text_addon_refresh(self, context):

    self .layout.separator(factor=1.0)
    self.layout.operator("installer.text_editor",
                         text="Install-Reload Addon from Text Editor", icon='COLLAPSEMENU')

    return {'FINISHED'}


classes = (INSTALLER_OT_FileBrowser, INSTALLER_OT_TextEditor)

addon_keymaps = []


def register():

    # classes
    for c in classes:
        bpy.utils.register_class(c)

    # menus entries
    bpy.types.TEXT_MT_text.append(draw)
    bpy.types.TOPBAR_MT_app.append(draw)
    bpy.types.TEXT_MT_text.append(text_addon_refresh)

    # key
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.user

    for k in kc.keymaps["Text"].keymap_items:
        if k.idname == "wm.call_menu" and k.properties.name == "SCREEN_MT_user_menu" and k.active:
            if k.properties.name == "SCREEN_MT_user_menu":
                return

    kc = wm.keyconfigs.addon
    km = kc.keymaps.new(name='Text', space_type='TEXT_EDITOR')
    kmi = km.keymap_items.new("wm.call_menu", "Q", "PRESS", ctrl=True)
    kmi.properties.name = "SCREEN_MT_user_menu"
    addon_keymaps.append((km, kmi))


def unregister():

    # key
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.user
    for k in kc.keymaps["Text"].keymap_items:
        if k.idname == "wm.call_menu" and k.properties.name == "SCREEN_MT_user_menu" and k.active:
            if k.properties.name == "SCREEN_MT_user_menu":
                try:
                    for km, kmi in addon_keymaps:
                        km.keymap_items.remove(kmi)
                except:
                    pass

    addon_keymaps.clear()

    # menus entries
    bpy.types.TEXT_MT_text.remove(draw)
    bpy.types.TOPBAR_MT_app.remove(draw)
    bpy.types.TEXT_MT_text.remove(text_addon_refresh)

    # classes
    for c in classes:
        bpy.utils.unregister_class(c)
