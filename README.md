# Advanced Addons Installer  
## Browser to directly apply things on selection, when confirm  
  
[video of presentation](https://youtu.be/-N1ua8GWvqI)    
  
## 1-install/reload selected ADDON(S)  
 "Update" option (in browser):  
* on: install greater version number. reload if same  
* off: previous version allowed (actual version disabled)  
avoids dupplicates and fake modules  
     
## 2-install folder as an addon  
* detecting  "\_\_init\_\_.py" inside  
  
## 3-install/reload active file from TEXT EDITOR  
if you drag or open a file the original file is saved when the addon is installed
and if you modify the same file from an external text editor when installing the addon 
the file is reloaded. no need to handle this  
![](install_from_text_editor_synchro.gif)  
  
## 4-run scripts (single file .py with no bl_info)  
  
## 5-location and options 
  
-Blender icon menu:  
 *  install/reload addon (allows to put it in all Quick favorites)  
   
-File menu  
* restart (blender)  
  
-in the default blender installer (in properties)  
* last installed addons  
* disable/enable all addons  
* remove fake-modules  
* clean "missing scripts"  
* clean dupplicates and lower versions  
  
-advanced addons installer browser  
* same menu that the one before in blender properties
* Installed addons from folder  
* Install from list   

 -text editor  
  * creates a quick favorite 'Ctrl+Q' 
  * "Addon from text editor" in text menu

N.B you can check messages in the console


