#!usr/bin/env python
#-*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 02/04/2023

import numpy as np
from matplotlib import pyplot as plt
from hmm_miscellaneous import*


class Expectation(Miscellaneous):
    
    def __init__(self, c):
        
        self.c = c#rescaling factor
    
    
    def calculateEmissionProb(self, HMM, N_timePoint, vecObs):
    
        matEmitProb = np.zeros((HMM.N_state, N_timePoint))

        for s in range(HMM.N_state):
          if HMM.N_asyState != 1:
            s_asy = s%HMM.N_asyState
          else:
            s_asy = 0
          center = HMM.vecAsyState[s_asy] + 120.0*(s//HMM.N_asyState)
          
          matEmitProb[s] += self.periodicGaussian(vecObs, center, HMM.vecEmitStd[s_asy])
        
        return matEmitProb
    
    
    def calculate2wardProb_fast(self, HMM, N_timePoint, vecObs):#renormalized to avoid numerical underflow

        matEmitProb = self.calculateEmissionProb(HMM, N_timePoint, vecObs)

        matForwardProb = np.zeros((HMM.N_state, N_timePoint))
        matForwardProb[:, 0] += matEmitProb[:, 0]

        matBackwardProb = np.zeros((HMM.N_state, N_timePoint))
        matBackwardProb[:, -1] += 1.0
        
        rc_forward = np.zeros(N_timePoint)#renormalization counter
        rc_backward= np.zeros(N_timePoint)

        for t in range(1, N_timePoint):
          
            tt = N_timePoint-1-t
          
            matForwardProb[:, t] += matEmitProb[:, t] * np.dot(np.transpose(HMM.matTransProb), matForwardProb[:, t-1])
            matBackwardProb[:, tt] += np.dot(HMM.matTransProb, matEmitProb[:, tt+1]*matBackwardProb[:, tt+1])
          
            if sum(matForwardProb[:, t]) < self.c:
                rc_forward[t:] += 1
                matForwardProb[:, t] /= self.c
          
            if sum(matBackwardProb[:, tt]) < self.c:
                rc_backward[:tt] += 1
                matBackwardProb[:, tt] /= self.c
        
        L_log = np.log(np.dot(matForwardProb[:, 0], matBackwardProb[:, 0])) + (rc_forward[0]+rc_backward[0])*np.log(self.c)
        #print("L_log, %.6f, %.6f"%(np.log(np.dot(matForwardProb[:, 0], matBackwardProb[:, 0])), (rc_forward[0]+rc_backward[0])*np.log(self.c)))
        
        return matEmitProb, matForwardProb, matBackwardProb, rc_forward, rc_backward, L_log

    
    
    def calculateViterbiProb_fast(self, HMM, N_timePoint, matEmitProb, w):#with log scale

        matViterbi_log = np.zeros((HMM.N_state, N_timePoint))
        matViterbi_log[:, 0] += self.safelog(matEmitProb[:, 0])
        
        for t in range(1, N_timePoint):
          
          matViterbi_log[:, t] += np.max(matViterbi_log[:, t-1] + w * self.safelog(np.transpose(HMM.matTransProb)), axis=1)\
                                + self.safelog(matEmitProb[:, t])
        
        return matViterbi_log


    def assignStates_viterbi(self, HMM, vecObs, w):#using log-scaled Viterbi matrix
        
        N_timePoint = len(vecObs)
        
        matEmitProb = self.calculateEmissionProb(HMM, N_timePoint, vecObs)
        matViterbi_log = self.calculateViterbiProb_fast(HMM, N_timePoint, matEmitProb, w)
        
        vecAssignedState = np.zeros(N_timePoint, dtype = int)
        
        vecAssignedState[-1] = np.argmax(matViterbi_log[:, -1])

        for t in range(N_timePoint-2, -1, -1):
          vecAssignedState[t] = np.argmax(matViterbi_log[:, t] + self.safelog(HMM.matTransProb[:, vecAssignedState[t+1]]))

        return vecAssignedState
