#! usr/bin/env python
# -*- coding: utf-8 -*-

from generate_markov_model import *

class Input:
    
    def __init__(self, fileName, confs, v_index, activeConf, angle_cat, jointConfTrans):
        
        self.fileName = fileName
        self.myVariant = MarkovModel(confs, v_index, activeConf, angle_cat, jointConfTrans)
        self.activeConf = activeConf
        
        activeConfStr = ""
        for each in activeConf:
            activeConfStr += confs[each]
        self.title = "%s-%s"%(self.myVariant.version, activeConfStr)


    def writeVariables(self, dict_variables):
        
        dict_search = dict(Y = "TRUE",
                           N = "FALSE")
        dict_distr = dict(U = "UNIFORM",
                          G = "GAUSSIAN",
                          N = "NONE")
        dict_unit = dict(N = "kT",
                         E = "kcal/mol")
        
        N_var = 0
        
        with open(self.fileName+".input", "a") as file:
            
            for var in self.myVariant.varNames:
                if dict_variables[var][0] == "Y":
                    N_var += 1
            file.write("%-10s%10d\n"%("N_VARIABLE", N_var))

            for var in self.myVariant.varNames:
                file.write("%-10s%10s%10s%10s"%("VARIABLE", var, dict_search[dict_variables[var][0]], dict_distr[dict_variables[var][1]]))
                if dict_variables[var][0] == "Y":
                    file.write("%10.2f%10.2f%10.2f"%(dict_variables[var][2], dict_variables[var][3], dict_variables[var][4]))
                else:
                    file.write("%30.2f"%(dict_variables[var][4]))
                file.write("%10s\n"%(dict_unit[dict_variables[var][5]]))
        
        return 0
    
    
    def writeExpData(self, data_exp):
        
        with open(self.fileName+".input", "a") as file:
        
            file.write("%-10s%10d\n"%("N_EXPDATA", len(data_exp)))
            for i in range(len(data_exp)):
                file.write("%-10s%10s%10.1e%10.1e%12.3e\n"%("EXPDATA", "GROUP"+str(i+1), data_exp[i][0], data_exp[i][1], data_exp[i][2]))
        
        return 0


    def writeSettings(self, mode, N_initGuess, N_indepTrial, N_search, search_std, f_shrink, N_goodSetStep, N_maxStep, score_goodSetCriterion, errorbar, std_zeta, std_eta, occ_on, std_occ, constHydrEnergy):
        
        with open(self.fileName + ".input", "a") as file:
        
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "MODE", mode))
            
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "N_INIT", N_initGuess))
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "N_TRIAL", N_indepTrial))
            
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "N_SEARCH", N_search))
            file.write("%-10s%20s%10.2f\n"%("OPTIMIZING", "STD_SEARCH", search_std))
            file.write("%-10s%20s%10.2f\n"%("OPTIMIZING", "SHRINK_FACTOR", f_shrink))
            
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "N_STEP_GOODSET", N_goodSetStep))
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "N_STEP_MAX", N_maxStep))
            file.write("%-10s%20s%10.0e\n"%("OPTIMIZING", "SCORE_CRITERION", score_goodSetCriterion))
            file.write("%-10s%20s%10.0e\n"%("OPTIMIZING", "ERRORBAR", errorbar))
            
            file.write("%-10s%20s%10.2f\n"%("OPTIMIZING", "STD_ZETA", std_zeta))
            file.write("%-10s%20s%10.2f\n"%("OPTIMIZING", "STD_ETA", std_eta))
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "OCC_ON", occ_on))
            file.write("%-10s%20s%10.2f\n"%("OPTIMIZING", "STD_OCC", std_occ))
            
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "CONST_HYDR_ENERGY", constHydrEnergy))
          
            file.write("%-10s%20s%10d\n"%("OPTIMIZING", "N_ACTIVE_CONF", len(self.activeConf)))
            file.write("%-10s%20s"%("OPTIMIZING", "ACTIVE_CONF"))
            for each in self.activeConf:
                file.write("%4d"%each)
            file.write("\n")
        
        return 0


    def __call__(self,
                 dict_variables, data_exp,
                 mode, N_initGuess, N_indepTrial, N_search, search_std, f_shrink, N_goodSetStep, N_maxStep, score_goodSetCriterion, errorbar, std_zeta, std_eta, occ_on, std_occ, constHydrEnergy):
        
        with open(self.fileName + ".input", "w") as file:
            file.write("%-10s%15s\n"%("VERSION", self.title))
        
        self.writeVariables(dict_variables)
        self.writeExpData(data_exp)

        # Write into the .input file only asymmetric states and transitions
        self.myVariant(self.fileName)

        self.writeSettings(mode, N_initGuess, N_indepTrial, N_search, search_std, f_shrink, N_goodSetStep, N_maxStep, score_goodSetCriterion, errorbar, std_zeta, std_eta, occ_on, std_occ, constHydrEnergy)

        return 0
