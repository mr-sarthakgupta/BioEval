#!usr/bin/env python
#-*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 02/04/2023

import numpy as np
from matplotlib import pyplot as plt
from hmm_miscellaneous import*
from hmm_expectation import*


class Maximization(Expectation):
    
    def __init__(self, N_bin, c):
        
        self.N_bin = N_bin
        self.bins = np.linspace(0.0, 360.0, N_bin + 1)
        self.reprVal = (self.bins[:-1] + self.bins[1:])/2
        
        Expectation.__init__(self, c)
    
    
    def calculateAsyTransProb(self, HMM, numerator, denominator):
    
        matAsyTransProb = np.zeros((HMM.N_asyState, HMM.N_state))
        
        matAsyTransProb[:, :HMM.N_asyState] += numerator[:HMM.N_asyState, :HMM.N_asyState]\
                                             + numerator[HMM.N_asyState:2*HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState]\
                                             + numerator[2*HMM.N_asyState:3*HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState]
        matAsyTransProb[:, HMM.N_asyState:2*HMM.N_asyState] += numerator[:HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState]\
                                                             + numerator[HMM.N_asyState:2*HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState]\
                                                             + numerator[2*HMM.N_asyState:3*HMM.N_asyState, :HMM.N_asyState]
        matAsyTransProb[:, 2*HMM.N_asyState:3*HMM.N_asyState] += numerator[:HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState]\
                                                               + numerator[HMM.N_asyState:2*HMM.N_asyState, :HMM.N_asyState]\
                                                               + numerator[2*HMM.N_asyState:3*HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState]

        for s in range(HMM.N_asyState):
            matAsyTransProb[s] /= denominator[s]
        
        return matAsyTransProb
    
    
    def calculateFullTransProb(self, HMM, matAsyTransProb):
      
        HMM.matTransProb[:HMM.N_asyState] = matAsyTransProb

        HMM.matTransProb[HMM.N_asyState:2*HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState]     = matAsyTransProb[:, :HMM.N_asyState]
        HMM.matTransProb[2*HMM.N_asyState:3*HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState] = matAsyTransProb[:, :HMM.N_asyState]
      
        HMM.matTransProb[HMM.N_asyState:2*HMM.N_asyState, :HMM.N_asyState]                   = matAsyTransProb[:, 2*HMM.N_asyState:3*HMM.N_asyState]
        HMM.matTransProb[2*HMM.N_asyState:3*HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState] = matAsyTransProb[:, 2*HMM.N_asyState:3*HMM.N_asyState]

        HMM.matTransProb[HMM.N_asyState:2*HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState] = matAsyTransProb[:, HMM.N_asyState:2*HMM.N_asyState]
        HMM.matTransProb[2*HMM.N_asyState:3*HMM.N_asyState, :HMM.N_asyState]                 = matAsyTransProb[:, HMM.N_asyState:2*HMM.N_asyState]
        
        return 0
    
    
    def plotObservationDistribution(self, HMM, reprVal, emitProb):
        
        fig, ax = plt.subplots()
        
        for i in range(HMM.N_state):
            
            l = ax.plot(reprVal, emitProb[i]/sum(emitProb[i]), label = i)
            
            center = HMM.vecAsyState[i%HMM.N_asyState] + 120.0*(i//HMM.N_asyState)
            prob = self.periodicGaussian(reprVal, center, HMM.vecEmitStd[i%HMM.N_asyState])
            ax.plot(reprVal, prob/sum(prob), c = l[0].get_color(), ls = ":")
        
        ax.legend()
        plt.show()
        
        return 0
    
    
    def calculateTemporaryVars_BW(self, HMM, matEmitProb, matForwardProb, matBackwardProb, rc_forward, rc_backward):
        
        rc0 = rc_forward[0] + rc_backward[0]
        rc_ttp1 = rc_forward[:-1] + rc_backward[1:] - rc0#dim = N_t-1
        rc_tt = rc_forward + rc_backward - rc0#dim=N_t
        L = np.dot(matForwardProb[:, 0], matBackwardProb[:, 0])
        #print("L", L)
        
        X = (matBackwardProb * matEmitProb)[:, 1:] * (self.c**rc_ttp1) / L
        xi_tsum = HMM.matTransProb * np.dot(matForwardProb[:, :-1], np.transpose(X))#matrix C
        
        gamma = matForwardProb * matBackwardProb * (self.c**rc_tt) / L#matrix G
        gamma_tsum = np.sum(gamma, axis= 1)#vector g
        #print("gamma_sum", gamma_sum)
        
        return gamma, gamma_tsum, xi_tsum#matrix G, vector g, matrix C (of one trajectory)
    
    
    def reestimate_BaumWelch(self, HMM, reprVal, G_choice, gamma_tsum, xi_tsum):
        
        # calculate transition probabilities
        #================================================================================
        denominator = []
        for s in range(HMM.N_asyState):
            denominator.append(gamma_tsum[s] + gamma_tsum[s+HMM.N_asyState] + gamma_tsum[s+2*HMM.N_asyState])
        
        matAsyTransProb = self.calculateAsyTransProb(HMM, xi_tsum, denominator)
        self.calculateFullTransProb(HMM, matAsyTransProb)
        #=================================================================================
        
        # calculate asymmetric dwell positions & stds
        #=================================================================================
        E = G_choice / gamma_tsum
        
        for i in range(HMM.N_asyState):
            
            x_stack = []
            w_stack = []
            
            for n in range(3):
            
                x_stack += list(reprVal - 120.0*n)
                w_stack += list(E[:, i + n*HMM.N_asyState])
            
            HMM.vecAsyState[i], HMM.vecEmitStd[i] = self.calculateCircularMean(np.array(x_stack), np.array(w_stack))
        #=================================================================================
        
        return 0
    
    
    def __call__(self, HMM, trajs, offset):
        
        g = np.zeros(HMM.N_state)#vector g
        C = np.zeros((HMM.N_state, HMM.N_state))#matrix C
        G_choice = np.zeros((self.N_bin, HMM.N_state))
        L_all = 0.0
        
        for t_camera, vecObs, _ in trajs:
            
            self.print_sys("%.2f+%.2f|"%(t_camera[0], t_camera[-1] - t_camera[0]))
            
            N_timePoint = len(vecObs)
            vecObs_mod360 = (vecObs + offset) % 360.0
            obsGroup = self.discretizeData(vecObs_mod360, self.bins)
            
            matEmitProb, matForwardProb, matBackwardProb, rc_forward, rc_backward, L_tot_1traj = self.calculate2wardProb_fast(HMM, N_timePoint, vecObs_mod360)
            gamma, gamma_tsum, xi_tsum = self.calculateTemporaryVars_BW(HMM, matEmitProb, matForwardProb, matBackwardProb, rc_forward, rc_backward)
            
            L_all += L_tot_1traj
            g += gamma_tsum
            C += xi_tsum
            
            for n in range(self.N_bin):
                for t in obsGroup[n]:
                    G_choice[n] += gamma[:, t]
            
        self.reestimate_BaumWelch(HMM, self.reprVal, G_choice, g, C)
        
        offset -= HMM.vecAsyState[0]
        
        HMM.vecAsyState -= HMM.vecAsyState[0]
        HMM.vecAsyState %= 120.0
        
        self.print_sys(" *\n")
        
        return L_all, offset
