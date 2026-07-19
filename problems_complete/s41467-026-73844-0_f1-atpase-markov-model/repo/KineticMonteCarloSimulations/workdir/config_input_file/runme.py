#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 19/04/2023

import numpy as np
from generate_markov_model import *
from input_generator import Input
import sys
import os


dict_variables = {"G_O":      ["Y", "U", -20.0, 20.0, 0.0, "N"],
                  "G_C":     ["Y", "U", -20.0, 20.0, 0.0, "N"],
                  "G_C*":     ["N", "N", -20.0, 20.0, 0.0, "N"],
                  "AG_BETA":  ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_GAMMA": ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_CHEM":  ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_OT":    ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_OD":    ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_CT":   ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_CD":   ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_C*T":   ["Y", "U", 0.0, 23.0, 6.9, "N"],
                  "AG_C*D":   ["Y", "U", 0.0, 23.0, 6.9, "N"],
                  "BG_OT":    ["Y", "U", -50.0, 0.0, -6.27, "E"],
                  "BG_OD":    ["Y", "U", -50.0, 0.0, -6.40, "E"],
                  "BG_CT":   ["Y", "U", -50.0, 0.0, -12.00, "E"],
                  "BG_CD":   ["Y", "U", -50.0, 0.0, -12.00, "E"], 
                  "BG_C*T":   ["Y", "U", -50.0, 0.0, -12.00, "E"],
                  "BG_C*D":   ["Y", "U", -50.0, 0.0, -12.00, "E"],
                  # an additional half-closed conformation
                  "G_H":      ["Y", "U", -20.0, 20.0, 0.0, "N"],
                  "AG_HT":    ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "AG_HD":    ["Y", "U", 0.0, 23.0, 4.6, "N"],
                  "BG_HT":    ["Y", "U", -50.0, 0.0, -6.27, "E"],
                  "BG_HD":    ["Y", "U", -50.0, 0.0, -6.40, "E"],
                  "IG_120-O":    ["N", "N", -50.0, 0.0, -6.40, "N"]}



file_name = "F1-ATPase"

list_set_index = [2]
#list_c_ATP = [2e-8, 2e-7, 2e-6, 6e-6, 2e-5, 6e-5, 2e-4, 2e-3, 6e-3]
list_c_ATP = [2e-3]#[2e-7, 2e-6, 2e-5, 2e-4, 2e-3]
list_c_ADP = [1e-9]


with open("%s.summary.csv"%file_name, "r") as file:
    lines = file.readlines()

for set_index in list_set_index:
    
  for c_ATP in list_c_ATP:

    for c_ADP in list_c_ADP:

      line = lines[set_index].split(",")
      values = np.array(line[2:2+24], dtype = float)

      dir = "param_file=%s,param_set=%d,[T]=%.2e,[D]=%.2e"%(file_name, set_index, c_ATP, c_ADP)
      k = 1

      while os.path.exists("../%s_%d"%(dir, k)):
        k += 1
      
      os.mkdir("../%s_%d"%(dir, k))
      
      Input(fileName = "../%s_%d/F1-ATPase"%(dir, k), 
            confs = "ohca",
            v_index = 323,
            activeConf = [2],
            angle_cat = 80,
            jointConfTrans = False)(\
                variable_values = values,
                N_sample = 1,
                sim_time = 1.0,#unit: s
                init_state = (80, 1, 2, 3, 1, 0, 0),
                c_ATP = c_ATP,#[ATP] (mol/L)
                c_ADP = c_ADP,#[ADP] (mol/L)
                kappa = 5.0,# spring constant (k_B*T)
                xi = 6.7e-5,# rotational friction drag coefficient (k_B*T*s)
                stepLength = 1.0e-9,
                lagTime_rec = 0.0,
                fps_rec = 1.0e5)
