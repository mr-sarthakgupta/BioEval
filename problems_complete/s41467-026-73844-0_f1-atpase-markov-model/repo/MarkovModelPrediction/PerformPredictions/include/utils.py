#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 23/07/2023

import os
import numpy as np

def prepareWorkDir(dirNameFormat, newWorkDir, *keywords):
    
    dir = dirNameFormat%(keywords)
    
    if newWorkDir == True:
      
        k = 1
    
        while os.path.exists("%s_%d"%(dir, k)):
            k += 1
    
        dir_unique = "%s_%d"%(dir, k)
        os.mkdir(dir_unique)
    
    else:
        
        dir_unique = "%s"%dir
        
        if os.path.exists(dir_unique) is False:
            os.mkdir(dir_unique)

    return dir_unique


def readPara(filePath, lineIndex, work_dir=None):
    
    with open(filePath, "r") as file:
        lines = file.readlines()
    
    if work_dir is not None:
        
        with open("%s/RECORD.txt"%work_dir, "w") as file:

            #file.write(lines[0])
            file.write("#SUMMARY FILE NAME\n")
            file.write("%s\n"%filePath)
            file.write("#SUMMARY FILE READ IN\n")
            file.write(lines[lineIndex])
    
    vecPara = np.array(lines[lineIndex].split(",")[2:2+23], dtype = float)
    
    return vecPara, lines[lineIndex].strip()
