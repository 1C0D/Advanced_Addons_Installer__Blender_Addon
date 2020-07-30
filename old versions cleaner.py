import bpy
import addon_utils
from collections import Counter


MyList=[(addon.bl_info['category'],addon.bl_info['name'], addon.bl_info['version'],addon.__name__) 
        for addon in addon_utils.modules()]
dict = Counter(word for i,j,k,l in MyList for word in [(i,j)])

counter=[(word ,count) for word,count in dict.most_common() if count > 1  ]

version=[]
for i,j,k,l in MyList:
    for u,v in counter:
        if (i,j) == u:
            version.append([i,j,k,l])

##e.g:[['Development', ' A', (1, 8, 3), 'Afghf'], ['Development', ' A', (1, 8, 3), 'A1'], ['Development', ' A', (1, 8, 2), 'A2121']]
version_tri=sorted(version, key=lambda element: (element[1], element[2], element[3]))[0:-1]

for addon in addon_utils.modules():
    for i,j,k,l in version_tri:
        if (addon.bl_info['category'],addon.bl_info['name'],addon.bl_info['version'])== (i,j,k):
            bpy.ops.preferences.addon_remove(module=l)

