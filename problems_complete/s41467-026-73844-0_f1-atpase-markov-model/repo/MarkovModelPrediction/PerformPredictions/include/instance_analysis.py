#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 25/12/2024

import numpy as np
from include.instance import Instance


class InstanceAnalysis:

    def __init__(self, model, vec_para, workDir = "", gbInteractionEnergy=0.):
        
        self.model = model
        self.vec_para = vec_para
        self.para_label = 0
        self.workDir = workDir
        self.instance = Instance(model, gbInteractionEnergy)
        
        self.__bindStateAbbrev = {0: "T", 1: "D", 2: "E"}
        self.__confStateAbbrev = {0: "o", 1: "h", 2: "c", 3: "c*"}


    def updateParameters(self, vec_para, para_label):

        self.vec_para += -self.vec_para + vec_para
        self.para_label = para_label
    

    def __analyzeSteadyState(self, cT, cD, summaryFile=None):
        
        self.instance.set_trans_rate_matrix(self.vec_para, cT, cD)
        
        self.instance.calculate_steady_state_properties()
        self.instance.analyzeRotDwells()
        self.instance.analyzeSteadyState_betaConfig()
        
        #self.instance.write_st_distr("%s/SteadyState_Distr_(%.1e,%.1e).csv"%(self.workDir, cT, cD))
        
        #self.instance.analyzeSteadyState_betaConfig("%s/SteadyState_BetaConfig_(%.1e,%.1e).csv"%(self.workDir, cT, cD))
        #self.instance.analyzeSteadyState_NucExchange("%s/SteadyState_Flux_(%.1e,%.1e).csv"%(self.workDir, cT, cD),
        #                                       "%s/SteadyState_NucExchange_(%.1e,%.1e).csv"%(self.workDir, cT, cD))
        
        #print("Steady state ([ATP] = %.2e, [ADP] = %.2e)"%(cT, cD))
        #print("k_cat = %.4f, k_rot = %.4f"%(self.instance.k_cat, self.instance.k_rot))
        
        if summaryFile is None:
            return
            
        summaryFile.write("%.2f,%.2f,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e"%(\
                          np.log10(cT), np.log10(cD),
                          self.instance.report["k_cat"], self.instance.report["k_rot"],
                          self.instance.report["occ_tot"], self.instance.report["occ_ATP"], self.instance.report["occ_ADP"],
                          self.instance.report["pop_cat"], self.instance.report["pop_wait"]))
            
        for trans in self.model.trans_modes:
            for dwell in self.model.dwells:
                summaryFile.write(",%.6e"%(self.instance.report["%s_%d"%(trans, dwell)]))

        for config in self.instance.betaConfigs:
            summaryFile.write(",%.6e"%(self.instance.betaConfigPop[config]))
                    
        summaryFile.write("\n")
            
        return
    

    
    def __writeTitle(self, file):

        file.write("LOG([ATP]),LOG([ADP]),K_CAT,K_ROT,OCC_TOT,OCC_ATP,OCC_ADP")
        file.write(",POP_CAT,POP_WAIT")

        for trans in self.model.trans_modes:
            for dwell in self.model.dwells:
                file.write(",%s:%d"%(trans, dwell))

        for config in self.instance.betaConfigs:
            file.write(",%d-%s%s%s"%(config[0], 
                                     self.model.dictConfName[config[1]], 
                                     self.model.dictConfName[config[2]], 
                                     self.model.dictConfName[config[3]]))
        
        file.write("\n")
      
        return 0


    def scan_conc_gradient(self, gradient = "ATP", concRange = {"T": np.logspace(-9, 0, 15), "D": [1e-9, 1e-6]}):
        
        if gradient in ["T", "D"]:
        
            c1_label = gradient
            
            if c1_label == "T":
                c2_label = "D"
            
            elif c1_label == "D":
                c2_label = "T"
            
            conc = {"T": 0.0, "D": 0.0}
            
            for c2 in concRange[c2_label]:
                
                conc[c2_label] = c2
                
                with open("%s/SteadyStates_c%s=%.2e_set=%d.csv"%(self.workDir, c2_label, c2, self.para_label),"w") as file:
                    self.__writeTitle(file)
                    
                    for c1 in concRange[c1_label]:
                        
                        conc[c1_label] = c1
                        
                        self.__analyzeSteadyState(cT = conc["T"], cD = conc["D"], summaryFile = file)
        
        else:
                
            with open("%s/SteadyStates_mix_set=%d.csv"%(self.workDir, self.para_label),"w") as file:
                self.__writeTitle(file)

                for c in concRange["T"]:
                    self.__analyzeSteadyState(cT = c, cD = c, summaryFile = file)
        
        return 0