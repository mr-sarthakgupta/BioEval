#!usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 07/10/2022

import numpy as np
import itertools
from variant_library import *

class MarkovModel(Variant):
    
    def __init__(self, confs, v_index, activeConf, angle_cat = 80, jointConfTrans = False):
    # Gamma orientation: with fold of symmetry = 3, (80, 200, 320) & (120, 240, 360) are two symmetric groups.
    #                    Use (120, 240, 360) rather than (0, 120, 240) to make gamma at 80 and 120 point.
    #                    to the same beta, and name this beta beta_A.
    #                    Increased angle corresponds to counterclockwise rotation.
    # bStates: binding state, 0 for ATP-bound, 1 for ADP-bound, 2 for empty
    # cStates: beta conformation, 0 for open, 1 for closed_1, 2 for closed_2
        
        self.bindStates = [0, 1, 2]
        self.dictBindClass = {(0, 0): 0, (1, 0): 1, (2, 0): 2, (3, 0): 3,
                              (0, 1): 4, (1, 1): 5, (2, 1): 6,
                              (0, 2): 7, (1, 2): 8,
                              (0, 3): 9}#number of sites that are (ATP-bound, ADP-bound)
        self.stepwiseBindingState = {2: [(0, "+ATP"), (1, "+ADP")],#empty
                                     0: [(2, "-ATP"), (1, "HYD")],#ATP-bound
                                     1: [(2, "-ADP"), (0, "SYN")]}#ADP-bound
                                     
        self.angle_cat = angle_cat
        self.stepwiseAngle = [360, self.angle_cat, 120, 120+self.angle_cat]

        self.jointConfTrans = jointConfTrans

        self.dictChemFlux = {(0, 1): 1,  (1, 4): 2,  (0, 4): 3,
                             (1, 2): 4,  (2, 5): 5,  (1, 5): 6,
                             (4, 5): 7,  (5, 7): 8,  (4, 7): 9,
                             (2, 3): 10, (3, 6): 11, (2, 6): 12,
                             (5, 6): 13, (6, 8): 14, (5, 8): 15,
                             (7, 8): 16, (8, 9): 17, (7, 9): 18}
        self.dictTransType = {("+ATP", 0): 1,  ("+ADP", 0): 2,
                              ("+ATP", 1): 3,  ("+ADP", 1): 4,
                              ("+ATP", 2): 5,  ("+ADP", 2): 6,
                              ("+ATP", 3): 7,  ("+ADP", 3): 8,
                              
                              ("-ATP", 0): 11, ("-ADP", 0): 12,
                              ("-ATP", 1): 13, ("-ADP", 1): 14,
                              ("-ATP", 2): 15, ("-ADP", 2): 16,
                              ("-ATP", 3): 17, ("-ADP", 3): 18,
                              
                              ("HYD", 0):  21, ("SYN", 0):  22,
                              ("HYD", 1):  23, ("SYN", 1):  24,
                              ("HYD", 2):  25, ("SYN", 2):  26,
                              ("HYD", 3):  27, ("SYN", 3):  28,
                              
                              "RT":        31, "CT":        32}
                              
        Variant.__init__(self, confs, v_index)
        self.inactiveConf = [each for each in self.confStates if each not in activeConf]


    '''
    =======================================================================================
    ||                              Generate Markov States                               ||
    =======================================================================================
    '''
    def generateAsyMarkovStates(self):
        
        asyMarkovStates = []# each row: [gamma, beta_A conf, beta_B conf, beta_C, conf, beta_A bind, beta_B bind, beta_C bind]
        bindClass = []
        
        bindCombs = list(itertools.product(self.bindStates, repeat = 3))
        
        confCombs_cat = list(itertools.product(self.gbCoupling_cat[0],self.gbCoupling_cat[1], self.gbCoupling_cat[2]))
        confCombs_wait = list(itertools.product(self.gbCoupling_wait[0],self.gbCoupling_wait[1], self.gbCoupling_wait[2]))
        
        for each in confCombs_cat:
            
            for each1 in bindCombs:
                
                state = [self.angle_cat] + list(each) + list(each1)
                
                asyMarkovStates.append(state)
                
                bindClass.append(self.dictBindClass[(state[4:7].count(0), state[4:7].count(1))])
        
        
        for each in confCombs_wait:
            
            for each1 in bindCombs:
                
                state = [120] + list(each) + list(each1)
                
                asyMarkovStates.append(state)
                
                bindClass.append(self.dictBindClass[(state[4:7].count(0), state[4:7].count(1))])
        
        numAsyMarkovState = len(asyMarkovStates)
        dictMarkovStates = {tuple(asyMarkovStates[i]): i for i in range(numAsyMarkovState)}
        
        return numAsyMarkovState, asyMarkovStates, dictMarkovStates, bindClass
    
    
    def addSymmetricMarkovStates(self, numAsyMarkovState, asyMarkovStates, dictMarkovStates):
        
        for i in range(numAsyMarkovState):
        
            state = asyMarkovStates[i]
            symState1 = (state[0]+120, state[3], state[1], state[2], state[6], state[4], state[5])
            symState2 = (state[0]+240, state[2], state[3], state[1], state[5], state[6], state[4])
            
            #120 degree rotation
            dictMarkovStates[symState1] = i + numAsyMarkovState
            #240 degree rotation
            dictMarkovStates[symState2] = i + 2*numAsyMarkovState
        
        return 0
        
    
    '''
    =======================================================================================
    ||                            Generate Accessible Subspace                           ||
    =======================================================================================
    '''
    def searchAccessibleSubspaceByBindingStates(self, dictMarkovStates, dictAccessibleSubspace, i, state):
        
        for b in [4, 5, 6]:# change binding state
            
            for each in self.stepwiseBindingState[state[b]]:
                
                if ((each[1] in ["HYD", "SYN"]) and state[b-3] in self.inactiveConf) == False:
                    
                    newState = state[0:b] + [each[0]] +state[(b+1):]
                    
                    dictAccessibleSubspace[i].add((dictMarkovStates[tuple(newState)], 
                                                   self.dictTransType[(each[1], state[b-3])]))
                                                   
        return 0


    def searchAccessibleSubspaceByBetaConfTrans(self, dictMarkovStates, dictAccessibleSubspace, i, state):
        
      if self.jointConfTrans == True:

        for comb in list(itertools.product(self.stepwiseConfTrans[state[1]]+[state[1]],
                                           self.stepwiseConfTrans[state[2]]+[state[2]],
                                           self.stepwiseConfTrans[state[3]]+[state[3]])):
            
            if comb != (state[1], state[2], state[3]):
                
                newState = (state[0], comb[0], comb[1], comb[2], state[4], state[5], state[6])
                
                if newState in dictMarkovStates:
                    dictAccessibleSubspace[i].add((dictMarkovStates[newState], self.dictTransType["CT"]))
      
      else:
        
        for beta in range(1, 4):
          
          c = state[beta]

          for each in self.stepwiseConfTrans[c]:
            newState = [] + state
            newState[beta] = each
            newState = tuple(newState)

            if newState in dictMarkovStates:
                dictAccessibleSubspace[i].add((dictMarkovStates[newState], self.dictTransType["CT"]))
      
      return 0


    def searchAccessibleSubspaceByGammaRot(self, dictMarkovStates, dictAccessibleSubspace, i, state):
        
        for dir in [1, -1]:
            
            newGamma = self.stepwiseAngle[self.stepwiseAngle.index(state[0])+dir]
            onlyRotState = [newGamma] + state[1:]
            
            if tuple(onlyRotState) in dictMarkovStates:
                
                dictAccessibleSubspace[i].add((dictMarkovStates[tuple(onlyRotState)], self.dictTransType["RT"]))
        
        return 0


    def generateAsyAccesibleSubspace(self, numAsyMarkovState, asyMarkovStates, dictMarkovStates):

        dictAccessibleSubspace = {i: set() for i in range(numAsyMarkovState)}
        
        for i in range(numAsyMarkovState):
        
            state = asyMarkovStates[i]
            
            # change binding state
            self.searchAccessibleSubspaceByBindingStates(dictMarkovStates, dictAccessibleSubspace, i, state)
            
            # change beta conformation (no gamma rotation)
            self.searchAccessibleSubspaceByBetaConfTrans(dictMarkovStates, dictAccessibleSubspace, i, state)
            
            # change gamma (possibly include beta conformation change)
            self.searchAccessibleSubspaceByGammaRot(dictMarkovStates, dictAccessibleSubspace, i, state)
        
        return dictAccessibleSubspace
    
    
    def writeTransitions(self, outFileName, numAsyMarkovState, asyMarkovStates, dictAccessibleSubspace, bindClass):
        
        file = open(outFileName+".input", "a")
        
        file.write("%-10s%10d\n"%("N_STATE", numAsyMarkovState))
        
        numTransit = 0
        
        for i in range(numAsyMarkovState):
            
            state = asyMarkovStates[i]
            numTransit += len(dictAccessibleSubspace[i])
            
            file.write("%-10s%10s%6d%4d%4d%4d%4d%4d%4d%4d\n"%("MODEL", "STATE",
                       i, state[0], state[1], state[2], state[3], state[4], state[5], state[6]))
         
        file.write("%-10s%10d\n"%("N_TRANSIT", numTransit))
         
        for i in range(numAsyMarkovState):
            
            sortedTransitions = sorted(dictAccessibleSubspace[i], key = lambda x: x[1])
            
            for each in sortedTransitions:
            
                a = bindClass[i]
                b = bindClass[each[0]%numAsyMarkovState]
                if a < b:
                    c = self.dictChemFlux[(a, b)]
                elif a > b:
                    c = -self.dictChemFlux[(b, a)]
                else:
                    c = 0

                if each[1] == self.dictTransType["RT"]:
                    pt = each[0] // numAsyMarkovState
                    if pt == 1:
                        c = 20
                    elif pt == 2:
                        c = -20
                    else:
                        if asyMarkovStates[i][0] == 80:
                            c = 19
                        else:
                            c = -19
                
                file.write("%-10s%10s%6d%6d%4d%4d\n"%("MODEL", "TRANSITION", i, each[0], each[1], c))
        
        file.close()
        
        return 0
        
    
    def __call__(self, outFileName):
        
        numAsyMarkovState, asyMarkovStates, dictMarkovStates, bindClass = self.generateAsyMarkovStates()
        self.addSymmetricMarkovStates(numAsyMarkovState, asyMarkovStates, dictMarkovStates)
        
        dictAccessibleSubspace = self.generateAsyAccesibleSubspace(numAsyMarkovState, asyMarkovStates, dictMarkovStates)
        
        self.writeTransitions(outFileName, numAsyMarkovState, asyMarkovStates, dictAccessibleSubspace, bindClass)
        
        return 0
