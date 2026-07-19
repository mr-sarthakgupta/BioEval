#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 25/12/2024

import numpy as np
from include.concentration_gradient import ConcentrationGradient
from matplotlib import pyplot as plt

class CoarseGrainedPathway():
    
    def __init__(self, angle_cat=80, shadowColors=None):

        self.N_paramSets = 0
        
        self.N_dwells = 6
        self.__dwells = [120, angle_cat+120, 240, angle_cat+240, 360, angle_cat]
        
        self.__transModes = ["+ATP", "HYD", "-ADP"]
        
        self.probs = dict()
        self.probs_sorted = dict()
        self.paramIndex_sorted = []

        if shadowColors is None:
            tab20_cmap = plt.cm.get_cmap("Pastel1")
            self.shadowColors = [tab20_cmap(i) for i in range(tab20_cmap.N)]
        else:
            self.shadowColors = [] + shadowColors

        self.instance = ConcentrationGradient()
    
    
    def __getProbs(self, filePaths, cT):
        
        self.probs.clear()
        self.N_paramSets = 0
        
        for fp in filePaths:
            
            flag = self.instance.load(fp)
            if not flag:
                print("%s not found"%fp)
                continue

            self.N_paramSets += 1
            
            i = np.argmin(abs(self.instance.log_c["ATP"] - np.log10(cT)))
            for trans in self.__transModes:
                if trans not in self.probs:
                    self.probs[trans] = []

                self.probs[trans].append([\
                    self.instance.data["%s_%d"%(trans, dwell)][i]\
                    for dwell in self.__dwells\
                ])

                rate = 0.
                for n, dwell in enumerate(self.__dwells):
                    if self.probs[trans][-1][n] < 0.:
                        self.probs[trans][-1][n] = 0.
                    rate += self.probs[trans][-1][n]

                for n, dwell in enumerate(self.__dwells):
                    self.probs[trans][-1][n] /= rate
        
        for trans in self.__transModes:
            self.probs[trans] = np.array(self.probs[trans])

        '''
        fig, ax = plt.subplots()
        for i, dwell in enumerate(self.__dwells):
            plt.plot([0, 1], [i, i], color=self.shadowColors[i], lw = 2, label="%d"%dwell)
            
        plt.legend()
        plt.show()
        plt.close()
        '''
        
        return
    

    def __sortParamSets(self, probs, sortDwells=None):
    
        paramGroup = {r: [] for r in range(self.N_dwells)}
        
        for n in range(self.N_paramSets):
            #r_max = np.argmax(probs[n])
            #paramGroup[r_max].append(n)
            paramGroup[0].append(n)

        if sortDwells is None:
            sortDwells = range(self.N_dwells)
    
        accumProb = np.zeros(self.N_paramSets)
        for r in sortDwells:
            accumProb += probs[:, r]
            
            maxProb_with_index = list(zip(paramGroup[r], [accumProb[n] for n in paramGroup[r]]))
            maxProb_with_index.sort(key = lambda x: x[1], reverse = True)
        
            self.paramIndex_sorted += [x[0] for x in maxProb_with_index]
    
        
        for r in range(self.N_dwells):
            
            if r not in sortDwells:
                maxProb_with_index = list(zip(paramGroup[r], [probs[n][r] for n in paramGroup[r]]))
                maxProb_with_index.sort(key = lambda x: x[1], reverse = True)
        
                self.paramIndex_sorted += [x[0] for x in maxProb_with_index]
        
        return


    def __plotProbs(self, ax, probs, plotDwells=None, plotThreshold=0.0):
    
        if plotDwells is None:
            if plotThreshold == 0.0:
                plotDwells = range(self.N_dwells)
            else:
                plotDwells = []
                for r in range(self.N_dwells):
                    if max(probs[:, r]) > plotThreshold:
                        plotDwells.append(r)
        
        accumProb = np.zeros(self.N_paramSets)
    
        for r in plotDwells:
            
            dwell_probs = probs[:, r]#[list(range(100))+list(range(300, self.N_paramSets))]
            
            ax.bar(np.arange(self.N_paramSets)+1., dwell_probs, bottom = accumProb, label = self.__dwells[r], color = self.shadowColors[r], width = 1.)

            accumProb += dwell_probs
            

        #ax.bar(np.arange(self.N_paramSets), np.ones(self.N_paramSets)-accumProb, bottom = accumProb, label = "Other dwell(s)", color = "darkred", width=1.)
        #ax.legend()
    
        return

    '''
    def __find_most_likely_pathway(self, outFileName, most_likely_ns = 3):
        
        with open("%s.pathway.csv"%outFileName, "w") as file:
            file.write("PARAM_INDEX")
            for trans in self.trans_modes:
                for i in range(most_likely_ns):
                    file.write(",%s-#%d_MODE,PROB"%(trans.upper(), i+1))
            file.write("\n")
            
            for n, par_index in enumerate(self.paramIndex_sorted):
                file.write("%d"%par_index)

                for trans in self.trans_modes:
                    rot_mode_probs_sorted = sorted([(i, self.probs_sorted["bind"][n][i]) for i in range(self.N_dwells)], key=lambda x: x[1], reverse=True)
                    for i in range(most_likely_ns):
                        file.write(",%s,%.6f"%(self.rot_modes[rot_mode_probs_sorted[i][0]],
                                               rot_mode_probs_sorted[i][1]))
                
                file.write("\n")
                
        return
    '''


    def __call__(self, filePaths, outFileName, workdir=".",sort=True, tick=None):

        '''
        with open("%scT=1e-6.pathway.csv"%outFileName, "r") as file:
            lines = file.readlines()
            
        for line in lines[1:]:
            line = line.strip().split(",")
            self.paramIndex_sorted.append(int(line[0]))
        '''
        
        W = 17.18/2.54

        fig, ax = plt.subplots(3, 2, figsize = (W/2, W/2), sharex = True, sharey = True)
        
        #self.__getProbs(filePaths, 1e-6)
        #self.__sortParamSets(self.probs["+ATP"], sortDwells = [0])

        self.__getProbs(filePaths, 1e-7)
        
        if sort:
            self.__sortParamSets(self.probs["+ATP"], sortDwells = [0])
        else:
            self.paramIndex_sorted = range(self.N_paramSets)
            
        for a, trans in enumerate(self.__transModes):
            self.probs_sorted[trans] = np.array([self.probs[trans][n] for n in self.paramIndex_sorted])
            self.__plotProbs(ax[a][0], self.probs_sorted[trans], plotThreshold = 0.0)
        
        #self.__find_most_likely_pathway(outFileName+"_cT=1e-7")
        
        self.__getProbs(filePaths, 1e-3)
        for a, trans in enumerate(self.__transModes):
            self.probs_sorted[trans] = np.array([self.probs[trans][n] for n in self.paramIndex_sorted])
            self.__plotProbs(ax[a][1], self.probs_sorted[trans], plotThreshold = 0.0)
            
        #self.__find_most_likely_pathway(outFileName+"_cT=1e-3")
        
        for i in range(3):
            ax[i][0].set_ylim(0., 1.)
            ax[i][0].set_yticks([0., 0.5, 1.0])
            ax[i][0].set_yticklabels(["0", "0.5", "1"], fontsize=10)
            #ax[i][0].set_ylabel("Accu. probability")

        if tick is None:
            tick = self.N_paramSets
            
        for i in range(2):
            ax[2][i].set_xlim(0.5, self.N_paramSets+0.5)
            ax[2][i].set_xticks([1, tick])
            ax[2][i].set_xticklabels([1, tick], fontsize=10)
            #ax[2][i].set_xlabel("#ParameterSet", fontsize=12) 

        #ax[0][1].legend()
        #ax[1][1].legend()
        #ax[2][1].legend()
        '''
        for i in range(3):
          for j in range(2):
              ax[i][j].axvline(43.5, color="black", lw=1)
              ax[i][j].axvline(48.5, color="black", lw=1)
              ax[i][j].axvline(52.5, color="black", lw=1)

              #ax[i][j].legend()
        '''
        
        #plt.tight_layout()
        plt.savefig("%s/pathway_%s.png"%(workdir, outFileName), dpi = 500, transparent = True)
        #plt.show()

        return self.paramIndex_sorted