"""
New:
assert power!
open multifiles in text editor and deal with multifiles addons from there

links:
install addons in a folder
https://blender.stackexchange.com/questions/135044/how-to-install-multiple-add-ons-with-python-script/135045#135045
resolve conflicts
https://docs.blender.org/api/2.93/bpy.ops.text.html?highlight=resolve_conflict#bpy.ops.text.resolve_conflict
"""


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
    "version": (1, 4, 1),
    "blender": (2, 93, 0), # and 2.3
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

#os.path.abspath(bpy.path.abspath(relpath))

# ----------------------------- FUNCTIONS --------------------------------------


def show_message_box(message, title, icon):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def reported(self, err=False, message='', type='INFO', title='Report: Error', message1='', box=False):
    msg = '/some ERRORS (Console)' if err else ''

    self.report({type}, message + msg)
    if err or box:
        message1 = message+msg if not message1 else message1
        show_message_box(message1, title, icon='ERROR')


def open_console():
    from ctypes import windll
    GetConsoleWindow = windll.kernel32.GetConsoleWindow
    ShowWindow = windll.user32.ShowWindow
    SwitchToThisWindow = windll.user32.SwitchToThisWindow
    IsWindowVisible = windll.user32.IsWindowVisible
    hWnd = GetConsoleWindow()
    ShowWindow(hWnd, 5)  # SW_SHOW
    SwitchToThisWindow(hWnd, True)  # on Top


def get_bl_info_dic(file, path, err=False):
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
        init = [info.filename for info in zf.infolist() 
                    if os.path.split(info.filename)[1] == '__init__.py']
        #if info.filename.split("/")[1] == '__init__.py']
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
    data_mod_category = mod.bl_info.get('category', 'User')
    return data_mod_name, data_mod_category, data_mod_version


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
    try:
        with open(path, 'r') as file:
            exec(compile(file.read(), path, 'exec'),
                 global_namespace)
    except:
        self.report(
            {'WARNING'}, f'WRONG PATH {path}, check your selection')
        show_message_box(
            message=f'WRONG PATH {path}, check your selection', title="WARNING", icon='ERROR')
        return

    self.report({'INFO'}, f'RUN SCRIPT: "{name}"')


class IS_OT_Installed(bpy.types.Operator):
    bl_idname = "is.installed"
    bl_label = "is installed"
    bl_option = {'INTERNAL'}
    bl_description = 'Print installed addons in this folder'

    def execute(self, context):
        dirpath = context.space_data.params.directory.decode("utf-8")
        print('\n' + '*'*20 +
              f" INSTALLED ADDONS in {dirpath} " + '*'*20 + "\n")
        addon_list = []
        err = False

        for name_ext in os.listdir(dirpath):
            path = os.path.join(dirpath, name_ext)
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
                    print(f'\n===> INVALID BL_INFO in Folder: {path}\n')
                    err = True
                    continue
                else:
                    addon_list.append(
                        (name, data_mod_category, data_mod_name, data_mod_version))  # list of parameters to sort
                

        # ----------end loop

        if addon_list:
            installed = []

            addon_path = bpy.utils.user_resource('SCRIPTS', path="addons")
            # check only user addons enabled!
            for mod_name, path in bpy.path.module_names(addon_path):
                if mod_name in context.preferences.addons.keys():
                    try:
                        mod = sys.modules[mod_name]
                    except KeyError as ex:
                        # fake modules was really a bad idea in Blender
                        print(
                            f'\n===> INVALID BL_INFO in Installed Addon: {mod_name}.\n{ex}\n')
                        err = True
                        continue
                    else:
                        installed.append(
                            (mod.__name__, mod.bl_info.get('category', 'User'), mod.bl_info['name'],
                             mod.bl_info.get('version', (0, 0, 0))))
            # open a file to write to
            if context.scene.print_result_bridge:
                filename = os.path.join(dirpath, "installed.txt")
                with open(filename, 'w') as file:
                    file.write(str(dirpath)+"\n\nInstalled addons:\n\n")

                    for a in addon_list:
                        if a in installed:
                            file.write(", ".join(str(e) for e in a)+"\n")
                            print(", ".join(str(e) for e in a))
                bpy.ops.file.refresh()
            else:
                for a in addon_list:
                    if a in installed:
                        print(", ".join(str(e) for e in a))

                print(
                    "\nFile name     |      category     |      name     |      version\n")

            dirpath = context.space_data.params.directory.decode("utf-8")
            filepath = os.path.join(dirpath, "installed.txt")
            if os.path.exists(filepath) and context.scene.print_result_bridge:
                message1 = "installed.txt added to this folder"
                box = True

            else:
                import platform
                if platform.system() == 'Windows':
                    open_console()
                    message1 = ''
                    box = False
                else:
                    box = True
                    message1 = 'Result in Console'

            reported(self, err, message='DONE', message1=message1,
                     title='Message:', box=box)

        else:
            reported(self, err, message='0 result', title='Message:')

        return {'FINISHED'}


class OPEN_OT_Installed(bpy.types.Operator):
    bl_idname = "open.installed"
    bl_label = "Open installed"
    bl_option = {'INTERNAL'}

    prop: bpy.props.EnumProperty(items=[(
        'open', 'open', 'open'), ('browse', 'browse', 'browse'), ('del', 'del', 'del')])
    file: bpy.props.StringProperty()
    dirpath: bpy.props.StringProperty()

    def execute(self, context):

        filepath = os.path.join(self.dirpath, self.file)
        if os.path.exists(filepath):

            if self.prop == 'open':
                subprocess.Popen(f'explorer / open, {filepath}')  # open?
            elif self.prop == 'browse':
                subprocess.Popen(f'explorer /select, {filepath}')  # open?
            else:
                os.remove(filepath)
                bpy.ops.file.refresh()

        return {'FINISHED'}


# ----------------------------- BROWSER --------------------------------------

bpy.types.Scene.print_result_bridge = bpy.props.BoolProperty(default=True)


class INSTALLER_OT_FileBrowser(bpy.types.Operator, ImportHelper):
    """Install addon(s) from a browser"""
    bl_idname = "installer.file_broswer"
    bl_label = "Install/Reload/Run"

    filter_glob: bpy.props.StringProperty(
        default='*.py;*.zip',
        options={'HIDDEN'},
        subtype='FILE_PATH'  # to be sure to select a file
    )
    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    directory: bpy.props.StringProperty(
        subtype='DIR_PATH')  # to have the directory path too

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
        default=False, update=update_print_result)

    install_folder: bpy.props.BoolProperty(default=False, get=get, set=set, update=update_install_folder,
                                           name="Install From Folder")

# ---------- browser ui props
    update_versions: bpy.props.BoolProperty(
        default=True, name="Update Versions")

    arrow0: bpy.props.BoolProperty()  # tabs
    arrow1: bpy.props.BoolProperty()

    def update_enable_inst(self, context):
        if self.enable_inst:
            bpy.ops.file.execute("INVOKE_DEFAULT")

    enable_inst: bpy.props.BoolProperty(
        default=False, update=update_enable_inst)

    def execute(self, context):
        print('\n' + '*'*50 + ' ADDON INSTALLER|SCRIPT RUNNER ' + '*'*50 + '\n')

# ---------------------- addon installation from folder

        dirpath = Path(self.directory)
        dirname = os.path.basename(dirpath)
        addon_path = bpy.utils.user_resource('SCRIPTS', path="addons")
        err = False
        from_folder = False
        addon_list = []
        names = []
        ignored = []
        name1 = ''
        files = [] if self.enable_inst else self.files

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
                    print(f' INVALID BL_INFO: {init}\n')
                    reported(self, err, message='INVALID BL_INFO', type='ERROR')
                    return {'CANCELLED'}

                addon_list.append(
                    [data_mod_category, data_mod_name, data_mod_version, data_mod_name, init])


# ---------------------- addon installation from files/script running

        else:
            if self.enable_inst:
                print('*'*30 + ' INSTALLATION FROM LIST ' + '*'*30 + '\n')
                print('N.B:install.txt must have 1 name.zip or.py by line\n')
                filepath = os.path.join(dirpath, "install.txt")
                with open(filepath, 'r') as file:
                    for line in file:
                        element = line[:-1]  # remove \n
                        element = element.strip()
                        if element and "Advanced_Addons_Installer" not in element and element.endswith((".py", ".zip")):
                            files.append(Path(element))
                        else:
                            if element:
                                print(
                                    f'\n===>{element} Not taken into account\n')
                                err = True
                                ignored.append(element)
                self.enable_inst = False

            for f in files:
                path = os.path.join(dirpath, f.name)
                name = Path(path).stem
                names.append(name)
                data = []
                body_info = None

                if not os.path.exists(path):
                    self.report(
                        {'WARNING'}, f'WRONG PATH {path}, check your selection')
                    show_message_box(
                        message=f'WRONG PATH {path}, check your selection', title="WARNING", icon='ERROR')
                    return {'CANCELLED'}

                if Path(path).suffix == '.py':
                    data, err = open_py(path, err)

                elif Path(path).suffix == '.zip':
                    data, err = open_zip(path, err)

                # else:  # .txt
                    # ignored.append(f.name)
                    # continue

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
                        show_message_box(
                            message="SELECT 1 FILE ONLY IF SCRIPT", title="WARNING", icon='ERROR')

                        return {'CANCELLED'}
                    
                    script = run_script(self, path, dirpath, name)

                    return {'FINISHED'}

        # not in the precedent loop to not repeat same operations for each file
        greatest = []
        lower_versions = []
        dont_installed = []
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
            dont_installed = [g for g in greatest for addon in addon_utils.modules(refresh=False)
                             if (g[0] == addon.bl_info.get('category', 'User')
                                 and g[1] == addon.bl_info['name']
                                 and g[2] < addon.bl_info.get('version', (0, 0, 0)))]

            for n in dont_installed:
                greatest.remove(n)

            # remove <= installed version
            to_remove = [addon for addon in addon_utils.modules(refresh=False) for g in greatest
                         if (addon.bl_info.get('category', 'User') == g[0]
                             and addon.bl_info['name'] == g[1]
                             and (addon.bl_info.get('version', (0, 0, 0)) < g[2]
                                  or (addon.bl_info.get('version', (0, 0, 0)) == g[2]
                                      and addon.__name__ != g[3])))]

            for removed in to_remove:
                try:
                    bpy.ops.preferences.addon_remove(
                        module=removed.__name__)

                except:
                    err = True
                    print(
                        f"\n===> ERROR REMOVING PREVIOUS VERSION {removed.__name__}\n")

            ignored.extend([(i[1], i[2]) for i in dont_installed])
            ignored.extend([(i[1], i[2]) for i in lower_versions])

        else:  # no update

            my_list = [addon for addon in addon_utils.modules(refresh=False) for a in addon_list
                       if (addon.bl_info['name'] == a[1]
                           and addon.bl_info.get('category', 'User') == a[0])]
            for a in my_list:
                bpy.ops.preferences.addon_disable(module=a.__name__)

            # greatest = addon_list  # this is not "greatest" but we need this name after

        addon_list_cpy = addon_list[:]
        for add in addon_list:
            name1 = add[3]
            version = add[2]
            path = add[4]

            dest = os.path.join(addon_path, data_mod_name)
            name1 = name1 if not from_folder else data_mod_name

            # disable #usefull?
            try:
                bpy.ops.preferences.addon_disable(module=name1)

            except:
                err = True
                print(
                    f"\n===> ERROR DISABLING PREVIOUS VERSION of {name1}\n")

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
                    print(f"\n===> COULDN'T INSTALL {name1}\n")

            # enable
            try:
                if Path(path).suffix == '.zip':

                    # changing the name of a zip, the name of the first subfolder is different. when doing enable, name is the name of the subfolder...
                    with ZipFile(path, 'r') as f:
                        names = [info.filename for info in f.infolist()
                                 if info.is_dir()]
                    if names:
                        namezip = os.path.split(names[0])[0]
                        # namezip = names[0].split("/")[0]
                    else:
                        namezip = name1

                    bpy.ops.preferences.addon_enable(module=namezip)
                else:
                    bpy.ops.preferences.addon_enable(module=name1)

            except:
                addon_list_cpy.remove(add)
                bpy.ops.preferences.addon_remove(module=name1)  # clean it
                err = True
                print(f"\n===> COULDN'T ENABLE {name1} (not installed)\n")
        if not from_folder:
            message = f'{len(to_remove)} REMOVED, {len(addon_list_cpy)} INSTALLED/RELOADED, {len(ignored)} IGNORED'
            reported(self, err, message=message, message1='/some ERRORS (Console)')
        else:
            message = f'===> FROM FOLDER: INSTALLED/RELOADED {[(i[1],i[2]) for i in addon_list_cpy]}\n'
            self.report({'INFO'}, message)

        print('\n' + '_'*80 + '\n')
        if not from_folder:
            print(
                f'{len(to_remove)} REMOVED, {len(addon_list_cpy)} INSTALLED/ENABLED, {len(ignored)} IGNORED')
            print(f'===> IGNORED {ignored}')
            print(
                f"===> REMOVED {[(i.bl_info['name'], i.bl_info['version']) for i in to_remove]}")
            print(
                f'===> INSTALLED/RELOADED {[(i[1],i[2]) for i in addon_list_cpy]}\n')
        else:
            print(
                f'===> FROM FOLDER: INSTALLED/RELOADED {[(i[1],i[2]) for i in addon_list_cpy]}\n')           

        return {'FINISHED'}

    def draw(self, context):

        # header(self, context, factor=0.9)

        layout = self.layout
        if self.install_folder:
            row = layout.row()
            row.prop(self, "update_versions")

            layout.label(text="INSTALL FOLDER AS AN ADDON")

        else:
            dirpath = context.space_data.params.directory.decode("utf-8")
            filepath = os.path.join(dirpath, "installed.txt")
            filepath1 = os.path.join(dirpath, "install.txt")

            def pyzip(dirpath):
                for file in os.listdir(dirpath):
                    if file.endswith(('.py', '.zip')):
                        return True

            if pyzip(dirpath):
                row = layout.row()
                row.prop(self, "update_versions")
                layout.label(text="Select file(s) and Press Install")
                layout.label(text='')
                layout.label(text="Other Operations:")
                row = layout.row(align=True)
                icon = "TRIA_DOWN" if self.arrow0 else "TRIA_UP"
                row.prop(self, "arrow0", text="", icon=icon, toggle=False)
                row.label(text='INSTALLED ADDONS in folder')
                if self.arrow0:
                    row = layout.row(align=True)
                    sub = row.row()
                    sub.scale_x = 0.5
                    sub.operator("is.installed", text="PRINT")
                    label = 'to File' if self. print_result else 'to Console'
                    row.prop(self, "print_result",
                             text=label)
                    if os.path.exists(filepath):
                        layout.label(text='"installed.txt": EXISTS')
                        row = layout.row(align=True)
                        op1 = row.operator("open.installed", text="OPEN")
                        op1.prop = 'open'
                        op1.file = 'installed.txt'
                        op1.dirpath = dirpath

                        op2 = row.operator("open.installed", text="(OS)BROWSE")
                        op2.prop = 'browse'
                        op2.file = 'installed.txt'
                        op2.dirpath = dirpath

                        op3 = row.operator("open.installed", text="DEL")
                        op3.prop = 'del'
                        op3.file = 'installed.txt'
                        op3.dirpath = dirpath
                    layout.label(text='')

                row = layout.row(align=True)
                icon = "TRIA_DOWN" if self.arrow1 else "TRIA_UP"
                row.prop(self, "arrow1", text="", icon=icon, toggle=False)
                row.label(text='INSTALL FROM LIST')  # bool
                if self.arrow1:
                    message = '"install.txt": IN FOLDER'
                    message1 = '"install.txt": NOT IN FOLDER'
                    label = message if os.path.exists(filepath1) else message1
                    layout.label(text=label)
                    row = layout.row(align=True)
                    row.operator("list.all", text='', icon='COLLAPSEMENU')
                    row.label(text='"install.txt" from All files in folder')

                    if os.path.exists(filepath1):
                        split = layout.split(factor=0.7)
                        row = split.row(align=True)
                        # row = layout.row(align=True)
                        op1 = row.operator("open.installed", text="OPEN")
                        op1.prop = 'open'
                        op1.file = 'install.txt'
                        op1.dirpath = dirpath

                        op2 = row.operator("open.installed",
                                           text="BROWSE")
                        op2.prop = 'browse'
                        op2.file = 'install.txt'
                        op2.dirpath = dirpath

                        op3 = row.operator("open.installed",
                                           text="DEL")
                        op3.prop = 'del'
                        op3.file = 'install.txt'
                        op3.dirpath = dirpath
                        split = layout.split(factor=0.7)

                        if os.path.exists(filepath1):
                            row = split.row(align=True)
                            row.prop(self, "enable_inst",
                                     text="INSTALL FROM LIST", toggle=True)


# ----------------------------- INSTALL/RELOAD FROM TEXT EDITOR -----------------------------

# checked
class INSTALLER_OT_TextEditor(bpy.types.Operator):
    """install addon from text editor (+option reload ext file) """
    bl_idname = "installer.text_editor"
    bl_label = "Install Addon from Text Editor"
    
    reload : bpy.props.BoolProperty()

    def execute(self, context):

        err = False
        _text = context.space_data.text

        if _text:

            print('\n' + '*'*50 +
                  ' INSTALL|RELOAD FROM TEXT EDITOR ' + '*'*50 + '\n')

            ext_path = _text.filepath
            addon_path = bpy.utils.user_resource('SCRIPTS', path="addons")
            addon_dir = os.path.dirname(ext_path)

            if ext_path and addon_dir!=addon_path:
                if _text.is_modified and self.reload: #!= on disk
                    bpy.ops.text.resolve_conflict(resolution='RELOAD')

                name_ext = os.path.split(ext_path)[-1]
                name = name_ext[:-3]
                assert os.path.exists(ext_path), f'\n INVALID PATH {ext_path}\n'
                assert ext_path.endswith(('.py', '.txt')), f'\n WRONG EXTENSION {ext_path}\n'
                data, _ = open_py(ext_path)
                body_info, ModuleType, ast, body = use_ast(ext_path, data)
                assert body_info, f'\n "{name}" has No BL_INFO\n'
                try:
                    data_mod_name, data_mod_category, data_mod_version = get_module_infos(
                        name, ModuleType, ast, body)
                except:
                    print(f'\n===> "{name}" has INVALID BL_INFO\n')
                    return {'CANCELLED'}
                _text['ext_path'] = ext_path

            else:
                name_ext = _text.name
                assert name_ext, f'\n No Text Name \n'
                name = name_ext[:-3]
                split = name_ext.split(".")
                if len(split)==1 and split[0] == 'Text' or len(split)==2 and split[0] == 'TEXT' and split[-1].is_digit:                    
                    self.report(
                        {'ERROR'}, 'Give a name to your addon (not "Text.")')
                    return {'CANCELLED'}
                # if same addon entered twice in text editor, name is addon.py.001
                if not name_ext.endswith('.py'):
                    parts = name_ext.split(".")
                    if len(parts) > 2 and parts[-2] == 'py':
                        parts.pop()
                        name_ext = ".".join(parts)
                    else:
                        name_ext += '.py'  # .py missing in text editor name
                    name = name_ext[:-3]    

                addon = False
                split = []
                word=""
                for line in _text.lines:
                    if line.body.startswith("bl_info"):
                        addon = True
                    if "name" in line.body or 'name' in line.body:
                        parts = [x.strip().strip(',"').strip(",'") for x in line.body.split(":")]
                        break

                idx = parts.index('name')
                data_mod_name = parts[idx+1]
                data_mod_name = data_mod_name.lower().replace(" ","_")
                assert addon, f'\n "{name}" has no BL_INFO\n'
                
            # remove previous version
            to_remove = [addon for addon in addon_utils.modules(refresh=False)
                             if data_mod_name == addon.bl_info['name']
                                 and addon_utils.check(addon.__name__)[0]]
            # disable
            bpy.ops.preferences.addon_disable(module=name)
            # remove
            [bpy.ops.preferences.addon_remove(module= addon.__name__) for addon in to_remove] 
            # copy to addon folder
            full_path = os.path.join(addon_path, name_ext)                
            bpy.ops.text.save_as(filepath=full_path, check_existing=False)        
            # refresh
            refresh_addon(context)
            # enable
            bpy.ops.preferences.addon_enable(module=name)

            self.report({'INFO'}, "Installed/Reloaded: " + name)
            
            if ext_path:
                bpy.ops.text.save_as(filepath=ext_path, check_existing=False)

        else:
            self.report({'WARNING'}, "No Text file in Text Editor")

        return {'FINISHED'}


class ADDON_OT_Cleaner(bpy.types.Operator):
    bl_idname = "addon.cleaner"
    bl_label = "addon cleaner"
    bl_description = "Clean Lower Versions (if duplicates)"

    def execute(self, context):

        # search dupplicates addon and old versions in all addons to keep only last update
        my_list = [(addon.bl_info.get('category', 'User'), addon.bl_info['name'], addon.bl_info.get('version', (0, 0, 0)), addon.__name__)
                   for addon in addon_utils.modules(refresh=False)]  # tuple with 4 values

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


class ADDON_OT_missin_script_remove(bpy.types.Operator):
    bl_idname = "addon.missin_script_remove"
    bl_label = 'clean up "missing script"'
    bl_description = "remove missing script warnings"

    def execute(self, context):

        # space_userpref.py 2026, 1829

        # mods = [mod for mod in addon_utils.modules(refresh=False)]

        addons = context.preferences.addons
        used_ext = {mod_name for mod_name in addons.keys()}
        module_names = [
            mod.__name__ for mod in addon_utils.modules(refresh=False)]
        # module_names = {mod.__name__ for mod in mods}
        missing_modules = [ext for ext in used_ext if ext not in module_names]
        for name in missing_modules:
            bpy.ops.preferences.addon_disable(module=name)

        print(f"\nMISSING MODULES DISABLED: {missing_modules}\n")
        label = f'{len(missing_modules)} "missing script" erased /see Console' if missing_modules else f'{len(missing_modules)} "missing script" Found'

        self.report({'INFO'}, label)

        return {'FINISHED'}


class ADDON_OT_fake_remove(bpy.types.Operator):
    bl_idname = "addon.fake_remove"
    bl_label = "fake modules remove"
    bl_description = "Remove (User) Fake Modules"

    def execute(self, context):

        addon_path = bpy.utils.user_resource('SCRIPTS', path="addons")
        names = []

        for name in os.listdir(addon_path):

            name_path = os.path.join(addon_path, name)

            if os.path.isfile(name_path) and Path(name).suffix == '.py':
                try:
                    with open(name_path, "r", encoding='UTF-8') as f:
                        data, err = get_bl_info_dic(f, name_path)
                        if not data:
                            print('===> FAKE-MODULE REMOVED: ',  name)
                            names.append(name)
                            os.remove(name_path)
                except EnvironmentError as ex:
                    print("Error opening file:", name_path, ex)
                    continue

            if os.path.isdir(name_path):
                if "__init__.py" in os.listdir(name_path) and name != "__pycache__":
                    name_path1 = Path(os.path.join(
                        addon_path, name, "__init__.py"))
                    data, err = open_py(name_path1)
                    body_info, *_ = use_ast(name_path1, data)
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
            {'INFO'}, f'{len(names)} FAKE(S) MODULE REMOVED, see Console')

        return {'FINISHED'}


class ADDON_OT_last_installed(bpy.types.Operator):
    bl_idname = "addon.print_last_installed"
    bl_label = "Last installed addons "
    """sort addons by time (result in console)"""

    def execute(self, context):

        print('\n' + '*'*20 + ' sorted last installed addonsR ' + '*'*20 + '\n')
        installed = []

        addon_path = bpy.utils.user_resource('SCRIPTS', path="addons")
        addons = context.preferences.addons
        for mod_name, path in bpy.path.module_names(addon_path):
            if mod_name in addons.keys():
                try:
                    mod = sys.modules[mod_name]
                    installed.append(
                        (mod.__name__, mod.bl_info.get('category', 'User'), mod.bl_info['name'], mod.bl_info.get('version', (0, 0, 0)), mod.__time__))
                except KeyError:
                    pass
        last_installed = sorted(installed, key=lambda x: (x[4]))

        last_installed_date = [(i, j, k, l, ctime(m))
                               for i, j, k, l, m in last_installed]

        for last in last_installed_date:
            print(last)

        print("\nFile name     |      category     |      name     |      version      |      date\n")

        import platform
        if platform.system() == 'Windows':
            open_console()
        else:
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


class ADDON_OT_installed_list(bpy.types.Operator):
    """generates addons list"""
    bl_idname = "addon.installed_list"
    bl_label = "generates addons list"

    def execute(self, context):

        addons_path = bpy.utils.user_resource('SCRIPTS', path="addons")
        filepath = os.path.join(addons_path, "Enabled.txt")
        addons = context.preferences.addons

        with open(filepath, 'w') as file:
            for mod_name, path in bpy.path.module_names(addons_path):
                if mod_name in addons.keys():
                    file.write(mod_name+"\n")

        bpy.ops.open.installed(
            prop='browse', file="Enabled.txt", dirpath=addons_path)

        return {'FINISHED'}


class ADDON_OT_disable_all(bpy.types.Operator):
    """disable all addons"""
    bl_idname = "addon.disable_all"
    bl_label = "create list & disable all addons"

    def execute(self, context):

        # lets clean up "missing scripts"
        bpy.ops.addon.missin_script_remove()

        addons_path = bpy.utils.user_resource('SCRIPTS', path="addons")
        filepath = os.path.join(addons_path, "Enabled.txt")
        addons = context.preferences.addons

        with open(filepath, 'w') as file:
            for mod_name in list(addons.keys()):
                file.write(mod_name+"\n")

        enablist = [addon.module for addon in addons]
        for addon in addon_utils.modules(refresh=False):
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

        addons_path = bpy.utils.user_resource('SCRIPTS', path="addons")
        filepath = os.path.join(addons_path, "Enabled.txt")

        if not os.path.exists(filepath):
            self.report({'ERROR'}, f'Weird, Enabled.txt has been deleted')
            return {'CANCELLED'}

        liste = []
        with open(filepath, 'r') as file:
            for line in file:
                element = line[:-1]  # remove \n
                liste.append(element)

        for addon in addon_utils.modules(refresh=False):
            if addon.__name__ in (liste) and "Advanced_Addons_Installer" not in addon.__name__:
                try:
                    bpy.ops.preferences.addon_enable(module=addon.__name__)
                except:
                    err = True
                    message = f"COULDN'T ENABLE {addon.__name__} "
                    print(f"\n ===>{message}\n")
                    reported(self, err, message=message)
        return {'FINISHED'}


class LIST_OT_all(bpy.types.Operator):
    """you can then edit it..."""
    bl_idname = "list.all"
    bl_label = "list of all py_zip in folder"
    bl_option = {'INTERNAL'}

    def execute(self, context):

        dirpath = context.space_data.params.directory.decode("utf-8")
        filepath = os.path.join(dirpath, "install.txt")

        with open(filepath, 'w') as f:  # TODO: must list dir too with valid bl_info inside
            for file in os.listdir(dirpath):
                if file.endswith(('.py', '.zip')):
                    f.write(file+"\n")

        bpy.ops.file.refresh()

        return {'FINISHED'}


class OPEN_OT_multi_files(bpy.types.Operator, ImportHelper):
    """open several files in text editor"""
    bl_idname = "open.multi_files"
    bl_label = "open several files in text editor"
    # bl_option = {'INTERNAL'}

    filter_glob: bpy.props.StringProperty(
        default='*.py',
        options={'HIDDEN'},
        subtype='FILE_PATH'  # to be sure to select a file
    )
    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    directory: bpy.props.StringProperty(
        subtype='DIR_PATH')  # to have the directory path too

    def execute(self, context):

        dirpath = Path(self.directory)
        names = [text.name for text in bpy.data.texts[:]]
        for file in self.files:
            path = os.path.join(dirpath, file.name)
            for n in names:
                if file.name == n:
                    text = context.space_data.text = bpy.data.texts[n]
                    bpy.ops.text.unlink()           
            bpy.ops.text.open(filepath=path)

        return {'FINISHED'}

    def draw(self, context):

        # header(self, context, factor=0.9)

        layout = self.layout
        layout.label(text="Caution: files with same name")
        layout.label(text="                in text editor")
        layout.label(text="                will be replaced")
        

# ---------------------------------------- Menus ----------------------------------------


class ADDON_MT_enable_disable_menu(bpy.types.Menu):
    bl_label = 'Enable/Disable All Addons'

    def draw(self, context):
        layout = self.layout
        layout.operator("addon.disable_all",
                        text="Disable All")
        layout.operator("addon.enable_from_list",
                        text="Re-enable")
        layout.operator("addon.installed_list",
                        text='Do a List of enabled')


class ADDON_MT_management_menu(bpy.types.Menu):
    bl_label = 'addon management'

    def draw(self, context):
        layout = self.layout
        layout.operator("installer.file_broswer",
                        text="Install/Reload Addon(s)", icon='FILEBROWSER')


def draw0(self, context):

    layout = self.layout
    # layout.separator(factor=1.0)
    layout.operator("open.multi_files",
                    text="Open multifiles", icon='FILEBROWSER')


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
                    text="Addon from Text Editor", icon='COLLAPSEMENU').reload=False
    layout.operator("installer.text_editor",
                    text="Addon from Text Ed. [Reload]", icon='COLLAPSEMENU').reload=True                    
    layout.operator("open.user_addons", text='Open User addons',
                    icon='FOLDER_REDIRECT')


def draw2(self, context):

    layout = self.layout
    layout.operator(RESTART_OT_blender.bl_idname,
                    text="Restart Blender")


def update_switch(self, context):
    if self.switch:
        bpy.ops.addon.enable_from_list()
    else:
        bpy.ops.addon.disable_all()


bpy.types.Scene.switch = bpy.props.BoolProperty(
    default=True, update=update_switch, description='disable/enable all addons')


def header(self, context, factor=1):

    layout = self.layout
    split = layout.split(factor=factor)
    row = split.row()
    row.operator(ADDON_OT_last_installed.bl_idname, text='last installed', icon='MOD_TIME')
    scene = context.scene
    label = "Disable All" if scene.switch else "Enable All"
    row.prop(scene, "switch", text=label, toggle=True, invert_checkbox=True)
    row.operator(ADDON_OT_fake_remove.bl_idname,
                 text="clean fake modules", icon='TRASH')
    row.operator(ADDON_OT_missin_script_remove.bl_idname,
                 text="clean missing cripts", icon='MATCLOTH')
    row.operator(ADDON_OT_Cleaner.bl_idname,
                 text="clean lower versions addons", icon='RIGHTARROW')


classes = (INSTALLER_OT_FileBrowser, INSTALLER_OT_TextEditor,
           ADDON_OT_Cleaner, ADDON_OT_fake_remove,
           ADDON_MT_management_menu, ADDON_OT_last_installed,
           RESTART_OT_blender,
           ADDON_OT_installed_list, ADDON_OT_disable_all,
           ADDON_OT_enable_from_list, ADDON_MT_enable_disable_menu,
           OPEN_OT_Installed, IS_OT_Installed, LIST_OT_all,
           ADDON_OT_missin_script_remove,
           OPEN_OT_multi_files,
           )

addon_keymaps = []


def register():

    # classes
    for c in classes:
        bpy.utils.register_class(c)

    # menus entries

    bpy.types.TEXT_MT_text.append(draw1)
    bpy.types.TEXT_MT_text.prepend(draw0)
    if bpy.app.version >= (3, 0, 0):
        bpy.types.TOPBAR_MT_blender.append(draw)
    else:
        bpy.types.TOPBAR_MT_app.append(draw)
    bpy.types.TOPBAR_MT_file.append(draw2)
    bpy.types.USERPREF_PT_addons.prepend(header)

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
    bpy.types.TEXT_MT_text.remove(draw0)
    if bpy.app.version >= (3, 0, 0):
        bpy.types.TOPBAR_MT_blender.remove(draw)
    else:
        bpy.types.TOPBAR_MT_app.remove(draw)
    bpy.types.TOPBAR_MT_file.remove(draw2)
    bpy.types.USERPREF_PT_addons.remove(header)

    # classes
    for c in classes:
        bpy.utils.unregister_class(c)
