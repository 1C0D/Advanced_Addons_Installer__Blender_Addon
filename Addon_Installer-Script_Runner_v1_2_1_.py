from bpy_extras.io_utils import ImportHelper
from pathlib import Path
import time
import bpy
import os
import addon_utils
from collections import Counter
from zipfile import ZipFile

'''
if no bl_info running like a script




'''
bl_info = {
    "name": "Addon Installer|Script Runner",
    "description": "install save reload addons or run scripts just selecting a file",
    "author": "1C0D and from Amaral Krichman's addon",
    # multi selection file added for multi addons installation
    "version": (1, 2, 2),
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

    clean_doubles_update_versions: bpy.props.BoolProperty(default=True)

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    # https://blender.stackexchange.com/questions/30678/bpy-file-browser-get-selected-file-names

    def execute(self, context):
        
        print('*'*200)
        print('')
        print('ADDON INSTALLER|SCRIPT RUNNER')
        print('')     

        dirname = os.path.dirname(self.filepath)
        names = []

        for f in self.files:

            p = os.path.join(dirname, f.name)
            name = Path(p).stem
            names.append(name)
            
            # check if bl_info (Script or not)
            Script = True
            if Path(p).suffix == '.py' or Path(p).suffix == '.txt': 	 # == and not is!
                with open(p, 'r', encoding="utf-8") as f:
                    body = f.readlines()
                    for line in body:
                        if line.startswith("bl_info"):
                            Script = False
                            break

            if Path(p).suffix == '.zip':
                Script = False

            if Script:
                if len(self.files) > 1:
                    print('_'*100)
                    print('')
                    print('"'+ name +'" NOT INSTALLED! (no bl-info)' )
                    print('_'*100)
                    print('')                
                    self.report({'ERROR'}, "BL_INFO MISSING, "+ name +" IS NOT AN ADDON")
                    continue
                    
                print('_'*100)
                print('')
                print('SCRIPT EXECUTION' + name)
                print('_'*100)
                print('')
                exec(compile(open(p).read(), p, 'exec'))  # run script
                self.report({'INFO'}, "RUN SCRIPT: " + name)
                return {'FINISHED'}
            
            print('_'*100)
            print('')
            print('ADDON(S) INSTALLATION/RELOAD ' + name)
            print('_'*100)
            print('')

            try:
                bpy.ops.preferences.addon_disable(module=name)

            except RuntimeError:
                print(
                    '#################couldn\'t addon_disable '+ name)
                self.report(
                    {'ERROR'}, "CAN'T DISABLE ADDON, see in the console")
                return {'CANCELLED'}

            # remove/install
            try:
                bpy.ops.preferences.addon_remove(module=name)

            except RuntimeError:
                print(
                    '#################couldn\'t addon_remove ' +name)
                self.report(
                    {'ERROR'}, "CAN'T REMOVE ADDON, see in the console")
                return {'CANCELLED'}

            try:
                bpy.ops.preferences.addon_install(filepath=p)

            except RuntimeError:
                print(
                    '#################couldn\'t addon_install ' +name)
                self.report(
                    {'ERROR'}, "CAN'T INSTALL ADDON, see in the console")
                return {'CANCELLED'}

            # enable
            try:
                if Path(p).suffix == '.zip':
                    
                    # changing the name of a zip, the name of the first subfolder is different. when doing enable, name is the name of the subfolder...
                    with ZipFile(p, 'r') as f:
                        names = [info.filename for info in f.infolist()
                                 if info.is_dir()]
          
                    namezip = names[0].split("/")[0]

                    bpy.ops.preferences.addon_enable(module=namezip)
                else:
                    bpy.ops.preferences.addon_enable(module=name)

            except RuntimeError:
                print(
                    '#################couldn\'t addon_enable ' +name)
                self.report(
                    {'ERROR'}, "CAN'T ENABLE ADDON, see in the console")
                return {'CANCELLED'}

            if len(self.files) < 2:
                self.report({'INFO'}, "INSTALLED/RELOADED: " + name)

        if len(self.files) > 1:
            self.report({'INFO'}, "MULTI INSTALLED/RELOADED ")

        # search dupplicates addon and old versions in all addons to keep only last update
        if self.clean_doubles_update_versions:
            my_list = [(addon.bl_info['category'], addon.bl_info['name'], addon.bl_info['version'], addon.__name__)
                       for addon in addon_utils.modules()]  # tuple with 4 values

            dict = Counter(word for i, j, k, l in my_list for word in [
                           (i, j)])  # to check "category: name" occurences

            counter = [(word, count) for word,
                       count in dict.most_common() if count > 1]  # dupplicates
                       
            #e.g:[['Development', ' A', (1, 8, 1), 'Afghf'], ['Development', ' A', (1, 8, 3), 'A1'], ['Development', ' A', (1, 8, 2), 'A2121'],['Development', ' A', (1, 8, 3), 'A4541']] 
            
            #let's put the greatest version apart 
            version = []
            greatest = []
            greater = None
            for u, v in counter:
                greater = None
                for i, j, k, l in my_list:
                    if (i, j) == u:
                        version.append([i, j, k, l])
                        if not greater:
                            greater = k
                            greatest.append([i, j, k, l])                               
                        elif k > greater:
                            if greatest:
                                greatest.pop()
                                greatest.append([i, j, k, l])
                            else:
                                greatest.append([i, j, k, l])                           
            
            for g in greatest:
                if g in version:
                    version.remove(g)

            # for addon in addon_utils.modules():
            for u, v, w, z in my_list:
                for i, j, k, l in version:
                    # if (addon.bl_info['category'], addon.bl_info['name'], addon.bl_info['version']) == (i, j, k):
                    if (u, v, w) == (i, j, k):
                        bpy.ops.preferences.addon_remove(module=l)


            print('')
            print(
                f'NOT INSTALLED VERSIONS (category|name|version|file_name): {version}')
            print('')
            print(
                f'INSTALLED (category|name|version|file_name): {greatest}')
            print('')


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
            if line.body.startswith("bl_info"):
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

        except RuntimeError:
            print(
                '###################################################couldn\'t addon_disable')
            self.report({'ERROR'}, "CAN'T DISABLE ADDON, see in the console")
            return {'CANCELLED'}
        # refresh
        ar = context.screen.areas
        area = next((a for a in ar if a.type == 'PREFERENCES'), None)
        bpy.ops.preferences.addon_refresh({'area': area})

        # enable
        try:
            bpy.ops.preferences.addon_enable(module=name[:-3])

        except RuntimeError:
            print(
                '###################################################couldn\'t addon_enable')
            self.report({'ERROR'}, "CAN'T ENABLE ADDON, see in the console")
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
    kc = wm.keyconfigs.addon    
    km = kc.keymaps.new(name='Text', space_type='TEXT_EDITOR')
    kmi = km.keymap_items.new("wm.call_menu", "Q", "PRESS", ctrl=True)
    kmi.properties.name = "SCREEN_MT_user_menu"
    addon_keymaps.append((km, kmi))


def unregister():

    # key
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
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
