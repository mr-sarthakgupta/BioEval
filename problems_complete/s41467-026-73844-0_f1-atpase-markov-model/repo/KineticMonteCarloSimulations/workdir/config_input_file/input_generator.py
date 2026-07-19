#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 19/04/2023

import numpy as np
from generate_markov_model import *

class Input:
    
    def __init__(self, fileName, confs, v_index, activeConf, angle_cat, jointConfTrans):
        
        self.fileName = fileName
        self.myVariant = MarkovModel(confs, v_index, activeConf, angle_cat, jointConfTrans)
    
    
    def writeVariables(self, values):
        
        with open(self.fileName+".input", "w") as file:
        
            for i in range(len(self.myVariant.varNames)):
                file.write("%-10s%10s%10.4f%10s\n"%("VARIABLE", self.myVariant.varNames[i], values[i], "kT"))
        
        return 0


    def writeSettings(self, N_sample, sim_time, index_init_state, c_ATP, c_ADP, kappa, xi, stepLength, lagTime_rec, fps_rec):
        
        with open(self.fileName + ".input", "a") as file:
        
            file.write("%-10s%12s%16d\n"%("SIMULATION", "N_SAMPLE", N_sample))
            file.write("%-10s%12s%16.2f\n"%("SIMULATION", "SIM_TIME", sim_time))
            file.write("%-10s%12s%16d\n"%("SIMULATION", "INIT_STATE", index_init_state))
            file.write("%-10s%12s%16.1e\n"%("SIMULATION", "C_ATP", c_ATP))
            file.write("%-10s%12s%16.1e\n"%("SIMULATION", "C_ADP", c_ADP))
            file.write("%-10s%12s%16.2e\n"%("SIMULATION", "KAPPA", kappa))
            file.write("%-10s%12s%16.2e\n"%("SIMULATION", "XI", xi))
            file.write("%-10s%12s%16.2e\n"%("SIMULATION", "STEP_LENGTH", stepLength))
            file.write("%-10s%12s%16.2f\n"%("SIMULATION", "LAG_TIME", lagTime_rec))
            file.write("%-10s%12s%16.1e\n"%("SIMULATION", "FPS", fps_rec))
        
        return 0


    def __call__(self,
                 variable_values,
                 N_sample, sim_time, init_state, c_ATP, c_ADP, kappa, xi, stepLength, lagTime_rec, fps_rec):
        
        self.writeVariables(variable_values)

        # Write into the .input file only asymmetric states and transitions
        dict_states = self.myVariant(self.fileName)
        
        index_init_state = dict_states[init_state]
        self.writeSettings(N_sample, sim_time, index_init_state, c_ATP, c_ADP, kappa, xi, stepLength, lagTime_rec, fps_rec)
        
        return 0
