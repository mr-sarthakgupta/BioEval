#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 25/12/2024

from itertools import product
from include.variant import *


class MarkovModel:
    
    def __init__(self, 
                 confs, v_index, activeConf,
                 name = "F1-ATPase",
                 angle_cat = 80,
                 jointConfTrans = False):
    # Gamma orientation: with fold of symmetry = 3, (80, 200, 320) & (120, 240, 360) are two symmetric groups.
    #                                      Use (120, 240, 360) rather than (0, 120, 240) to make gamma at 80 and 120 point to the
    #                                      same beta, and name this beta beta_A.
    #                                      Increased angle corresponds to counterclockwise rotation.
    # bStates: binding state, 2 for empty, 0 for ATP-bound, 1 for ADP-bound
        
        self.name = name
        self.activeConf = activeConf
        self.angle_cat = angle_cat
        self.__jointConfTrans = jointConfTrans
        
        self.__variant = Variant(confs, v_index, activeConf)
        self.version = self.__variant.version
        self.N_conf = len(self.__variant.confStates)
        self.outFileName = "%s_%s"%(self.name, self.version)
        
        self.stepwiseAngle = [360, self.angle_cat, 120, self.angle_cat+120]
        self.betaConfig = {each: set() for each in [self.angle_cat, 120, self.angle_cat+120, 240, self.angle_cat+240, 360]}

        self.N = -9999
        self.asyState = []# each row: [gamma, beta_A conf, beta_B conf, beta_C, conf, beta_A bind, beta_B bind, beta_C bind]
        self.state = dict()
        
        self.accSubspace = dict()
        
        self.__bindStates = [0, 1, 2]
        self.__bindStatesTag = {0: "ATP-bound", 1: "ADP-bound", 2: "empty"}
        self.__stepwiseBindingState = {2: [(0, "+ATP"), (1, "+ADP")],
                                     0: [(2, "-ATP"), (1, "HYD")],
                                     1: [(2, "-ADP"), (0, "SYN")]}

        self.dictConfName = {0: "o", 1: "h", 2: "c", 3: "a"}

        # Generate Markov states===============================================================
        self.generateAsyMarkovStates()
        self.addSymmetricMarkovStates()
        #======================================================================================
        
        # Generate accessible subspace for each (asymmetric) Markov state======================
        for i in range(self.N):
            self.accSubspace[i] = set()
            
            state = self.asyState[i]
            
            self.searchAccessibleSubspaceByBindingStates(i, state)# change binding state
            self.searchAccessibleSubspaceByBetaConfTrans(i, state)# change beta conformation (no gamma rotation)
            self.searchAccessibleSubspaceByGammaRot(i, state)     # change gamma (no beta conformation change)
        #======================================================================================
        
        self.betaConfig["all"] = list(self.betaConfig[self.angle_cat] | self.betaConfig[120])

        self.dwells = [self.angle_cat, 120, self.angle_cat+120, 240, self.angle_cat+240, 360]
        self.trans_modes = ["+ATP", "-ADP", "HYD"]
        self.trans2dwell = {trans: dict() for trans in self.trans_modes}
        self.groupTransitionByDwell()
                    
        return

    
    #Functions for generating Markov states====================================================
    
    def generateAsyMarkovStates(self):
        
        bindCombs = list(product(self.__bindStates, repeat = 3))
        
        confCombs_cat = list(product(self.__variant.gbCoupling_cat[0],self.__variant.gbCoupling_cat[1], self.__variant.gbCoupling_cat[2]))
        confCombs_wait = list(product(self.__variant.gbCoupling_wait[0],self.__variant.gbCoupling_wait[1], self.__variant.gbCoupling_wait[2]))
        
        for each in confCombs_cat:
            
            self.betaConfig[self.angle_cat].add(each)
            
            for each1 in bindCombs:
                
                state = [self.angle_cat] + list(each) + list(each1)
                self.asyState.append(state)
        
        
        for each in confCombs_wait:
            
            self.betaConfig[120].add(each)
            
            for each1 in bindCombs:
                
                state = [120] + list(each) + list(each1)
                self.asyState.append(state)
        
        self.N = len(self.asyState)
        for i in range(self.N):
            self.state[tuple(self.asyState[i])] = i
        
        return


    def addSymmetricMarkovStates(self):
        
        # No return, but the input dictMarkovState is updated
        
        file = open(self.outFileName+"_state.markov", "w")
        
        for i in range(self.N):
        
            state = self.asyState[i]
            symState1 = (state[0]+120, state[3], state[1], state[2], state[6], state[4], state[5])
            symState2 = (state[0]+240, state[2], state[3], state[1], state[5], state[6], state[4])
            
            self.betaConfig[state[0]+120].add(symState1[1:4])
            self.betaConfig[state[0]+240].add(symState2[1:4])
            
            #120 degree rotation
            self.state[symState1] = i + self.N
            #240 degree rotation
            self.state[symState2] = i + 2*self.N
            
            file.write("%4d%4d%15s%15s%15s%15s%15s%15s"%(i+1, state[0], 
                       self.__variant.cStatesTag[state[1]], self.__variant.cStatesTag[state[2]], self.__variant.cStatesTag[state[3]],
                       self.__bindStatesTag[state[4]], self.__bindStatesTag[state[5]], self.__bindStatesTag[state[6]]))
            
            file.write("%8d%4d%15s%15s%15s%15s%15s%15s"%(i+self.N+1, symState1[0], 
                            self.__variant.cStatesTag[symState1[1]], self.__variant.cStatesTag[symState1[2]], self.__variant.cStatesTag[symState1[3]],
                            self.__bindStatesTag[symState1[4]], self.__bindStatesTag[symState1[5]], self.__bindStatesTag[symState1[6]]))
            
            file.write("%8d%4d%15s%15s%15s%15s%15s%15s\n"%(i+2*self.N+1, symState2[0], 
                            self.__variant.cStatesTag[symState2[1]], self.__variant.cStatesTag[symState2[2]], self.__variant.cStatesTag[symState2[3]],
                            self.__bindStatesTag[symState2[4]], self.__bindStatesTag[symState2[5]], self.__bindStatesTag[symState2[6]]))
        
        file.close()
        
        return
    
    #==========================================================================================
    
    
    #Functions for generating accessible subspace==============================================
    
    def searchAccessibleSubspaceByBindingStates(self, i, state):
        
        for b in [4, 5, 6]:# change binding state
            
            for each in self.__stepwiseBindingState[state[b]]:
                
                if ((each[1] in ["HYD", "SYN"]) and (state[b-3] in self.__variant.inactiveConf)) == False:#change with model
                
                    newState = state[0:b] + [each[0]] +state[(b+1):]
                    
                    self.accSubspace[i].add((self.state[tuple(newState)], each[1], state[b-3]))
        
        return


    def searchAccessibleSubspaceByBetaConfTrans(self, i, state):
        
        if self.__jointConfTrans == True:

          for comb in list(product(self.__variant.stepwiseConfTrans[state[1]]+[state[1]],
                                           self.__variant.stepwiseConfTrans[state[2]]+[state[2]],
                                           self.__variant.stepwiseConfTrans[state[3]]+[state[3]])):
            
              if comb != (state[1], state[2], state[3]):
                
                  newState = (state[0], comb[0], comb[1], comb[2], state[4], state[5], state[6])
                
                  if newState in self.state:
                      self.accSubspace[i].add((self.state[newState], "CT"))
        
        else:

            for beta in range(1, 4):
          
                c = state[beta]

                for each in self.__variant.stepwiseConfTrans[c]:
                    newState = [] + state
                    newState[beta] = each
                    newState = tuple(newState)

                    if newState in self.state:
                        self.accSubspace[i].add((self.state[newState], "CT"))
      
        return


    def searchAccessibleSubspaceByGammaRot(self, i, state):
        
        for dir in [1, -1]:
            
            newGamma = self.stepwiseAngle[self.stepwiseAngle.index(state[0])+dir]
            onlyRotState = [newGamma] + state[1:]
            
            if tuple(onlyRotState) in self.state:
                
                self.accSubspace[i].add((self.state[tuple(onlyRotState)], "RT"))
                    
        return


    def groupTransitionByDwell(self):

        self.state2dwell = {dwell: [] for dwell in self.dwells}
        
        for s in self.state:
            self.state2dwell[s[0]].append(self.state[s])
        
        allState = sorted(self.state.items(), key = lambda x: x[1])
        
        for dwell in self.dwells:
            
            for trans in self.trans2dwell:
                self.trans2dwell[trans][dwell] = []
            
            for i in self.state2dwell[dwell]:
                
                if allState[i][0][4] == 2:#beta_1 is empty
                    
                    j = self.state[allState[i][0][:4]+(0,)+allState[i][0][5:]]
                    self.trans2dwell["+ATP"][dwell].append((i, j))
                    
                elif allState[i][0][4] == 1:#beta_1 is ADP bound
                    
                    j = self.state[allState[i][0][:4]+(2,)+allState[i][0][5:]]
                    self.trans2dwell["-ADP"][dwell].append((i, j))
                
                elif allState[i][0][4] == 0:#beta_1 is ATP bound
                    
                    if allState[i][0][1] in self.activeConf:
                        j = self.state[allState[i][0][:4]+(1,)+allState[i][0][5:]]
                        self.trans2dwell["HYD"][dwell].append((i, j))