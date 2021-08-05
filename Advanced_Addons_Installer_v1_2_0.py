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
from zipfile import ZipFile, is_zipfile
import shutil

bl_info = {
    "name": "Advanced Addons Installer",
    "description": "install save reload addons or run scripts",
    "author": "1C0D",
    "version": (1, 2, 0),
    "blender": (2, 93, 0),
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
    detecting  "__init__.py" inside. 
    this is how the addon is switching between install from folder or normal install from a file or a zip
    ! if you change the name of the folder the update version is not working

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

bpy.types.Scene.print_result_bridge = bpy.props.BoolProperty()

# ----------------------------- FUNCTIONS --------------------------------------


def ShowMessageBox(message, title, icon):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def reported(self, err, message='', type='INFO', title='Report: Error', message1='', box=False):
    msg = ' / ERRORS!(Console)' if err else ''

    self.report({type}, message + msg)
    if err or box:
        message1 = message+msg if not message1 else message1
        ShowMessageBox(message1, title, icon='ERROR')


def get_bl_info_dic(file, path, err):
    with file:
        lines = []
        line_iter = iter(file)
        l = ""
        while not l.startswith("bl_info"):
            try:
                l = line_iter.readline()
            except UnicodeDecodeError as ex:
                print(f'\n===> Error reading file as UTF-8: {path}\n{ex}\n')
                err = True
                return None, err

            if len(l) == 0:
                break

        while l.rstrip():
            lines.append(l)
            try:
                l = line_iter.readline()
            except UnicodeDecodeError as ex:
                print(f'\n===> Error reading file as UTF-8: {path}\n{ex}\n')
                err = True
                return None, err

        data = "".join(lines)
    del file
    return data, err


def use_ast(path, data):  # type error ast?
    import ast
    ModuleType = type(ast)
    body = None

    try:
        ast_data = ast.parse(data, filename=path)
    except:
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


def open_py(path, err=False):
    try:
        with open(path, "r", encoding='UTF-8') as f:
            data, err = get_bl_info_dic(f, path, err)  # detect bl_info
    except EnvironmentError as ex:
        print(f'\n===> Error reading file as UTF-8: {path}\n{ex}\n')
        err = True
        return None, err

    return data, err


def open_zip(path, err):
    if not is_zipfile(path):  # valid ZIP
        print(f'\n===> INVALID ZIPFILE: {path}\n')
        err = True
        return None, err

    with ZipFile(path, 'r') as zf:
        init = [info.filename for info in zf.infolist(
        ) if info.filename.split("/")[1] == '__init__.py']
        for fic in init:
            try:
                with io.TextIOWrapper(
                        zf.open(fic), encoding="utf-8") as f:
                    data, err = get_bl_info_dic(f, path, err)  # detect bl_info
                del f
            except EnvironmentError as ex:
                print(f'\n===> Error reading file in {path}\n{ex}\n')
                err = True
                return None, err
    return data, err


def get_module_infos(name, ModuleType, ast, body):  # compare with blender code
    mod = ModuleType(name)  # find bl_info parameters
    mod.bl_info = ast.literal_eval(body.value)
    data_mod_name = mod.bl_info['name']
    data_mod_version = mod.bl_info.get('version', (0, 0, 0))
    if len(data_mod_version) == 2:
        data_mod_version += (0,)
    data_mod_category = mod.bl_info['category']
    return data_mod_name, data_mod_category, data_mod_version


def join_dir_file(context, filename, dirpath=''):
    if not dirpath:
        dirpath = context.space_data.params.directory.decode("utf-8")
    return os.path.join(dirpath, filename)


def refresh_addon(context):
    ar = context.screen.areas
    area = next((a for a in ar if a.type == 'PREFERENCES'), None)
    bpy.ops.preferences.addon_refresh({'area': area})


def modify_date_init(path):  # useful after to sort last modified addons
    from datetime import datetime

    def set_file_last_modified(file_path, dt):
        dt_epoch = dt.timestamp()
        os.utime(file_path, (dt_epoch, dt_epoch))

    now = datetime.now()
    new_path = os.path.join(path, "__init__.py")
    set_file_last_modified(new_path, now)


def run_script(self, path, dirpath, name):

    if dirpath not in sys.path:
        sys.path.append(dirpath)
    # Change current working directory to scripts folder
    os.chdir(dirpath)

    # exec(compile(open(path).read(), path, 'exec'),{}) #not enough
    global_namespace = {
        "__file__": path, "__name__": "__main__"}
    with open(path, 'r') as file:
        exec(compile(file.read(), path, 'exec'),
             global_namespace)

    self.report({'INFO'}, f'RUN SCRIPT: "{name}"')


class IS_OT_Installed(bpy.types.Operator):
    bl_idname = "is.installed"
    bl_label = "is installed"
    bl_option = {'INTERNAL'}

    def execute(self, context):
        dirpath = context.space_data.params.directory.decode("utf-8")
        addon_list = []
        err = False

        for name_ext in os.listdir(dirpath):
            path = join_dir_file(context, name_ext, dirpath)
            name = Path(path).stem
            data = []

            if not os.path.isfile(path):
                continue

            if Path(path).suffix == '.py':
                data, err = open_py(path, err)

            elif Path(path).suffix == '.zip':
                data, err = open_zip(path, err)
                if err:
                    continue

            else:
                continue

            body_info, ModuleType, ast, body = use_ast(path, data)  # use ast

            # ADDON(S) INSTALLATION/RELOAD
            if body_info:  # ADDONS
                try:
                    data_mod_name, data_mod_category, data_mod_version = get_module_infos(
                        name, ModuleType, ast, body)

                except:
                    print(f'\n===> INVALID BL_INFO: {path}\n')
                    err = True
                    continue

                addon_list.append(
                    (name, data_mod_category, data_mod_name, data_mod_version))  # list of parameters to sort

        # ----------end loop
        print('\n' + '*'*20 +
              f" Installed Addons in {dirpath} " + '*'*20 + "\n")
        if addon_list:
            installed = []
            for mod_name in bpy.context.preferences.addons.keys():
                try:
                    mod = sys.modules[mod_name]
                    installed.append(
                        (mod.__name__, mod.bl_info['category'], mod.bl_info['name'],
                         mod.bl_info.get('version', (0, 0, 0))))
                except KeyError as ex:
                    print(f'\n===> INVALID BL_INFO in {mod_name}\n{ex}\n')
                    err = True
            # open a file to write to
            if context.scene.print_result_bridge:
                filename = join_dir_file(context, "Installed.txt", dirpath)
                with open(filename, 'w') as file:
                    file.write(str(dirpath)+"\n\nInstalled addons:\n\n")

                    for a in addon_list:
                        if a in installed:
                            file.write(", ".join(str(e) for e in a)+"\n")
                            print(", ".join(str(e) for e in a))
            else:
                for a in addon_list:
                    if a in installed:
                        print(", ".join(str(e) for e in a))

                print(
                    "\nFile name     |      category     |      name     |      version\n")

            dirpath = context.space_data.params.directory.decode("utf-8")
            filepath = join_dir_file(context, "Installed.txt", dirpath)
            if os.path.exists(filepath):
                message1 = "Installed.txt added to the folder"
            else:
                message1 = 'Check Result in Blender Console'

            reported(self, err, message='DONE', message1=message1,
                     title='Message:', box=True)

        else:
            reported(self, err, message='0 result', title='Message:')

        return {'FINISHED'}


class OPEN_OT_Installed(bpy.types.Operator):
    bl_idname = "open.installed"
    bl_label = "Open installed"
    bl_option = {'INTERNAL'}

    ON: bpy.props.BoolProperty(default=True)

    def execute(self, context):

        filepath = join_dir_file(context, "Installed.txt")
        if os.path.exists(filepath):
            bpy.ops.file.select(open=False, deselect_all=True)
            if self.ON:
                subprocess.Popen(f'explorer / open, {filepath}')  # open?
            else:
                subprocess.Popen(f'explorer /select, {filepath}')  # open?

        return {'FINISHED'}


# ----------------------------- BROWSER --------------------------------------

class INSTALLER_OT_FileBrowser(bpy.types.Operator, ImportHelper):
    bl_idname = "installer.file_broswer"
    bl_label = "Install/Reload/Run"

    filter_glob: bpy.props.StringProperty(
        default='*.py;*.zip;*.txt',
        options={'HIDDEN'},
        subtype='FILE_PATH'  # to be sure to select a file
    )

    update_versions: bpy.props.BoolProperty(
        default=True, name="Update Versions")

    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    # https://blender.stackexchange.com/questions/30678/bpy-file-browser-get-selected-file-names

# ---------- properties for installation from folder

    def get(self):
        dirpath = Path(self.directory)
        if "__init__.py" in os.listdir(dirpath):
            init = os.path.join(dirpath, "__init__.py")
            data, _ = open_py(init)
            body_info, *_ = use_ast(init, data)

        return "__init__.py" in os.listdir(dirpath) and bool(body_info)

    def set(self, value):
        dirpath = Path(self.directory)
        if "__init__.py" in os.listdir(dirpath):
            init = os.path.join(dirpath, "__init__.py")
            data, _ = open_py(init)
            body_info, *_ = use_ast(init, data)

        valeur = "__init__.py" in os.listdir(dirpath) and bool(body_info)
        valeur = value

    def update_install_folder(self, context):
        dirpath = Path(self.directory)
        if "__init__.py" in os.listdir(dirpath):
            init = os.path.join(dirpath, "__init__.py")
            data, _ = open_py(init)
            body_info, *_ = use_ast(init, data)

            if bool(body_info):
                self.install_folder = True

    def update_print_result(self, context):
        if not self.install_folder:
            context.scene.print_result_bridge = self.print_result

    print_result: bpy.props.BoolProperty(
        default=True, update=update_print_result)

    install_folder: bpy.props.BoolProperty(default=False, get=get, set=set, update=update_install_folder,
                                           name="Install From Folder")

    directory: bpy.props.StringProperty(
        subtype='DIR_PATH')  # to have the directory path too

    def execute(self, context):
        print('\n' + '*'*50 + ' ADDON INSTALLER|SCRIPT RUNNER ' + '*'*50 + '\n')

# ---------------------- addon installation from folder

        dirpath = Path(self.directory)
        dirname = os.path.basename(dirpath)
        addon_path = bpy.utils.user_resource('SCRIPTS', "addons")
        err = False
        from_folder = False
        addon_list = []
        names = []
        ignored = []
        name1 = ''

        if "__init__.py" in os.listdir(dirpath):  # detect __init__ in folder
            from_folder = True
            init = os.path.join(dirpath, "__init__.py")
            data, err = open_py(init, err)
            body_info, ModuleType, ast, body = use_ast(
                init, data)  # use ast to get bl_info[name]
            # ADDON FROM FOLDER
            if body_info:
                try:
                    data_mod_name, data_mod_category, data_mod_version = get_module_infos(
                        dirname, ModuleType, ast, body)
                except:
                    err = True
                    print(f'\n===> INVALID BL_INFO: {init}\n')
                    reported(self, err, message='INVALID BL_INFO', type='ERROR')
                    return {'CANCELLED'}

                addon_list.append(
                    [data_mod_category, data_mod_name, data_mod_version, data_mod_name, init])


# ---------------------- addon installation from files/script running

        else:

            for f in self.files:

                path = os.path.join(dirpath, f.name)
                name = Path(path).stem
                names.append(name)
                data = []
                body_info = None

                if not os.path.exists(path):
                    self.report(
                        {'WARNING'}, f'WRONG PATH {path}, check your selection')
                    ShowMessageBox(
                        message=f'WRONG PATH {path}, check your selection', title="WARNING", icon='ERROR')
                    return {'CANCELLED'}

                if Path(path).suffix == '.py':
                    data, err = open_py(path, err)

                elif Path(path).suffix == '.zip':
                    data, err = open_zip(path, err)

                else:  # .txt
                    ignored.append(f.name)
                    continue

                if data:
                    body_info, ModuleType, ast, body = use_ast(
                        path, data)  # use ast

                # ADDON(S) INSTALLATION/RELOAD
                if body_info:
                    try:
                        data_mod_name, data_mod_category, data_mod_version = get_module_infos(
                            name, ModuleType, ast, body)
                    except:
                        ignored.append(f.name)
                        err = True
                        print(f'\n===> INVALID BL_INFO: {path}\n')
                        continue

                    addon_list.append(
                        [data_mod_category, data_mod_name, data_mod_version, name, path])  # do a list of parameters to sort them later

                else:  # SCRIPT EXECUTION
                    if len(self.files) > 1:
                        self.report(
                            {'WARNING'}, 'SELECT 1 FILE ONLY IF SCRIPT')
                        ShowMessageBox(
                            message="SELECT 1 FILE ONLY IF SCRIPT", title="WARNING", icon='ERROR')

                        return {'CANCELLED'}

                    script = run_script(self, path, dirpath, name)

                    return {'FINISHED'}

        # not in the precedent loop to not repeat same operations for each file
        greatest = []
        lower_versions = []
        not_installed = []
        to_remove = []
        installed = []

        if self.update_versions:
            # same "category: name" occurences in selected addons
            dict = Counter((i, j) for i, j, *_ in addon_list)

            # dict Counter({('Development', 'Open OS Browser'): 2})
            for u in dict.keys():
                greater = ()
                for i, j, k, l, m in addon_list:
                    if (i, j) == u:
                        if not greater:
                            greater = k
                            greatest.append([i, j, k, l, m])
                        elif greater and k > greater:
                            greater = k
                            lower = greatest.pop()
                            lower_versions.append(lower)
                            greatest.append([i, j, k, l, m])  # greatest

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

                except:
                    err = True
                    print(
                        f"\nERROR REMOVING PREVIOUS VERSION {removed.__name__}\n")
                    # self.report(
                    # {'ERROR'}, f"ERROR REMOVING PREVIOUS VERSION {removed.__name__}")

            ignored.extend([(i[1], i[2]) for i in not_installed])
            ignored.extend([(i[1], i[2]) for i in lower_versions])

        else:  # no update

            my_list = [addon for addon in addon_utils.modules() for a in addon_list
                       if (addon.bl_info['name'] == a[1]
                           and addon.bl_info['category'] == a[0])]
            for a in my_list:
                bpy.ops.preferences.addon_disable(module=a.__name__)

            greatest = addon_list  # this is not "greatest" but we need this name after

        greatest_cpy = greatest[:]
        for great in greatest:
            name1 = great[3]
            version = great[3]
            path = great[4]

            dest = os.path.join(addon_path, data_mod_name)
            name1 = name1 if not from_folder else data_mod_name

            # disable #usefull?
            try:
                bpy.ops.preferences.addon_disable(module=name1)

            except:
                err = True
                print(
                    f"\n===> ERROR DISABLING PREVIOUS VERSION {name1} /see console\n")

            # never cause error
            bpy.ops.preferences.addon_remove(module=name1)

            # remove
            if from_folder:
                if os.path.exists(dest):  # modify under python 3
                    shutil.rmtree(dest)
                shutil.copytree(dirpath, dest)  # creates the directory too
                new_path = os.path.join(dest, "__init__.py")
                modify_date_init(dest)
                # refresh addons
                refresh_addon(context)
            else:
                # remove/install
                try:
                    # errors still possible? we are checking bl_info and ext already. to see
                    bpy.ops.preferences.addon_install(filepath=path)
                except:
                    err = True
                    print(f"\n===> COULDN'T INSTALL {name1} /see console\n")

            # enable
            try:
                if Path(path).suffix == '.zip':

                    # changing the name of a zip, the name of the first subfolder is different. when doing enable, name is the name of the subfolder...
                    with ZipFile(path, 'r') as f:
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
                greatest_cpy.remove(great)
                bpy.ops.preferences.addon_remove(module=name1)  # clean it
                err = True
                print(f"\n===> COULDN'T ENABLE {name1} (not installed)\n")

        message = f'{len(to_remove)} REMOVED, {len(greatest_cpy)} INSTALLED/RELOADED, {len(ignored)} IGNORED'

        reported(self, err, message=message, message1='ERRORS check Console')

        print('\n' + '_'*80 + '\n')
        print(
            f'{len(to_remove)} REMOVED, {len(greatest_cpy)} INSTALLED/ENABLED, {len(ignored)} IGNORED')
        print(f'===> IGNORED {ignored}')
        print(
            f"===> REMOVED {[(i.bl_info['name'], i.bl_info['version']) for i in to_remove]}")
        print(
            f'===> INSTALLED/RELOADED {[(i[1],i[2]) for i in greatest_cpy]}\n')

        return {'FINISHED'}

    def draw(self, context):

        layout = self.layout
        if self.install_folder:
            row = layout.row()
            row.prop(self, "update_versions")

            layout.label(text="INSTALL FOLDER AS AN ADDON")

        else:
            dirpath = context.space_data.params.directory.decode("utf-8")
            filepath = join_dir_file(context, "Installed.txt", dirpath)

            def pyzip(dirpath):
                for file in os.listdir(dirpath):
                    if file.endswith(('.py', '.zip')):
                        return True

            if pyzip(dirpath):
                row = layout.row()
                row.prop(self, "update_versions")
                layout.label(text="Select file(s) and Press Install/...")
                layout.label(text='')
                layout.label(text="Other Operations:")
                layout.label(text='INSTALLED ADDONS in Folder')
                row = layout.row(align=True)
                row.operator("is.installed", text="PRINT")
                row.prop(self, "print_result",
                         text='Do: "Installed.txt"')
                if os.path.exists(filepath):
                    layout.label(text='"Installed.txt" exists:')
                    row = layout.row(align=True)
                    row.operator("open.installed", text="OPEN").ON = True
                    row.operator("open.installed",
                                 text="(OS)BROWSE").ON = False


# ----------------------------- INSTALL/RELOAD FROM TEXT EDITOR -----------------------------

# checked
class INSTALLER_OT_TextEditor(bpy.types.Operator):

    bl_idname = "installer.text_editor"
    bl_label = "Install Addon from Text Editor"

    def execute(self, context):

        err = False

        if context.space_data.text:

            print('\n' + '*'*50 +
                  ' INSTALLER|RELOAD FROM TEXT EDITOR ' + '*'*50 + '\n')

            name = context.space_data.text.name

            split = name.split(".")
            if len(split) == 1 and split[0] == 'Text' or len(split) == 2 and split[0] == 'Text' and split[-1].isnumeric:
                self.report(
                    {'ERROR'}, 'Give a name to your addon (not "Text")')
                return {'CANCELLED'}

            text = bpy.context.space_data.text
            addon = False
            for line in text.lines:
                if line.body.startswith("bl_info"):
                    addon = True
                break

            if addon is False:
                print(f'\n===> {name} has an INVALID BL_INFO\n')
                self.report({'ERROR'}, "BL_INFO MISSING, NOT AN ADDON")
                return {'CANCELLED'}

            # if same addon entered twice in text editor, name is addon.py.001
            if not name.endswith('.py'):
                parts = name.split(".")
                if len(parts) > 1 and parts[-2] == 'py':
                    parts.pop()
                    name = ".".join(parts)
                else:
                    name += '.py'  # .py missing in text editor name

            addon_path = bpy.utils.user_resource('SCRIPTS', "addons")
            # full_path = os.path.join(addon_path, name)
            # I had error path can't be made relative
            full_path = os.path.abspath(os.path.join(addon_path, name))

            # save to blender addons folder
            bpy.ops.text.save_as(filepath=full_path)

            # disable
            try:
                bpy.ops.preferences.addon_disable(module=name[:-3])

            except:
                self.report(
                    {'ERROR'}, f"\nCOULDN'T DISABLE {name}\n")
                return {'CANCELLED'}

            # refresh
            refresh_addon(context)

            # enable
            try:
                bpy.ops.preferences.addon_enable(module=name[:-3])

            except:
                self.report(
                    {'ERROR'}, f"\nCOULDN'T ENABLE {name}\n")
                return {'CANCELLED'}

            self.report({'INFO'}, "Installed/Reloaded: " + name)

        else:
            self.report({'WARNING'}, "No Text file in Text Editor")

        return {'FINISHED'}


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

        for g in greatest:
            if g in version:
                version.remove(g)

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

    err = False
    msg = ' /Check Console(Errors)'

    def execute(self, context):

        addon_path = bpy.utils.user_resource('SCRIPTS', "addons")
        names = []

        for name in os.listdir(addon_path):
            name_path = os.path.join(addon_path, name)

            if os.path.isfile(name_path) and Path(name_path).suffix == '.py':
                try:
                    with open(name_path, "r", encoding='UTF-8') as f:
                        data, err = get_bl_info_dic(f, name_path, err)
                        if not data:
                            print('===> FAKE-MODULE REMOVED: ',  name)
                            names.append(name)
                            os.remove(name_path)
                except EnvironmentError as ex:
                    print("Error opening file:", name_path, ex)
                    continue

            if os.path.isdir(name_path):
                if "__init__.py" in os.listdir(name_path) and name != "__pycache__":
                    data, err = open_py(name_path, err)
                    body_info, *_ = use_ast(name_path, data)
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
            {'INFO'}, f'{len(names)} FAKE(S) MODULE REMOVED, see in console')

        return {'FINISHED'}


class ADDON_OT_last_installed(bpy.types.Operator):
    bl_idname = "addon.print_last_installed"
    bl_label = "Last installed addons (see in console)"

    def execute(self, context):

        print('\n' + '*'*20 + ' sorted last installed addonsR ' + '*'*20 + '\n')
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

        print("\nFile name     |      category     |      name     |      version      |      date\n")

        self.report({'INFO'}, "See in the Console")

        return {'FINISHED'}


class RESTART_OT_blender(bpy.types.Operator):
    bl_idname = "blender.restart"
    bl_label = "Restart"

    def launch(self):
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

    def execute(self, context):

        atexit.register(self.launch)  # what is reloaded after the exit
        exit()  # quit blender
        return {'FINISHED'}


class OPEN_OT_user_addons(bpy.types.Operator):
    bl_idname = "open.user_addons"
    bl_label = "Open user addons folder"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled.txt")
        if os.path.exists(filepath):
            # bpy.ops.wm.path_open(filepath=filepath) + select file
            subprocess.Popen(f'explorer /select, {filepath}')
        else:
            bpy.ops.addon.installed_list()
            subprocess.Popen(f'explorer /select, {filepath}')

        return {"FINISHED"}


class ADDON_OT_installed_list(bpy.types.Operator):
    """generates addons list"""
    bl_idname = "addon.installed_list"
    bl_label = "generates addons list"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled.txt")
        addons = bpy.context.preferences.addons

        with open(filepath, 'w') as file:
            for mod_name in list(addons.keys()):
                file.write(mod_name+"\n")

        return {'FINISHED'}


class ADDON_OT_disable_all(bpy.types.Operator):
    """disable all addons"""
    bl_idname = "addon.disable_all"
    bl_label = "create list & disable all addons"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled.txt")
        addons = bpy.context.preferences.addons

        with open(filepath, 'w') as file:
            for mod_name in list(addons.keys()):
                file.write(mod_name+"\n")

        enablist = [addon.module for addon in addons]
        for addon in addon_utils.modules():
            if (
                addon.__name__ in enablist
                and "Advanced_Addons_Installer" not in addon.__name__
            ):
                try:
                    bpy.ops.preferences.addon_disable(module=addon.__name__)
                except:
                    self.report(
                        {'WARNING'}, f"COULDN'T DISABLE {addon.__name__}")

        return {'FINISHED'}


class ADDON_OT_enable_from_list(bpy.types.Operator):
    """enable addons from list"""
    bl_idname = "addon.enable_from_list"
    bl_label = "enable addons from list"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', "addons")
        filepath = os.path.join(addons_path, "Enabled.txt")

        liste = []
        with open(filepath, 'r') as file:
            for line in file:
                element = line[:-1]  # remove \n
                liste.append(element)

            for addon in addon_utils.modules():
                if (addon.__name__ in (liste)
                        and "Advanced_Addons_Installer" not in addon.__name__):
                    try:
                        bpy.ops.preferences.addon_enable(module=addon.__name__)
                    except:
                        self.report(
                            {'WARNING'}, f"COULDN'T ENABLE {addon.__name__} ")

        return {'FINISHED'}

# ---------------------------------------- Menus ----------------------------------------


class ADDON_MT_enable_disable_menu(bpy.types.Menu):
    bl_label = 'Enable/Disable All Addons'

    def draw(self, context):
        layout = self.layout
        layout.operator("addon.disable_all",
                        text="Do a List & Disable All")
        layout.operator("addon.enable_from_list",
                        text="Enable All from this List")
        layout.operator("addon.installed_list",
                        text='Do List Only (Enabled.txt)')
        layout.operator("open.user_addons", text='See List',
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
           ADDON_OT_enable_from_list, ADDON_MT_enable_disable_menu,
           OPEN_OT_Installed, IS_OT_Installed,
           )

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
