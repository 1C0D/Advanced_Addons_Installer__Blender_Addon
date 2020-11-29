from bpy_extras.io_utils import ImportHelper
from pathlib import Path
import bpy
import sys
import os
import subprocess
import atexit
import tempfile
import io
import addon_utils
from time import ctime, sleep
from collections import Counter
from zipfile import ZipFile


bl_info = {
    "name": "Addon Installer|Script Runner",
    "description": "install save reload addons or run scripts just selecting a file",
    "author": "1C0D (inspired by Amaral Krichman's addon)",
    # multi selection file added for multi addons installation
    "version": (1, 3, 8),
    "blender": (2, 83, 0),
    "location": "top bar (blender icon)/Text Editor> text menu",
    "warning": "",
    "doc_url": "https://github.com/1C0D/Addon_Installer-Script_Runner-BlenderAddon",
    "category": "Development",
}

'''

-using a browser to directly apply things when selecting files
-you can reload an addon after modifications
-the addons is enabled so you don't need at all to open prefs...
-support multi-installation add-ons (you can mix .zip .py...)

-update option (browser option):
¤ prevents duppicates (same version but different name)
¤ greater version automatically detected 

-if update is unchecked:
¤ you can install duplicates, lower versions
¤ previous installed versions are automatically disabled

-Scripts:
¤ prevents from installing scripts(bl_info missing) in multi installations
¤ Run the script if selected alone

-clean all addons:
¤ dupplicates and lower versions
¤ remove fake-modules (happens when installing a script)

-install/reload addons directly from text editor(you can drag a file)
it will save in the addon folder and refresh after reload
you can do a copy to another location between of course

-location: in the text editor menu or in the top bar (blender icon)


from there you can install it in every quick favorites
-a quick favorite is added to the text editor 'Ctrl+Q'

-you can run a script in blender from an external file too

N.B you can check messages in the console after installation...

-you can install/reload an addon opened in the text editor too

-last installed addon: print a list in console of installed addons sorted by date 


'''


# ----------------------------- INSTALL/RELOAD FROM FILES

class INSTALLER_OT_FileBrowser(bpy.types.Operator, ImportHelper):
    bl_idname = "installer.file_broswer"
    bl_label = "install addon run ext script from files"

    filter_glob: bpy.props.StringProperty(
        default='*.py;*.zip',
        options={'HIDDEN'},
        subtype='FILE_PATH'  # to be sure to select a file
    )

    update_versions: bpy.props.BoolProperty(
        default=True, name="Update versions")

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    # https://blender.stackexchange.com/questions/30678/bpy-file-browser-get-selected-file-names

    def execute(self, context):

        print('*'*150)
        print('')
        print('ADDON INSTALLER|SCRIPT RUNNER')
        print('')
        print('*'*150)

        dirname = os.path.dirname(self.filepath)
        names = []
        addon_list = []
        script = False
        name = ''

        for f in self.files:
            p = os.path.join(dirname, f.name)
            name = Path(p).stem
            names.append(name)
            
            
            if not os.path.exists(p):
                self.report({'ERROR'}, f'Wrong Path {p}')
                print(f"===> you may have changed of directory after having selected a file from another directory\n your path was: {p}")
                return {'CANCELLED'}

            if Path(p).suffix == '.py':
                try:
                    f = open(p, "r", encoding='UTF-8')
                except OSError as ex:
                    print(f'===> Error opening file: {p}, {ex}')
                    continue

            elif Path(p).suffix == '.zip':
                with ZipFile(p, 'r') as zf:
                    init = [info.filename for info in zf.infolist(
                    ) if info.filename.split("/")[1] == '__init__.py']
                    for fic in init:
                        try:
                            f = io.TextIOWrapper(
                                zf.open(fic), encoding="utf-8")
                        except OSError as ex:
                            print(f'===> Error opening file: {p}, {ex}')
                            continue
                del zf
            try:
                with f:
                    lines = []
                    line_iter = iter(f)
                    l = ""
                    while not l.startswith("bl_info"):
                        try:
                            l = line_iter.readline()
                        except UnicodeDecodeError as ex:
                            print(f'===> Error reading file as UTF-8: {p}, {ex}')
                            continue

                        if len(l) == 0:
                            break

                    while l.rstrip():
                        lines.append(l)
                        try:
                            l = line_iter.readline()
                        except UnicodeDecodeError as ex:
                            print(f'===> Error reading file as UTF-8: {p}, {ex}')
                            continue

                    data = "".join(lines)

            except AttributeError:
                self.report({'WARNING'}, 'Select a File!')
                return {'CANCELLED'}

            del f

            import ast
            ModuleType = type(ast)
            try:
                ast_data = ast.parse(data, filename=p)
            except:
                print(f'===> Syntax error "ast.parse" can\'t read: {repr(p)}')
                import traceback
                traceback.print_exc()
                ast_data = None

            body_info = None

            if ast_data:
                for body in ast_data.body:
                    if body.__class__ == ast.Assign:
                        if len(body.targets) == 1:
                            if getattr(body.targets[0], "id", "") == "bl_info":
                                body_info = body
                                break

            # ADDON(S) INSTALLATION/RELOAD
            if body_info:  # ADDONS
                try:
                    mod = ModuleType(name)
                    mod.bl_info = ast.literal_eval(body.value)
                    data_mod_name = mod.bl_info['name']
                    data_mod_version = mod.bl_info.get('version',(0,0,0))
                    data_mod_category = mod.bl_info['category']

                except:
                    print(f'===> AST error parsing bl_info for: {name}')
                    import traceback
                    traceback.print_exc()
                    raise
                    continue

                addon_list.append(
                    [data_mod_category, data_mod_name, data_mod_version, name, p])

            else:
                # SCRIPT EXECUTION
                script = True

                if len(self.files) > 1:
                    print('_'*100)
                    print('')
                    print(f'"{name}" NOT INSTALLED! (no bl-info)')
                    print('_'*100)
                    print('')

                    continue

                print('_'*100)
                print('')
                print(f'SCRIPT EXECUTION {name}')
                print('_'*100)
                print('')

                try:
                    # run script #change to a with
                    exec(compile(open(p).read(), p, 'exec'))

                except:
                    print(f'===> SCRIPT ERROR in "{name}"')
                    raise
                    return {'CANCELLED'}

        # not in the precedent loop to not repeat same operations for each file
        greatest = []
        lower_versions = []
        not_installed = []
        to_remove = []

        if self.update_versions:

            # same "category: name" occurences in selected addons
            dict = Counter(word for i, j, *_ in addon_list for word in [
                           (i, j)])

            counter = [(word, count) for word,
                       count in dict.most_common()]  # dupplicates

            # greatest / lower versions among selected (when multi install maybe several versions of a same addon...)
            greater = ()
            for u, v in counter:
                greater = ()
                for i, j, k, l, m in addon_list:
                    if (i, j) == u:
                        lower_versions.append([i, j, k, l, m])
                        if not greater:
                            greater = k
                            greatest.append([i, j, k, l, m])
                        elif greater and k > greater:
                            greater = k
                            greatest.pop()
                            greatest.append([i, j, k, l, m])  # greatest

            for g in greatest:
                if g in lower_versions:
                    lower_versions.remove(g)

            # don't install < versions
            not_installed = [g for g in greatest for addon in addon_utils.modules()
                             if (g[0] == addon.bl_info['category']
                                 and g[1] == addon.bl_info['name']
                                 and g[2] < addon.bl_info['version'])]

            for n in not_installed:
                greatest.remove(n)

            # remove <= installed version
            to_remove = [addon for addon in addon_utils.modules() for g in greatest
                         if (addon.bl_info['category'] == g[0]
                             and addon.bl_info['name'] == g[1]
                             and (addon.bl_info['version'] < g[2]
                                  or (addon.bl_info['version'] == g[2]
                                      and addon.__name__ != g[3])))]

            for removed in to_remove:
                try:
                    bpy.ops.preferences.addon_remove(module=removed.__name__)
                    print(f'===> "{removed.__name__}" REMOVED (LOWER VERSION)')
                except:
                    print(f'===> couldn\'t remove "{removed.__name__}"')
                    self.report({'ERROR'}, f"COULDN'T REMOVE {name}",  see in Console)
                    return {'CANCELLED'}

            if not greatest and not script:
                print('')
                print(
                    f'NOT INSTALLED (file_name|version|name): {[(i[3]+".py",i[1],i[2]) for i in addon_list]}')
                print('')

                self.report(
                    {'INFO'}, f'{len(addon_list)} IGNORED (lower version) ')

            elif not greatest and script:

                self.report({'INFO'}, f'RUN SCRIPT: "{name}"')

        else:

            if len(self.files) > 1:
                self.report({'ERROR'}, "SELECT ONLY 1 FILE (Update unchecked")
                return {'FINISHED'}

            else:

                my_list = [addon for addon in addon_utils.modules() for a in addon_list
                           if (addon.bl_info['name'] == a[1]
                               and addon.bl_info['category'] == a[0])]
                for a in my_list:
                    bpy.ops.preferences.addon_disable(module=a.__name__)

                greatest = addon_list

            if not greatest and script:

                self.report({'INFO'}, f'RUN SCRIPT: "{name}"')

        for great in greatest:
            name1 = great[3]
            version = great[3]
            p = great[4]

            print('_'*100)
            print('')
            print(f'INSTALL/RELOAD: {name1}, version: {version}')
            print('_'*100)
            print('')

            # disable
            try:
                bpy.ops.preferences.addon_disable(module=name1)

            except:
                print('===> couldn\'t disable' + name1)
                self.report({'ERROR'}, f"COULDN'T DISABLE {name1}, see in Console")
                return {'CANCELLED'}

            # remove/install
            try:
                bpy.ops.preferences.addon_remove(module=name1)

            except:
                print('===> couldn\'t remove' + name1)
                self.report({'ERROR'}, f"COULDN'T REMOVE {name1}, see in Console")
                return {'CANCELLED'}

            try:
                bpy.ops.preferences.addon_install(filepath=p)

            except:
                print('===> couldn\'t install' + name1)
                self.report({'ERROR'}, f"COULDN'T INSTALL {name1}, see in Console")
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
                    bpy.ops.preferences.addon_enable(module=name1)

            except:
                print('===> couldn\'t addon_enable ' + name1)
                self.report({'ERROR'}, f"COULDN'T ENABLE {name1}, see in Console")
                return {'CANCELLED'}

            lower_versions.extend(not_installed)

            print('')
            print(
                f'REMOVED (file_name|version|name): {[(i.__name__+".py",i.bl_info["name"],i.bl_info["version"]) for i in to_remove]}')
            print('')
            print(
                f'NOT INSTALLED (file_name|version|name): {[(i[3]+".py",i[1],i[2]) for i in lower_versions]}')
            print('')
            print(
                f'INSTALLED/RELOADED (file_name|version|name): {[(i[3]+".py",i[1],i[2]) for i in greatest]}')
            print('')

            self.report(
                {'INFO'}, f'{len(to_remove)} REMOVED, {len(greatest)} INSTALLED, {len(lower_versions)} IGNORED (lower version) ')

            if len(self.files) > 1:
                self.report({'INFO'}, "MULTI INSTALLED/RELOADED ")

            else:
                # if not script:
                self.report({'INFO'}, "INSTALLED/RELOADED: " + name1)

        return {'FINISHED'}

    def draw(self, context):

        layout = self.layout
        layout.label(text="Select addon(s) and confirm")
        text = "Update version(s) or Reload" if self.update_versions else "Any version or Reload"
        layout.prop(self, "update_versions", text=text)
        layout.label(text="")
        layout.label(text='Tips:')
        layout.label(text='  -select a SCRIPT to RUN it')
        layout.label(text='  -you can double click on 1 file')
        layout.label(text='  -quick favorite in text editor |Ctrl+Q|')
        layout.label(text='')
        layout.label(text='')
        layout.label(text='')
        layout.label(text='')
        layout.label(text='            Special thanks to Amaral Krichman')


# ----------------------------- INSTALL/RELOAD FROM TEXT EDITOR

class INSTALLER_OT_TextEditor(bpy.types.Operator):

    bl_idname = "installer.text_editor"
    bl_label = "Install Addon from Text Editor"

    def execute(self, context):

        print('*'*150)
        print('')
        print('INSTALLER|RELOAD FROM TEXT EDITOR')
        print('')
        print('*'*150)

        name = context.space_data.text.name

        text = bpy.context.space_data.text
        addon = False
        for line in text.lines:
            if line.body.startswith("bl_info"):
                addon = True
        if addon is False:
            print(f'===> {name} has no bl_info, not an addon')
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

        except:
            print('===> couldn\'t disable' + name)
            self.report({'ERROR'}, f"COULDN'T DISABLE {name}, see in Console")
            return {'CANCELLED'}

        # refresh
        ar = context.screen.areas
        area = next((a for a in ar if a.type == 'PREFERENCES'), None)
        bpy.ops.preferences.addon_refresh({'area': area})

        # enable
        try:
            bpy.ops.preferences.addon_enable(module=name[:-3])

        except:
            print('===> couldn\'t addon_enable ' + name)
            self.report({'ERROR'}, f"COULDN'T ENABLE {name}, see in Console")
            return {'CANCELLED'}

        self.report({'INFO'}, "Installed/Reloaded: " + name)

        return {'FINISHED'}


# -----------------------------ADDONS CLEANER

class ADDON_OT_Cleaner(bpy.types.Operator):
    bl_idname = "addon.cleaner"
    bl_label = "addon cleaner"

    def execute(self, context):

        # search dupplicates addon and old versions in all addons to keep only last update
        my_list = [(addon.bl_info.get('category',("User")), addon.bl_info['name'], addon.bl_info.get('version',(0,0,0)), addon.__name__)
                   for addon in addon_utils.modules()]  # tuple with 4 values

        dict = Counter(word for i, j, k, l in my_list for word in [
                       (i, j)])  # to check "category: name" occurences

        counter = [(word, count) for word,
                   count in dict.most_common() if count > 1]  # dupplicates

        # let's get the greatest version
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
                    elif greater and k > greater:
                        greater = k
                        greatest.pop()
                        greatest.append([i, j, k, l])

        print('version', version)
        print('greatest', greatest)
        for g in greatest:
            if g in version:
                version.remove(g)
        print('version', version)

        for v in version:
            bpy.ops.preferences.addon_remove(module=v[3])

        for g in greatest:
            bpy.ops.preferences.addon_enable(module=g[3])

        print('')
        print(
            f'REMOVED VERSIONS (category|name|version|file_name|date): {version}')
        print('')
        print(
            f'CURRENT VERSIONS (category|name|version|file_name|date): {greatest}')
        print('')
        self.report(
            {'INFO'}, f'{len(version)} LOWER VERSION(S) REMOVED {len(greatest)} ENABLED')

        return {'FINISHED'}


class ADDON_OT_fake_remove(bpy.types.Operator):
    bl_idname = "addon.fake_remove"
    bl_label = "fake modules remove"

    def execute(self, context):

        addon_path = bpy.utils.user_resource('SCRIPTS', "addons")
        names = []

        # !listdir give some name.* not paths...
        for path in os.listdir(addon_path):
            mod_path = os.path.join(addon_path, path)
            if os.path.isfile(mod_path) and Path(mod_path).suffix == '.py':
                mod_name = Path(mod_path).stem

                import ast
                ModuleType = type(ast)
                try:
                    file_mod = open(mod_path, "r", encoding='UTF-8')
                except OSError as ex:
                    print("Error opening file:", mod_path, ex)

                with file_mod:
                    lines = []
                    data = []
                    line_iter = iter(file_mod)
                    l = ""
                    while not l.startswith("bl_info"):
                        try:
                            l = line_iter.readline()
                        except UnicodeDecodeError as ex:
                            print("Error reading file as UTF-8:", mod_path, ex)
                            continue

                        if len(l) == 0:
                            break
                    while l.rstrip():
                        lines.append(l)
                        try:
                            l = line_iter.readline()
                        except UnicodeDecodeError as ex:
                            print("Error reading file as UTF-8:", mod_path, ex)
                            continue

                        data = "".join(lines)

                del file_mod

                try:
                    ast_data = ast.parse(data, filename=mod_path)
                except:
                    print('===> FAKE-MODULE REMOVED: ',  mod_name)
                    names.append(mod_name)
                    os.remove(mod_path)

        self.report(
            {'INFO'}, f'{len(names)} FAKES MODULE REMOVED, see names in console')

        return {'FINISHED'}


class ADDON_OT_last_installed(bpy.types.Operator):
    bl_idname = "addon.print_last_installed"
    bl_label = "Last installed addons (see in console)"

    def execute(self, context):

        print("#"*20, "sorted last installed addons")

        installed = []

        for mod_name in bpy.context.preferences.addons.keys():
            try:
                mod = sys.modules[mod_name]
                installed.append(
                    (mod.__name__, mod.bl_info['category'], mod.bl_info['name'], mod.bl_info['version'], mod.__time__))
            except KeyError:
                pass
        last_installed = sorted(installed, key=lambda x: (x[4]))

        last_installed_date = [(i, j, k, l, ctime(m))
                               for i, j, k, l, m in last_installed]

        for last in last_installed_date:
            print(last)
        print("")
        print("File name | category | name | version | date")

        return {'FINISHED'}
        
        
def launch():
    """
    launch the blender process
    """    
    binary_path = bpy.app.binary_path #blender.exe path 
    file_path = bpy.data.filepath #saved .blend file
    # check if the file is saved
    if file_path: 
        if bpy.data.is_dirty: #some changes since the last save
            bpy.ops.wm.save_as_mainfile(filepath=file_path)
            # launch a background process
        subprocess.Popen([binary_path, file_path])
    else: #if no save, save as temp
        file_path=os.path.join(tempfile.gettempdir(),"temp.blend")
        bpy.ops.wm.save_as_mainfile(filepath=file_path)
        subprocess.Popen([binary_path, file_path])

class RESTART_OT_blender(bpy.types.Operator):
    bl_idname = "blender.restart"
    bl_label = "Restart"

    def execute(self, context):
        #what is reloaded after the exit
        atexit.register(launch)
        # sleep for a sec
        sleep(1)
        # # quit blender
        exit()
        return {'FINISHED'}        


# ----------------------------------------Menus

class ADDON_MT_management_menu(bpy.types.Menu):
    bl_label = 'addon management'

    def draw(self, context):
        layout = self.layout
        layout.operator("installer.file_broswer",
                        text="Install-Reload Addon | Run ext Script", icon='FILEBROWSER')
        layout.operator(ADDON_OT_Cleaner.bl_idname,
                        text="Clean all addons lower versions")
        layout.operator(ADDON_OT_fake_remove.bl_idname,
                        text="Remove fake modules")
        layout.operator(ADDON_OT_last_installed.bl_idname)
        layout.operator(RESTART_OT_blender.bl_idname,
                        text="Restart Blender")


def draw(self, context):

    layout = self.layout
    layout.separator(factor=1.0)
    layout.menu('ADDON_MT_management_menu', text='Add-ons management')


def draw1(self, context):

    self .layout.separator(factor=1.0)
    self.layout.operator("installer.file_broswer",
                         text="Install-Reload Addon | Run ext Script", icon='FILEBROWSER')
    self.layout.operator("installer.text_editor",
                         text="Install-Reload Addon from Text Editor", icon='COLLAPSEMENU')


classes = (INSTALLER_OT_FileBrowser, INSTALLER_OT_TextEditor,
           ADDON_OT_Cleaner, ADDON_OT_fake_remove, ADDON_MT_management_menu, ADDON_OT_last_installed, RESTART_OT_blender)

addon_keymaps = []


def register():

    # classes
    for c in classes:
        bpy.utils.register_class(c)

    # menus entries

    bpy.types.TEXT_MT_text.append(draw1)
    bpy.types.TOPBAR_MT_app.append(draw)

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
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)

    addon_keymaps.clear()

    # menus entries
    bpy.types.TEXT_MT_text.remove(draw1)
    bpy.types.TOPBAR_MT_app.remove(draw)

    # classes
    for c in classes:
        bpy.utils.unregister_class(c)
