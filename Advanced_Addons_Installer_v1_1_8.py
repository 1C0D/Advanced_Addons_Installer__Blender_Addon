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
from time import ctime  # , sleep
from collections import Counter
from zipfile import ZipFile
import shutil

bl_info = {
    "name": "Advanced Addons Installer",
    "description": "install save reload addons or run scripts",
    "author": "1C0D",
    "version": (1, 1, 8),
    "blender": (2, 90, 0),
    "location": "top bar (blender icon)/Text Editor> text menu",
    "warning": "",
    "doc_url": "https://github.com/1C0D/Addon_Installer-Script_Runner-BlenderAddon",
    "category": "Development",
}

'''
Browser to directly apply things on selection, when confirm

1-install/reload selected ADDON(S)
    "Update" option (in browser):
        ¤ on: install greater version number. reload if same
        ¤ off: previous version allowed (actual version disabled)
    avoids dupplicates (same content but different file name)
    
2-install folder as an addon
    detecting  "__init__.py" inside

3-install/reload active file from TEXT EDITOR

4-run scripts (single file .py)

5-location and options
    -Blender icon menu:
        ¤ install/reload addon
        ¤ clean dupplicates and lower versions
        ¤ remove fake-modules
        ¤ last installed addons (result in console)
        ¤ restart blender (temp.blend if not saved)

    -text editor
        ¤ creates a quick favorite 'Ctrl+Q'
        ¤ install/reload addon
        ¤ install/reload from Text Editor

N.B you can check messages in the console

'''

# ----------------------------- FUNCTIONS --------------------------------------


def get_bl_info_dic(file, path):
    with file:
        lines = []
        line_iter = iter(file)
        l = ""
        while not l.startswith("bl_info"):
            try:
                l = line_iter.readline()
            except UnicodeDecodeError as ex:
                print(f'===> Error reading file as UTF-8: {path}, {ex}')
                return None

            if len(l) == 0:
                break

        while l.rstrip():
            lines.append(l)
            try:
                l = line_iter.readline()
            except UnicodeDecodeError as ex:
                print(f'===> Error reading file as UTF-8: {path}, {ex}')
                return None

        data = "".join(lines)
    del file
    return data


def use_ast(path, data):
    import ast
    ModuleType = type(ast)
    body = None

    try:
        ast_data = ast.parse(data, filename=path)
    except:
        print(f'===> Syntax error "ast.parse" can\'t read: {path}')
        ast_data = ""

    body_info = None

    if ast_data:
        for body in ast_data.body:
            if (
                body.__class__ == ast.Assign
                and len(body.targets) == 1
                and getattr(body.targets[0], "id", "") == "bl_info"
            ):
                body_info = body
                break

    return body_info, ModuleType, ast, body


def open_init(dirname):
    init = os.path.join(dirname, "__init__.py")
    try:
        with open(init, "r", encoding='UTF-8') as f:
            data = get_bl_info_dic(f, init)  # detect bl_info
            body_info, ModuleType, ast, body = use_ast(
                init, data)  # use ast to get bl_info[name]
    except EnvironmentError as ex:
        print(f'===> Error opening file: {init}')
        return None

    return body_info, ModuleType, ast, body


def is_installed(self, context):

    addon_path = Path(self.directory)
    addon_list = []

    for name_ext in os.listdir(addon_path):
        p = os.path.join(addon_path, name_ext)
        name = Path(p).stem
        data = []

        if not os.path.isfile(p):
            continue

        if Path(p).suffix == '.py':  # open .py
            try:
                with open(p, "r", encoding='UTF-8') as f:
                    data = get_bl_info_dic(f, p)  # detect bl_info
            except EnvironmentError as ex:  # parent of IOError, OSError *and* WindowsError where available
                print(f'===> Error opening file: {p}, {ex}')
                continue

        elif Path(p).suffix == '.zip':  # open .zip
            try:
                with ZipFile(p, 'r') as zf:
                    init = [info.filename for info in zf.infolist(
                    ) if info.filename.split("/")[1] == '__init__.py']
                    for fic in init:
                        try:
                            with io.TextIOWrapper(
                                    zf.open(fic), encoding="utf-8") as f:
                                data = get_bl_info_dic(f, p)  # detect bl_info
                        except EnvironmentError as ex:
                            print(f'===> Error opening file: {p}, {ex}')
                            continue

            except IndexError:
                print(f'===> 1 file ignored: {p}')
                continue

        body_info, ModuleType, ast, body = use_ast(p, data)  # use ast

        # ADDON(S) INSTALLATION/RELOAD
        if body_info:  # ADDONS
            try:
                mod = ModuleType(name)  # find bl_info parameters
                mod.bl_info = ast.literal_eval(body.value)
                data_mod_name = mod.bl_info['name']
                data_mod_version = mod.bl_info.get('version', (0, 0, 0))
                if len(data_mod_version) == 2:
                    data_mod_version += (0,)
                data_mod_category = mod.bl_info['category']

            except:
                print(f'===> Invalid bl_info for: {name}')
                # import traceback
                # traceback.print_exc()
                # raise
                continue

            addon_list.append(
                (name, data_mod_category, data_mod_name, data_mod_version))  # do a list of parameters to sort them later

    print('*'*50+"Installed"+'*'*50)
    if addon_list:
        installed = []
        for mod_name in bpy.context.preferences.addons.keys():
            try:
                mod = sys.modules[mod_name]
                installed.append(
                    (mod.__name__, mod.bl_info['category'], mod.bl_info['name'], mod.bl_info.get('version', (0, 0, 0))))
            except KeyError:
                pass
        # open a file to write to
        if self.print_result:
            filename = os.path.join(addon_path, "Installed_Addons.txt")
            with open(filename, 'w') as file:
                file.write(str(addon_path)+"\n")
                file.write("\n")
                file.write("Installed addons:\n")
                file.write("\n")
                for a in addon_list:
                    if a in installed:
                        file.write(", ".join(str(e) for e in a)+"\n")
                        print(", ".join(str(e) for e in a))
        else:
            for a in addon_list:
                if a in installed:
                    print(", ".join(str(e) for e in a))
        print("")
        print("File name | category | name | version")
    else:
        print('No addon installed in this directory')
# ----------------------------- BROWSER --------------------------------------


class INSTALLER_OT_FileBrowser(bpy.types.Operator, ImportHelper):
    bl_idname = "installer.file_broswer"
    bl_label = "Install/Reload/Run"

    filter_glob: bpy.props.StringProperty(
        default='*.py;*.zip',
        options={'HIDDEN'},
        subtype='FILE_PATH'  # to be sure to select a file
    )

    update_versions: bpy.props.BoolProperty(
        default=True, name="Update Versions")

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    # https://blender.stackexchange.com/questions/30678/bpy-file-browser-get-selected-file-names

# ---------- properties for installation from folder -------

    def get1(self):
        dirname = Path(self.directory)
        if "__init__.py" in os.listdir(dirname):
            body_info = self.open_init_dirname(dirname)
        return "__init__.py" in os.listdir(dirname) and bool(body_info)

    def set1(self, value):
        dirname = Path(self.directory)
        if "__init__.py" in os.listdir(dirname):
            body_info = self.open_init_dirname(dirname)
        valeur = ("__init__.py" in os.listdir(dirname)) and bool(body_info)
        valeur = value

    def update1(self, context):
        dirname = Path(self.directory)
        if "__init__.py" in os.listdir(dirname):
            body_info = self.open_init_dirname(dirname)
        if "__init__.py" in os.listdir(dirname) and bool(body_info):
            self.install_folder = True

    def open_init_dirname(self, dirname):
        dirbasename = os.path.basename(dirname)
        addon_path = bpy.utils.user_resource('SCRIPTS', 'addons')
        dest = os.path.join(addon_path, dirbasename)
        result, *_ = open_init(dirname)
        return result

    def update(self, context):
        if self.print_installed:
            is_installed(self, context)
            self.print_installed = False

    install_folder: bpy.props.BoolProperty(default=False, get=get1, set=set1, update=update1,
                                           name="Install From Folder")  # get=get1, set=set1, update=update1,

    print_installed: bpy.props.BoolProperty(default=False, update=update)
    print_result: bpy.props.BoolProperty(default=False)
    directory: bpy.props.StringProperty(
        subtype='DIR_PATH')  # to have the directory path too

    def execute(self, context):

        print('*'*150)
        print('')
        print('ADDON INSTALLER|SCRIPT RUNNER')
        print('')
        print('*'*150)

        names = []
        addon_list = []
        name = ''

# ---------------------- addon installation from folder ----------------

        dirname = Path(self.directory)
        dirbasename = os.path.basename(dirname)
        addon_path = bpy.utils.user_resource('SCRIPTS', "addons")
        dest = os.path.join(addon_path, dirbasename)

        if "__init__.py" in os.listdir(dirname):  # detect __init__ in folder
            body_info, ModuleType, ast, body = open_init(dirname)

            # ADDON FROM FOLDER
            if body_info:
                try:
                    mod = ModuleType(dirbasename)
                    mod.bl_info = ast.literal_eval(body.value)
                    data_mod_name = mod.bl_info['name']

                except:
                    # print(f'===> AST error parsing bl_info for: {dirbasename}')
                    self.report({'ERROR'}, "Invalid bl_info in init file")
                    return {'CANCELLED'}

                # disable
                try:
                    bpy.ops.preferences.addon_disable(module=dirbasename)

                except:
                    print('===> couldn\'t disable' + data_mod_name)
                    self.report(
                        {'ERROR'}, f"COULDN'T DISABLE {data_mod_name}, see in Console")
                    return {'CANCELLED'}

                # copy/replace files in addon folder
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(dirname, dest)

                # modify last modified > date of installation to get mod.__time__ (I do only on the __init__.py)
                # https://stackoverflow.com/questions/11348953/how-can-i-set-the-last-modified-time-of-a-file-from-python
                from datetime import datetime

                def set_file_last_modified(file_path, dt):
                    dt_epoch = dt.timestamp()
                    os.utime(file_path, (dt_epoch, dt_epoch))

                now = datetime.now()
                new_path = os.path.join(dest, "__init__.py")
                set_file_last_modified(new_path, now)

                # refresh addons
                ar = context.screen.areas
                area = next((a for a in ar if a.type == 'PREFERENCES'), None)
                bpy.ops.preferences.addon_refresh({'area': area})

                # enable addon
                try:
                    bpy.ops.preferences.addon_enable(module=dirbasename)

                except:
                    print('===> couldn\'t addon_enable ' + name)
                    self.report(
                        {'ERROR'}, f"COULDN'T ENABLE {data_mod_name}, see in Console")
                    return {'CANCELLED'}

                self.report({'INFO'}, "Installed/Reloaded: " + data_mod_name)

                return {'FINISHED'}

            else:
                self.report({'ERROR'}, "no valid bl_info in init file")
                return {'CANCELLED'}

# ---------------------- addon installation from files/script running ----------------

        else:
            for f in self.files:  # <bpy_struct, PropertyGroup("addon.py")

                p = os.path.join(dirname, f.name)
                name = Path(p).stem
                names.append(name)
                data = []

                if not os.path.exists(p):
                    self.report({'ERROR'}, f'Wrong Path {p}')
                    print(f"===> invalid path: {p}")
                    return {'CANCELLED'}

                if Path(p).suffix == '.py':  # open .py
                    try:
                        with open(p, "r", encoding='UTF-8') as f:
                            data = get_bl_info_dic(f, p)  # detect bl_info
                    except EnvironmentError as ex:
                        print(f'===> Error opening file: {p}, {ex}')
                        continue

                elif Path(p).suffix == '.zip':  # open .zip
                    try:
                        with ZipFile(p, 'r') as zf:
                            init = [info.filename for info in zf.infolist(
                            ) if info.filename.split("/")[1] == '__init__.py']
                            for fic in init:
                                try:
                                    with io.TextIOWrapper(
                                            zf.open(fic), encoding="utf-8") as f:
                                        data = get_bl_info_dic(
                                            f, p)  # detect bl_info
                                except EnvironmentError as ex:
                                    print(
                                        f'===> Error opening file: {p}, {ex}')
                                    continue

                        del zf
                    except IndexError:
                        print(f'===> 1 file ignored: {p}')
                        continue

                body_info, ModuleType, ast, body = use_ast(p, data)  # use ast

                # ADDON(S) INSTALLATION/RELOAD
                if body_info:  # ADDONS
                    try:
                        mod = ModuleType(name)  # find bl_info parameters
                        mod.bl_info = ast.literal_eval(body.value)
                        data_mod_name = mod.bl_info['name']
                        data_mod_version = mod.bl_info.get(
                            'version', (0, 0, 0))
                        if len(data_mod_version) == 2:
                            data_mod_version += (0,)
                        data_mod_category = mod.bl_info['category']

                    except:
                        print(f'===> Invalid bl_info for: {name}')
                        # import traceback
                        # traceback.print_exc()
                        # raise
                        continue

                    addon_list.append(
                        [data_mod_category, data_mod_name, data_mod_version, name, p])  # do a list of parameters to sort them later

                else:  # SCRIPT EXECUTION
                    if len(self.files) > 1:
                        self.report(
                            {'ERROR'}, 'Not executed, Select only 1 SCRIPT')
                        return {'FINISHED'}

                    try:
                        # run script
                        # Get scripts folder and add it to the search path for modules
                        if dirname not in sys.path:
                            sys.path.append(dirname)
                        # Change current working directory to scripts folder
                        os.chdir(dirname)

                        # exec(compile(open(path).read(), path, 'exec'),{})
                        global_namespace = {
                            "__file__": p, "__name__": "__main__"}
                        try:
                            with open(p, 'rb') as file:  # r rb maybe binary?
                                exec(compile(file.read(), p, 'exec'),
                                     global_namespace)

                        except (ValueError, FileNotFoundError) as e:
                            self.report({'WARNING'}, 'Not valid File!')
                            return {'CANCELLED'}

                        self.report({'INFO'}, f'RUN SCRIPT: "{name}"')
                        return {'FINISHED'}
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

                # counter = [(word, count) for word,
                # count in dict.most_common()]  # dupplicates

                # greatest / lower versions among selected (when multi install maybe several versions of a same addon...)
                # greater = ()
                for u, v in dict.items():
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
                        bpy.ops.preferences.addon_remove(
                            module=removed.__name__)
                        print(
                            f'===> "{removed.__name__}" REMOVED (LOWER VERSION)')
                    except:
                        print(f'===> couldn\'t remove "{removed.__name__}"')
                        self.report(
                            {'ERROR'}, f"COULDN'T REMOVE {name}",  see in Console)
                        return {'CANCELLED'}

                print('')
                print(
                    f'NOT INSTALLED (file_name|name|version): {[(i[3]+".py",i[1],i[2]) for i in addon_list]}')
                print('')

                self.report(
                    {'INFO'}, f'{len(addon_list)} IGNORED (lower version) ')

            else:

                if len(self.files) > 1:
                    self.report(
                        {'ERROR'}, "SELECT ONLY 1 FILE (Update unchecked")
                    return {'FINISHED'}

                else:

                    my_list = [addon for addon in addon_utils.modules() for a in addon_list
                               if (addon.bl_info['name'] == a[1]
                                   and addon.bl_info['category'] == a[0])]
                    for a in my_list:
                        bpy.ops.preferences.addon_disable(module=a.__name__)

                    greatest = addon_list

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
                    self.report(
                        {'ERROR'}, f"COULDN'T DISABLE {name1}, see in Console")
                    return {'CANCELLED'}

                # remove/install
                try:
                    bpy.ops.preferences.addon_remove(module=name1)

                except:
                    print('===> couldn\'t remove' + name1)
                    self.report(
                        {'ERROR'}, f"COULDN'T REMOVE {name1}, see in Console")
                    return {'CANCELLED'}

                try:
                    bpy.ops.preferences.addon_install(filepath=p)

                except:
                    print('===> couldn\'t install' + name1)
                    self.report(
                        {'ERROR'}, f"COULDN'T INSTALL {name1}, see in Console")
                    return {'CANCELLED'}

                # enable
                try:
                    if Path(p).suffix == '.zip':

                        # changing the name of a zip, the name of the first subfolder is different. when doing enable, name is the name of the subfolder...
                        with ZipFile(p, 'r') as f:
                            names = [info.filename for info in f.infolist()
                                     if info.is_dir()]
                        if names:
                            namezip = names[0].split("/")[0]
                        else:
                            namezip = name1

                        bpy.ops.preferences.addon_enable(module=namezip)
                    else:
                        bpy.ops.preferences.addon_enable(module=name1)

                except:
                    print('===> couldn\'t addon_enable ' + name1)
                    self.report(
                        {'ERROR'}, f"COULDN'T ENABLE {name1}, see in Console")
                    return {'CANCELLED'}

                lower_versions.extend(not_installed)

                print('')
                print(
                    f'REMOVED (file_name|name|version): {[(i.__name__+".py",i.bl_info["name"],i.bl_info["version"]) for i in to_remove]}')
                print('')
                print(
                    f'NOT INSTALLED (file_name|name|version): {[(i[3]+".py",i[1],i[2]) for i in lower_versions]}')
                print('')
                print(
                    f'INSTALLED/RELOADED (file_name|name|version): {[(i[3]+".py",i[1],i[2]) for i in greatest]}')
                print('')

                self.report(
                    {'INFO'}, f'{len(to_remove)} REMOVED, {len(greatest)} INSTALLED, {len(lower_versions)} IGNORED (lower version) ')

                if len(self.files) > 1:
                    self.report({'INFO'}, "MULTI INSTALLED/RELOADED ")

                else:
                    self.report({'INFO'}, "INSTALLED/RELOADED: " + name1)

            return {'FINISHED'}

    def draw(self, context):

        layout = self.layout
        if self.install_folder:
            layout.label(text="INSTALL FOLDER AS AN ADDON: ")
        else:
            layout.label(text="Select file(s) and confirm")
            layout.prop(self, "update_versions")
        layout.label(text='')
        layout.label(text="Clic (no change) > see in console:")
        # ,  invert_checkbox=False)
        layout.prop(self, "print_installed",
                    text="Installed Addons in this folder  ", toggle=True)
        layout.prop(self, "print_result",
                    text="create installed_addons.txt (in folder)")

# ----------------------------- INSTALL/RELOAD FROM TEXT EDITOR


class INSTALLER_OT_TextEditor(bpy.types.Operator):

    bl_idname = "installer.text_editor"
    bl_label = "Install Addon from Text Editor"

    def execute(self, context):

        if context.space_data.text:

            print('*'*150)
            print('')
            print('INSTALLER|RELOAD FROM TEXT EDITOR')
            print('')
            print('*'*150)

            name = context.space_data.text.name

            split = name.split(".")
            if len(split) <= 2 and split[0] == 'Text' and split[-1] != 'py':
                self.report(
                    {'WARNING'}, 'Name your file in text editor (not "Text.")')
                return {'CANCELLED'}
            # if start == 'Text' and end.isnumeric():
                # self.report({'ERROR'}, "Rename your addon in text editor(not Text or Text.001)")
                # return {'CANCELLED'}
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
                self.report(
                    {'ERROR'}, f"COULDN'T DISABLE {name}, see in Console")
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
                self.report(
                    {'ERROR'}, f"COULDN'T ENABLE {name}, see in Console")
                return {'CANCELLED'}

            self.report({'INFO'}, "Installed/Reloaded: " + name)

        else:
            self.report({'WARNING'}, "No Text file in Text Editor")

        return {'FINISHED'}


# -----------------------------ADDONS CLEANER

class ADDON_OT_Cleaner(bpy.types.Operator):
    bl_idname = "addon.cleaner"
    bl_label = "addon cleaner"

    def execute(self, context):

        # search dupplicates addon and old versions in all addons to keep only last update
        my_list = [(addon.bl_info.get('category', ("User")), addon.bl_info['name'], addon.bl_info.get('version', (0, 0, 0)), addon.__name__)
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
                    elif k > greater:
                        greater = k
                        greatest.pop()
                        greatest.append([i, j, greater, l])
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
        for name in os.listdir(addon_path):
            name_path = os.path.join(addon_path, name)

            if os.path.isfile(name_path) and Path(name_path).suffix == '.py':
                try:
                    with open(name_path, "r", encoding='UTF-8') as f:
                        data = get_bl_info_dic(f, name_path)
                        if not data:
                            print('===> FAKE-MODULE REMOVED: ',  name)
                            names.append(name)
                            os.remove(name_path)
                except EnvironmentError as ex:
                    print("Error opening file:", name_path, ex)
                    continue

            if os.path.isdir(name_path):
                if "__init__.py" in os.listdir(name_path) and name != "__pycache__":
                    body_info, ModuleType, ast, body = open_init(name_path)

                    if not body_info:
                        print('===> FAKE-MODULE REMOVED: ',  name, '(folder)')
                        names.append(name)
                        shutil.rmtree(name_path)
                        continue

                if "__init__.py" not in os.listdir(name_path) and name != "__pycache__":
                    print('===> FAKE-MODULE REMOVED: ',  name, '(folder)')
                    names.append(name)
                    shutil.rmtree(name_path)
                    continue

        self.report(
            {'INFO'}, f'{len(names)} FAKE(S) MODULE REMOVED, name(s) in console')

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
                    (mod.__name__, mod.bl_info['category'], mod.bl_info['name'], mod.bl_info.get('version', (0, 0, 0)), mod.__time__))
            except KeyError:
                pass
        last_installed = sorted(installed, key=lambda x: (x[4]))

        last_installed_date = [(i, j, k, l, ctime(m))
                               for i, j, k, l, m in last_installed]

        for last in last_installed_date:
            print(last)
        print("")
        print("File name | category | name | version | date")

        self.report({'INFO'}, "See in the Console")

        return {'FINISHED'}


def launch():
    """
    launch the blender process
    """
    binary_path = bpy.app.binary_path  # blender.exe path
    file_path = bpy.data.filepath  # saved .blend file
    # check if the file is saved
    if file_path:
        if bpy.data.is_dirty:  # some changes since the last save
            bpy.ops.wm.save_as_mainfile(filepath=file_path)

    else:  # if no save, save as temp
        file_path = os.path.join(tempfile.gettempdir(), "temp.blend")
        bpy.ops.wm.save_as_mainfile(filepath=file_path)

    # launch a background process
    subprocess.Popen([binary_path, file_path])


class RESTART_OT_blender(bpy.types.Operator):
    bl_idname = "blender.restart"
    bl_label = "Restart"

    def execute(self, context):
        # what is reloaded after the exit
        atexit.register(launch)
        # sleep #? _if bug
        # sleep(0.2)
        # # quit blender
        exit()
        return {'FINISHED'}


class OPEN_OT_user_addons(bpy.types.Operator):
    bl_idname = "open.user_addons"
    bl_label = "Open user addons folder"

    def execute(self, context):

        filepath = bpy.utils.user_resource('SCRIPTS', "addons")
        bpy.ops.wm.path_open(filepath=filepath)

        return {"FINISHED"}


class ADDON_OT_installed_list(bpy.types.Operator):
    """generates addons list"""
    bl_idname = "addon.installed_list"
    bl_label = "generates addons list"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled Addons.txt")
        addons = bpy.context.preferences.addons

        with open(filepath, 'w') as file:
            for mod_name in list(addons.keys()):
                file.write(mod_name+"\n")

        return {'FINISHED'}


class ADDON_OT_disable_all(bpy.types.Operator):
    """disable all addons"""
    bl_idname = "addon.disable_all"
    bl_label = "disable all addons"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled Addons.txt")
        addons = bpy.context.preferences.addons

        with open(filepath, 'w') as file:
            for mod_name in list(addons.keys()):
                file.write(mod_name+"\n")

        enablist = [addon.module for addon in addons]
        for addon in addon_utils.modules():
            print(addon.__name__)
            if (
                addon.__name__ in enablist
                and "Advanced_Addons_Installer" not in addon.__name__
            ):
                try:
                    bpy.ops.preferences.addon_disable(module=addon.__name__)
                except:
                    self.report(
                        {'WARNING'}, f"COULDN'T DISABLE {addon.__name__}, see in Console")

        return {'FINISHED'}


class ADDON_OT_enable_from_list(bpy.types.Operator):
    """enable addons from list"""
    bl_idname = "addon.enable_from_list"
    bl_label = "enable addons from list"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled Addons.txt")

        liste = []
        with open(filepath, 'r') as file:
            for line in file:
                # remove \n
                element = line[:-1]
                liste.append(element)
            for addon in addon_utils.modules():
                if (
                    addon.__name__ in (liste)
                    and "Advanced_Addons_Installer" not in addon.__name__
                ):
                    try:
                        bpy.ops.preferences.addon_enable(module=addon.__name__)
                    except:
                        self.report(
                            {'WARNING'}, f"COULDN'T ENABLE {addon.__name__}, see in Console")

        return {'FINISHED'}

# ----------------------------------------Menus


class ADDON_MT_enable_disable_menu(bpy.types.Menu):
    bl_label = 'Enable/Disable All Addons'

    def draw(self, context):
        layout = self.layout
        layout.operator("addon.disable_all",
                        text="Disable All Addons")
        layout.operator("addon.enable_from_list",
                        text="Enable All Addons")
        layout.operator("addon.installed_list",
                        text="list only: Enabled Addons.txt")  # faire ouvrir le dossier sur fichier ou entrée sup user folder
        layout.operator("open.user_addons", text='See it in User addons Folder',
                        icon='FOLDER_REDIRECT')


class ADDON_MT_management_menu(bpy.types.Menu):
    bl_label = 'addon management'

    def draw(self, context):
        layout = self.layout
        layout.operator("installer.file_broswer",
                        text="Install/Reload Addon(s)", icon='FILEBROWSER')
        layout.operator(ADDON_OT_Cleaner.bl_idname,
                        text="Clean Lower Versions Addons")
        layout.operator(ADDON_OT_fake_remove.bl_idname,
                        text="Remove Fake Modules")
        layout.operator(ADDON_OT_last_installed.bl_idname)
        layout.operator(RESTART_OT_blender.bl_idname,
                        text="Restart Blender")
        layout.menu('ADDON_MT_enable_disable_menu',
                    text='Enable/Disable All Addons')


def draw(self, context):

    layout = self.layout
    layout.separator(factor=1.0)
    layout.menu('ADDON_MT_management_menu', text='Add-ons Management')


def draw1(self, context):

    layout = self.layout
    layout.separator(factor=1.0)
    layout.operator("installer.file_broswer",
                    text="Install/Reload Addon(s)", icon='FILEBROWSER')
    layout.operator("installer.text_editor",
                    text="Addon from Text Editor", icon='COLLAPSEMENU')
    layout.operator("open.user_addons", text='Open User addons',
                    icon='FOLDER_REDIRECT')


classes = (INSTALLER_OT_FileBrowser, INSTALLER_OT_TextEditor,
           ADDON_OT_Cleaner, ADDON_OT_fake_remove,
           ADDON_MT_management_menu, ADDON_OT_last_installed,
           RESTART_OT_blender, OPEN_OT_user_addons,
           ADDON_OT_installed_list, ADDON_OT_disable_all,
           ADDON_OT_enable_from_list, ADDON_MT_enable_disable_menu)

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
