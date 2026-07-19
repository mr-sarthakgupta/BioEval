#!usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 13/10/2022

import numpy as np
import itertools
from variant_library import *

class MarkovModel(Variant):
    
    def __init__(self, confs, v_index, activeConf, angle_cat = 80, jointConfTrans = False):
    # Gamma orientation: with fold of symmetry = 3, (80, 200, 320) & (120, 240, 360) are two symmetric groups.
    #                                      Use (120, 240, 360) rather than (0, 120, 240) to make gamma at 80 and 120 point 
    #                                      to the same beta, and name this beta beta_A.
    #                                      Increased angle corresponds to counterclockwise rotation.
    # bStates: binding state, 0 for ATP-bound, 1 for ADP-bound, 2 for empty
    # cStates: beta conformation, 0 for open, 1 for closed, 2 for half-closed

        self.bindStates = [0, 1, 2]
        self.angle_cat = angle_cat
        self.stepwiseAngle = [360, self.angle_cat, 120, 120+self.angle_cat]
        self.stepwiseBindingState = {2: [(0, "+ATP"), (1, "+ADP")],#empty
                                     0: [(2, "-ATP"), (1, "HYD")],#ATP-bound
                                     1: [(2, "-ADP"), (0, "SYN")]}#ADP-bound
        
        self.jointConfTrans = jointConfTrans
        
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
        
        Variant.__init__(self, confs, v_index, activeConf)
        

    '''
    =======================================================================================
    ||                              Generate Markov States                               ||
    =======================================================================================
    '''
    
    def generateAsyMarkovStates(self):
        
        asyMarkovStates = []# each row: [gamma, beta_A conf, beta_B conf, beta_C, conf, beta_A bind, beta_B bind, beta_C bind]
        
        bindCombs = list(itertools.product(self.bindStates, repeat = 3))
        
        confCombs_cat = list(itertools.product(self.gbCoupling_cat[0],self.gbCoupling_cat[1], self.gbCoupling_cat[2]))
        confCombs_wait = list(itertools.product(self.gbCoupling_wait[0],self.gbCoupling_wait[1], self.gbCoupling_wait[2]))
        
        for each in confCombs_cat:
            
            for each1 in bindCombs:
                
                state = [self.angle_cat] + list(each) + list(each1)
                
                asyMarkovStates.append(state)
        
        
        for each in confCombs_wait:
            
            for each1 in bindCombs:
                
                state = [120] + list(each) + list(each1)
                
                asyMarkovStates.append(state)
                
        
        numAsyMarkovState = len(asyMarkovStates)
        dictMarkovStates = {tuple(asyMarkovStates[i]): i for i in range(numAsyMarkovState)}
        
        return numAsyMarkovState, asyMarkovStates, dictMarkovStates


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
    
    
    def writeTransitions(self, outFileName, numAsyMarkovState, asyMarkovStates, dictAccessibleSubspace):
        
        file = open(outFileName+".input", "a")
        
        file.write("%-10s%10d\n"%("ASY_STATE", numAsyMarkovState))
        
        for i in range(numAsyMarkovState):
            
            state = asyMarkovStates[i]
            
            symState1 = (state[0]+120, state[3], state[1], state[2], state[6], state[4], state[5])
            symState2 = (state[0]+240, state[2], state[3], state[1], state[5], state[6], state[4])
            numAccess = len(dictAccessibleSubspace[i])
            
            file.write("%-10s%10s%6d%4d%4d%4d%4d%4d%4d%4d%6d\n"%("MODEL", "STATE",
                             i, state[0], state[1], state[2], state[3], state[4], state[5], state[6], numAccess))
            file.write("%-10s%10s%6d%4d%4d%4d%4d%4d%4d%4d%6d\n"%("MODEL", "STATE", 
                            i+numAsyMarkovState, symState1[0], 
                            symState1[1], symState1[2], symState1[3], symState1[4], symState1[5], symState1[6],
                            numAccess))
            file.write("%-10s%10s%6d%4d%4d%4d%4d%4d%4d%4d%6d\n"%("MODEL", "STATE",
                             i+2*numAsyMarkovState, symState2[0], 
                             symState2[1], symState2[2], symState2[3], symState2[4], symState2[5], symState2[6],
                             numAccess))
         
        for i in range(numAsyMarkovState):
            
            sortedTransitions = sorted(dictAccessibleSubspace[i], key = lambda x: x[1])
            
            file.write("%-10s%10s%6d"%("MODEL", "TRANSITION", i))
            
            for each in sortedTransitions:
            
                file.write("%6d%4d"%(each[0], each[1]))
            
            file.write("\n%-10s%10s%6d"%("MODEL", "TRANSITION", i+numAsyMarkovState))
            
            for each in sortedTransitions:
            
                pt = each[0] // numAsyMarkovState
                j =  each[0] % numAsyMarkovState
                
                if pt == 0:
                    file.write("%6d%4d"%(j+numAsyMarkovState, each[1]))
                    
                elif pt == 1:
                    file.write("%6d%4d"%(j+2*numAsyMarkovState, each[1]))
                    
                else:
                    file.write("%6d%4d"%(j, each[1]))
                    
            file.write("\n%-10s%10s%6d"%("MODEL", "TRANSITION", i+2*numAsyMarkovState))
            
            for each in sortedTransitions:
                
                pt = each[0] // numAsyMarkovState
                j =  each[0] % numAsyMarkovState
                
                if pt == 0:
                    file.write("%6d%4d"%(j+2*numAsyMarkovState, each[1]))
                    
                elif pt == 1:
                    file.write("%6d%4d"%(j, each[1]))
                    
                else:
                    file.write("%6d%4d"%(j+numAsyMarkovState, each[1]))
        
            file.write("\n")
        
        file.close()
        
        return 0
        
    
    def __call__(self, outFileName):
        
        numAsyMarkovState, asyMarkovStates, dictMarkovStates = self.generateAsyMarkovStates()
        self.addSymmetricMarkovStates(numAsyMarkovState, asyMarkovStates, dictMarkovStates)
        
        dictAccessibleSubspace = self.generateAsyAccesibleSubspace(numAsyMarkovState, asyMarkovStates, dictMarkovStates)
        
        self.writeTransitions(outFileName, numAsyMarkovState, asyMarkovStates, dictAccessibleSubspace)
        
        return dictMarkovStates
