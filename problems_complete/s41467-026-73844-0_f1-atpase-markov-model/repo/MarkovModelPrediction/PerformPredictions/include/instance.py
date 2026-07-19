#!usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 25/12/2024

import numpy as np
from itertools import product
from collections import OrderedDict

class Parameter:
    
    def __init__(self, numConf):

        self.__attFreq = 1.0e9
        self.__numConf = numConf
        
        self.parameters = dict()
        self.rate_constants = dict()
        self.concentrations = {0: 0.0, 1: 0.0}
        
    
    def getParameter(self, vecPara):
        
        for i in range(self.__numConf):
            self.parameters[("BETA", i)] = float(vecPara[i])
        
        self.parameters["CONF"] = self.__attFreq*np.exp(-float(vecPara[self.__numConf]))
        self.parameters["ROT"]  = self.__attFreq*np.exp(-float(vecPara[self.__numConf+1]))
        self.parameters["CHEM"] = self.__attFreq*np.exp(-float(vecPara[self.__numConf+2]))
        
        for i in range(self.__numConf):
            
            for j in range(2):
            
                self.parameters[("BIND", "R", i, j)] = self.__attFreq*np.exp(-float(vecPara[self.__numConf+3+2*i+j]))
                self.parameters[("BIND", "E", i, j)] = float(vecPara[self.__numConf+3+2*self.__numConf+2*i+j])
            
        return
    
    
    def calculateRateConstant(self):
        
        self.rate_constants[("CONF",)] = self.parameters["CONF"]
        self.rate_constants[("ROT",)] = self.parameters["ROT"]
        self.rate_constants[("CHEM",)] = self.parameters["CHEM"]
        
        for each in list(product(range(self.__numConf), [0, 1])):# Binding
            
            self.rate_constants[("BIND", each[0], each[1])] = self.parameters[("BIND", "R", each[0], each[1])]
            self.rate_constants[("UNBIND", each[0], each[1])] = self.parameters[("BIND", "R", each[0], each[1])]/np.exp(-self.parameters[("BIND", "E", each[0], each[1])])

        return
    
    
    def set_values(self, vecPara, c_ATP, c_ADP):
        
        self.concentrations[0] = c_ATP
        self.concentrations[1] = c_ADP
        
        self.getParameter(vecPara)
        self.calculateRateConstant()

        return
        


class Instance:
    
    def __init__(self, model, gbInteractionEnergy=0.):
        
        self.model = model
        self.gbInteractionEnergy = gbInteractionEnergy
        
        self.__stateEnergy = np.zeros(self.model.N)
        self.matrixTransitionRate = np.zeros((self.model.N, self.model.N))
        self.dictTransition = dict()
        
        self.__dictAsyState = {state: self.model.state[state] for state in self.model.state if self.model.state[state] < self.model.N}
        self.__dictAsyState_inverse = {self.__dictAsyState[state]: state for state in self.__dictAsyState}

        self.__chemicalSpace = \
                             [((3, 0, 0), (2, 1, 0)),
                              ((2, 1, 0), (1, 2, 0)),
                              ((1, 2, 0), (0, 3, 0)),
                              ((2, 0, 1), (1, 1, 1)),
                              ((1, 1, 1), (0, 2, 1)),
                              ((1, 0, 2), (0, 1, 2)),#ATP binding
                              ((2, 1, 0), (2, 0, 1)),
                              ((1, 2, 0), (1, 1, 1)),
                              ((0, 3, 0), (0, 2, 1)),
                              ((1, 1, 1), (1, 0, 2)),
                              ((0, 2, 1), (0, 1, 2)),
                              ((0, 1, 2), (0, 0, 3)),#ATP hydrolysis
                              ((2, 0, 1), (3, 0, 0)),
                              ((1, 1, 1), (2, 1, 0)),
                              ((0, 2, 1), (1, 2, 0)),
                              ((1, 0, 2), (2, 0, 1)),
                              ((0, 1, 2), (1, 1, 1)),
                              ((0, 0, 3), (1, 0, 2))]#ADP unbinding

        
        self.__dictPairwiseFlux = dict()# __dictPairwiseFlux[(i, j)] is the stationary state flux from state i to state j
        self.__dictPairwiseNetFlux = dict()
        self.__net_flux = []
        
        self.__chemicalNetFlux = np.zeros(18)
        self.__rotationalNetFlux = np.zeros(2)
        
        self.st_distr = np.zeros(self.model.N)

        self.report = {"k_cat": 0., 
                       "k_rot": 0.,
                       "occ_tot": 0.,
                       "occ_ATP": 0.,
                       "occ_ADP": 0.,
                       "pop_cat": 0.,
                       "pop_wait": 0.,
                       "T_eq": 0.}
        for trans in self.model.trans_modes:
            for dwell in self.model.dwells:
                self.report["%s_%d"%(trans, dwell)] = 0.

        self.betaConfigPop = dict()
        self.betaConfigs = []
        for angle in [self.model.angle_cat, 120]:
            for config in self.model.betaConfig[angle]:
                self.betaConfigs.append((angle, config[0], config[1], config[2]))
                self.betaConfigPop[(angle, config[0], config[1], config[2])] = 0.
        
        return
        

    def __calculateStateEnergy(self):
    # beta conformational energy regarding the binding states
    # Bulk concentration of ATP and ADP influence the free energy by shifting the binding free energy
        
        for i in range(self.model.N):
            
            state = self.model.asyState[i]
            
            for k in range(1, 4):
                
                self.__stateEnergy[i] += self.__pars.parameters[("BETA", state[k])]# beta conf energy
                
                if state[k+3] != 2:
                    
                    self.__stateEnergy[i] += self.__pars.parameters[("BIND", "E", state[k], state[k+3])] - np.log(self.__pars.concentrations[state[k+3]])

            if state[0] == 120 and state[1] == 0:#beta_1 adopts open conformation at 120-degree
                self.__stateEnergy[i] += self.gbInteractionEnergy
        
        return
    
    
    def __generateAsyTransitions(self):
        
        for i in range(self.model.N):
            
            for each in self.model.accSubspace[i]:
                
                if each[1] != "RT":
                
                    if each[1] == "+ATP":
                        self.matrixTransitionRate[i][each[0]] = self.__pars.rate_constants[("BIND", each[2], 0)] * self.__pars.concentrations[0]
                    
                    elif each[1] == "+ADP":
                        self.matrixTransitionRate[i][each[0]] = self.__pars.rate_constants[("BIND", each[2], 1)] * self.__pars.concentrations[1]
                    
                    elif each[1] == "-ATP":
                        self.matrixTransitionRate[i][each[0]] = self.__pars.rate_constants[("UNBIND", each[2], 0)]
                    
                    elif each[1] == "-ADP":
                        self.matrixTransitionRate[i][each[0]] = self.__pars.rate_constants[("UNBIND", each[2], 1)]
                        
                    elif each[1] == "CT":
                        confEnergyChange = self.__stateEnergy[each[0]] - self.__stateEnergy[i]
                        self.matrixTransitionRate[i][each[0]]\
                                    = self.__pars.rate_constants[("CONF",)] * np.exp(-max(confEnergyChange, 0.0))
                        
                    else:#each[1]="HYD" or "SYN"
                        self.matrixTransitionRate[i][each[0]] = self.__pars.rate_constants[("CHEM",)]
                    
                    self.dictTransition[(i, each[0])] = (each[1], self.matrixTransitionRate[i][each[0]])
                     
                else:#each[1] = "RT"
                
                    j = each[0]%self.model.N
                    confEnergyChange = self.__stateEnergy[j] - self.__stateEnergy[i]
                    
                    self.matrixTransitionRate[i][j]\
                        += self.__pars.rate_constants[("ROT",)] * np.exp(-max(confEnergyChange, 0.0))
                
                    self.dictTransition[(i, each[0])] = (each[1], self.__pars.rate_constants[("ROT",)] * np.exp(-max(confEnergyChange, 0.0)))
                
        self.matrixTransitionRate += -np.diag(sum(np.transpose(self.matrixTransitionRate)))
        
        return
    
    
    def __addSymmetricTransitions(self, outFileName, write = True):
        
        # no return, but self.dictTransition is updated
        
        for i in range(self.model.N):
            
            for each in self.model.accSubspace[i]:
                
                pt = each[0] // self.model.N
                j =  each[0] % self.model.N
                    
                if pt == 0:
                    
                    self.dictTransition[(i+self.model.N, j+self.model.N)] = self.dictTransition[(i, each[0])]
                    self.dictTransition[(i+2*self.model.N, j+2*self.model.N)] = self.dictTransition[(i, each[0])]
                    
                elif pt == 1:
                    
                    self.dictTransition[(i+self.model.N, j+2*self.model.N)] = self.dictTransition[(i, each[0])]
                    self.dictTransition[(i+2*self.model.N, j)] = self.dictTransition[(i, each[0])]
                    
                else:
                    
                    self.dictTransition[(i+self.model.N, j)] = self.dictTransition[(i, each[0])]
                    self.dictTransition[(i+2*self.model.N, j+self.model.N)] = self.dictTransition[(i, each[0])]
                
        if write == True:
            with open(outFileName+".trans.csv", "w") as file:
            
                for each in self.dictTransition:
                    
                    file.write("%d,%d,%s,%12.2e\n"%(each[0]+1, each[1]+1, self.dictTransition[each][0], self.dictTransition[each][1]))
        
        return 0
    

    def __generateFullTransitionRateMatrix(self):
        
        R_full = np.zeros((3*self.model.N, 3*self.model.N))
        
        for i, j in self.dictTransition:
            
            R_full[i][j] = self.dictTransition[(i, j)][1]
            
        R_full += -np.diag(sum(np.transpose(R_full)))
        
        return R_full
    

    def set_trans_rate_matrix(self, vecPara, c_ATP, c_ADP, returnFullRateMatrix = False, write = False, outFileName = "F1-ATPase"):
        
        pars = Parameter(self.model.N_conf)
        pars.set_values(vecPara, c_ATP, c_ADP)
        self.__pars = pars

        self.__stateEnergy -= self.__stateEnergy
        self.__calculateStateEnergy()
        
        self.matrixTransitionRate -= self.matrixTransitionRate
        self.__generateAsyTransitions()
        self.__addSymmetricTransitions(outFileName, write)
        
        if returnFullRateMatrix is True:
            R_full = self.__generateFullTransitionRateMatrix()
            return R_full
        
        return
    

    def __calculateStationaryDistr(self):
        
        eigvals, eigvecs = np.linalg.eig(np.transpose(self.matrixTransitionRate))
        eigvals = eigvals.real
        sortedEigvals = sorted([(i, eigvals[i]) for i in range(self.model.N)], 
                               key = lambda x: abs(x[1]))
        self.st_distr = np.copy(eigvecs[:, sortedEigvals[0][0]].real)
        self.st_distr /= sum(self.st_distr)
        
        for i in range(self.model.N):
            
            if self.st_distr[i] < 0:
                self.st_distr[i] = 0.0
        
        self.st_distr /= sum(self.st_distr)
        
        self.report["T_eq"] = 1./abs(sortedEigvals[1][1])

        return
    
    
    def __calculatePairwiseFlux(self):
        
        for (i, j) in self.dictTransition:
            
            self.__dictPairwiseFlux[(i, j)] = self.dictTransition[(i, j)][1]*self.st_distr[i%self.model.N]/3
        
        return
        
    
    def __calculate_k_cat(self):
        
        self.__chemicalNetFlux -= self.__chemicalNetFlux

        for (i, j) in self.dictTransition:
            
            if self.dictTransition[(i, j)][0] in ["+ATP", "HYD", "-ADP"]:
            
                state_i = self.__dictAsyState_inverse[i % self.model.N]
                state_j = self.__dictAsyState_inverse[j % self.model.N]
                e1, t1, d1 = state_i[4:7].count(2), state_i[4:7].count(0), state_i[4:7].count(1)
                e2, t2, d2 = state_j[4:7].count(2), state_j[4:7].count(0), state_j[4:7].count(1)
                
                self.__chemicalNetFlux[self.__chemicalSpace.index(((e1, t1, d1), (e2, t2, d2)))] += self.__dictPairwiseFlux[(i, j)] - self.__dictPairwiseFlux[(j, i)]

        self.report["k_cat"] = sum(self.__chemicalNetFlux)/3.
        
        return
    
    
    def __calculate_k_rot(self):
        
        self.__rotationalNetFlux -= self.__rotationalNetFlux
        
        for (i, j) in self.dictTransition:
            
            if self.dictTransition[(i, j)][0] == "RT":
                
                a, c = i // self.model.N, i % self.model.N
                b, d = j // self.model.N, j % self.model.N
                
                if a == b:# rotation from 80 to 120 or reverse
                    if self.__dictAsyState_inverse[c][0] == 80:
                        self.__rotationalNetFlux[0] += self.__dictPairwiseFlux[(i, j)]
                    else:
                        self.__rotationalNetFlux[0] -= self.__dictPairwiseFlux[(i, j)]
                        
                elif a != b:# rotation from 120 to 200 or reverse
                    if self.__dictAsyState_inverse[c][0] == 80:
                        self.__rotationalNetFlux[1] -=  self.__dictPairwiseFlux[(i, j)]
                    else:
                        self.__rotationalNetFlux[1] +=  self.__dictPairwiseFlux[(i, j)]
        
        self.report["k_rot"] = (self.__rotationalNetFlux[0] + self.__rotationalNetFlux[1])/6.
        
        return
        
    
    def __calculatePairwiseNetFlux(self):
        
        self.__dictPairwiseNetFlux.clear()
        
        for (i, j) in self.__dictPairwiseFlux:

            if ((i, j) not in self.__dictPairwiseNetFlux) and ((j, i) not in self.__dictPairwiseNetFlux):
                
                if self.__dictPairwiseFlux[(i, j)] >= self.__dictPairwiseFlux[(j, i)]:
                    self.__dictPairwiseNetFlux[(i, j)] = self.__dictPairwiseFlux[(i, j)] - self.__dictPairwiseFlux[(j, i)]
                
                else:
                    self.__dictPairwiseNetFlux[(j, i)] = self.__dictPairwiseFlux[(j, i)] - self.__dictPairwiseFlux[(i, j)]
        
        self.__net_flux = sorted(self.__dictPairwiseNetFlux.items(), key = lambda x: x[1], reverse = True)
        
        return
    
    
    def __calculateOccupancy(self):
        
        occupancy = np.zeros(3)#population of each binding state
        
        for n in range(self.model.N):
            for s in range(3):
                occupancy[self.model.asyState[n][s+4]] += self.st_distr[n]
        
        self.report["occ_tot"] = occupancy[0] + occupancy[1]
        self.report["occ_ATP"] = occupancy[0]
        self.report["occ_ADP"] = occupancy[1]
        
        return


    def calculate_steady_state_properties(self):
        
        self.__calculateStationaryDistr()
        self.__calculatePairwiseFlux()
        
        self.__calculate_k_cat()
        self.__calculate_k_rot()
        self.__calculateOccupancy()
        
        return
    
    
    def write_st_distr(self, filePath):
        
        with open(filePath, "w") as file:
            for n in range(self.model.N):
                file.write("%d,%.6e\n"%(n, self.st_distr[n]))
        
        return
    

    def analyzeSteadyState_betaConfig(self):

        for config in self.betaConfigPop:
            self.betaConfigPop[config] = 0.
        
        for n, state in enumerate(self.model.asyState):
            self.betaConfigPop[(state[0], state[1], state[2], state[3])] += self.st_distr[n]
        
        return
    

    
    def analyzeRotDwells(self):
        
        self.report["pop_cat"] = 0.
        self.report["pop_wait"] = 0.

        for n in range(self.model.N):
            if self.model.asyState[n][0] == self.model.angle_cat:
                self.report["pop_cat"] += self.st_distr[n]
            elif self.model.asyState[n][0] == 120:
                self.report["pop_wait"] += self.st_distr[n]

        for trans in self.model.trans_modes:
            for dwell in self.model.dwells:
                self.report["%s_%d"%(trans, dwell)] = 0.
                
                for (i, j) in self.model.trans2dwell[trans][dwell]:
                    self.report["%s_%d"%(trans, dwell)] += self.__dictPairwiseFlux[(i, j)] - self.__dictPairwiseFlux[(j, i)]
        
        return
        

'''
    def analyzeSteadyState_NucExchange(self, filePath1, filePath2):
        
        self.__calculatePairwiseNetFlux()

        dict_bT = dict()
        dict_uD = dict()
        dict_state_inverse = {self.model.state[state]: state for state in self.model.state}
        
        with open(filePath1, "w") as file:
            
            file.write("#state_i,state_i,#state_j,state_j,flux,type,detail\n")
            
            for each in self.__net_flux:
                
                i, j = each[0][0], each[0][1]
                
                if min(dict_state_inverse[i][0], dict_state_inverse[j][0]) <= 120:
                
                    file.write("%d,(%d|%s-%s|%s-%s|%s-%s),%d,(%d|%s-%s|%s-%s|%s-%s),%.4e,#%s,"\
                               %(\
                               i, dict_state_inverse[i][0], 
                               self.__confStateAbbrev[dict_state_inverse[i][1]], self.__bindStateAbbrev[dict_state_inverse[i][4]], 
                               self.__confStateAbbrev[dict_state_inverse[i][2]], self.__bindStateAbbrev[dict_state_inverse[i][5]], 
                               self.__confStateAbbrev[dict_state_inverse[i][3]], self.__bindStateAbbrev[dict_state_inverse[i][6]],
                               j, dict_state_inverse[j][0], 
                               self.__confStateAbbrev[dict_state_inverse[j][1]], self.__bindStateAbbrev[dict_state_inverse[j][4]], 
                               self.__confStateAbbrev[dict_state_inverse[j][2]], self.__bindStateAbbrev[dict_state_inverse[j][5]],
                               self.__confStateAbbrev[dict_state_inverse[j][3]], self.__bindStateAbbrev[dict_state_inverse[j][6]],
                               each[1], self.instance.dictTransition[(i, j)][0]))
                    
                    
                    if self.instance.dictTransition[(i, j)][0] in ["+ATP", "-ATP", "+ADP", "-ADP", "HYD", "SYN"]:
                        for k in range(3):
                            if dict_state_inverse[i][k+4] - dict_state_inverse[j][k+4] != 0:
                                file.write("%d-%s"%(dict_state_inverse[i][0], self.__confStateAbbrev[dict_state_inverse[i][k+1]]))
                                
                                if self.instance.dictTransition[(i, j)][0] == "+ATP":
                                    tag = "%d-%s"%(dict_state_inverse[i][0], self.__confStateAbbrev[dict_state_inverse[i][k+1]])
                                    if tag in dict_bT:
                                        dict_bT[tag] += each[1]
                                    else:
                                        dict_bT[tag] = each[1]
                                
                                if self.instance.dictTransition[(i, j)][0] == "-ADP":
                                    tag = "%d-%s"%(dict_state_inverse[i][0], self.__confStateAbbrev[dict_state_inverse[i][k+1]])
                                    if tag in dict_uD:
                                        dict_uD[tag] += each[1]
                                    else:
                                        dict_uD[tag] = each[1]
                                
                    if self.instance.dictTransition[(i, j)][0] == "RT":
                        file.write("(%d-%d)"%(dict_state_inverse[i][0], dict_state_inverse[j][0]))
                    
                    file.write("\n")
        
        for each in ["80-o", "120-o", "80-h"]:
            
            if each not in dict_bT:
                dict_bT[each] = 0.0

            if each not in dict_uD:
                dict_uD[each] = 0.0

        with open(filePath2, "w") as file:
            file.write("%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n"%(\
                        dict_bT["80-o"], dict_bT["120-o"], dict_bT["80-h"],
                        dict_uD["80-o"], dict_uD["120-o"], dict_uD["80-h"]))
        
        return

    
    def calculateEvolution(self, cT, cD, rho_init, timePoints, tag, filePath):
        #filePath = "%s/PopulationEvolution_(%.2e,%.2e)_%s.csv"%(self.workDir, cT, cD, tag)
        
        matrixTransRate = self.instance.set_trans_rate_matrix(\
            self.vec_para, cT, cD, returnFullRateMatrix=True)# matrixTransRate is 3N*3N-dim

        omega, D = np.linalg.eig(np.transpose(matrixTransRate))
        
        D_inv = np.linalg.inv(D)
        psi_init = np.dot(D_inv, rho_init)
        
        N_t = len(timePoints)
        dictEvo = {i: np.zeros(N_t) for i in range(3*self.model.N)}
        dictDeriv = {i: np.zeros(N_t) for i in range(3*self.model.N)}
        
        with open(filePath, "w") as file:
        
            for i in range(N_t):
                
                file.write("%.6e"%timePoints[i])
                
                psi = psi_init*np.exp(timePoints[i]*omega)
                rho = np.dot(D, psi)
                rho = np.where(rho < 0.0, 0.0, rho)
                rho /= sum(rho)

                dpsi = -psi*omega
                drho = np.dot(D, dpsi)
                
                for j in range(3*self.model.N):
                    file.write(",%.12f"%rho[j].real)
                    dictEvo[j][i] = rho[j].real
                
                for j in range(3*self.model.N):
                    file.write(",%.12f"%drho[j].real)
                    dictDeriv[j][i] = drho[j].real
                
                file.write("\n")
        
        return timePoints, dictEvo, dictDeriv
'''