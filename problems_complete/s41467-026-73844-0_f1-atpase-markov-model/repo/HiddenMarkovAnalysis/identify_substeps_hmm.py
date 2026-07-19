#!usr/bin/env python
#-*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 04/04/2023

import numpy as np
from matplotlib import pyplot as plt
from hmm_miscellaneous import*
from hmm_expectation import*
from hmm_maximization import*
#from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit


class FileOperation(Miscellaneous):
    
    
    def readRecFile_simTraj(self, fileName):
    
        t_camera, vecObs = [], []

        with open("%s.rec.csv"%fileName, "r") as file:
        
            line = file.readline()#skip the first line, which contains title
            
            line = file.readline()
            while line:
                line = line.split(",")
                
                if len(line) >= 3:
                    t_camera.append(float(line[0]))
                    vecObs.append(float(line[2]))
                    
                line = file.readline()
        
        return np.array(t_camera), np.array(vecObs)
    
    
    def writeOutFile_proc(self, filePath, fileName, t_camera, vecObs, regularRotRegion):
    
        with open(".//%s//%s_processed.traj.csv"%(filePath, fileName), "w") as file:
            
            for s, (t_i, t_f) in enumerate(regularRotRegion):
                file.write("TRAJECTORY PART #,%d\n"%(s+1))
                
                plt.plot(t_camera[t_i:t_f], vecObs[t_i:t_f], zorder = 30)
                
                for t in range(t_i, t_f, 1):
                
                    file.write("%.6f,%.6f\n"%(t_camera[t], vecObs[t]))
        
        return 0
    
    
    def readRecFile_proc(self, filePath, fileNames):
        
        trajs = []
        
        for fileName in fileNames:
            
            with open(".//%s//%s_processed.traj.csv"%(filePath, fileName), "r") as file:
                
                line = file.readline()
                while line:
                    if line[0] == "T":
                        trajs.append([[], [], (fileName, int(line.split(",")[1]))])
                    else:
                        line = line.split(",")
                        trajs[-1][0].append(float(line[0]))
                        trajs[-1][1].append(float(line[1]))
                    line = file.readline()
        
        for each in trajs:
            each[0] = np.array(each[0])
            each[1] = np.array(each[1])
        
        return trajs
    
    
    def writeOutFile_BW(self, filePath, fileName, step, HMM, L_tot, offset):
        
        with open(".//%s//%s_BW.csv"%(filePath, fileName), "a") as file:
            
            file.write("%d,%.4f,%.4f"%(step, L_tot, offset))
          
            for i in range(HMM.N_asyState):
                file.write(",%.2f,%.2f"%(HMM.vecAsyState[i], HMM.vecEmitStd[i]))
            
            for i in range(HMM.N_asyState):
                for j in range(HMM.N_state):
                    file.write(",%.6e"%(HMM.matTransProb[i][j]))
            
            file.write("\n")
            
        return 0
    
    
    def readRecFile_BW(self, filePath, fileName, lineIndex, HMM):
        
        with open(".//%s//%s_BW.csv"%(filePath, fileName), "r") as file:
            
            lines = file.readlines()
        
        line = lines[lineIndex].split(",")
        for i in range(HMM.N_asyState):
            HMM.vecAsyState[i] = float(line[3 + 2*i])
            HMM.vecEmitStd[i]  = float(line[3 + 2*i + 1])
        for i in range(HMM.N_asyState):
            for j in range(HMM.N_state):
                HMM.matTransProb[i][j] = float(line[3 + 2*HMM.N_asyState + (i*HMM.N_state + j)])
        
        matAsyTransProb = HMM.matTransProb[:HMM.N_asyState]
        
        HMM.matTransProb[HMM.N_asyState:2*HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState]     = matAsyTransProb[:, :HMM.N_asyState]
        HMM.matTransProb[2*HMM.N_asyState:3*HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState] = matAsyTransProb[:, :HMM.N_asyState]
      
        HMM.matTransProb[HMM.N_asyState:2*HMM.N_asyState, :HMM.N_asyState]                   = matAsyTransProb[:, 2*HMM.N_asyState:3*HMM.N_asyState]
        HMM.matTransProb[2*HMM.N_asyState:3*HMM.N_asyState, HMM.N_asyState:2*HMM.N_asyState] = matAsyTransProb[:, 2*HMM.N_asyState:3*HMM.N_asyState]

        HMM.matTransProb[HMM.N_asyState:2*HMM.N_asyState, 2*HMM.N_asyState:3*HMM.N_asyState] = matAsyTransProb[:, HMM.N_asyState:2*HMM.N_asyState]
        HMM.matTransProb[2*HMM.N_asyState:3*HMM.N_asyState, :HMM.N_asyState]                 = matAsyTransProb[:, HMM.N_asyState:2*HMM.N_asyState]
        
        return float(line[2])
    
    
    def writeOutFile_infer(self, file, HMM, dwellPos, s, t_camera, vec_obs_reloc, vecAssignedState):
        
        N_timePoint = len(t_camera)
        
        file.write("TRAJECTORY PART #,%d\n"%(s+1))
        for t in range(N_timePoint):
            
            angle_res = dwellPos[vecAssignedState[t]]
            inferred_angle = angle_res + 360.0*round((vec_obs_reloc[t] - angle_res)/360.0)
            
            file.write("%.6f,%.6f,%.6f,%d\n"%(t_camera[t], vec_obs_reloc[t], inferred_angle, vecAssignedState[t]))
            
        return 0
    
    
    def readRecFile_infer(self, outFilePath, outFileName, fileNames, w):
        
        assignedState = []
        
        for fileName in fileNames:
            
            with open(".//%s//%s_infer_%s,w=%.1e.traj.csv"%(outFilePath, fileName, outFileName, w), "r") as file:
            
                line = file.readline()
                while line:
                    
                    if line[0] == "T":
                        assignedState.append([])
                    
                    else:
                    
                        line = line.split(",")
                        assignedState[-1].append(int(line[3]))
                    
                    line = file.readline()
        
        return assignedState
    
    
    def writeOutFile_lifetime(self, filePath, fileName, N_dwells, lifetime):
    
        with open(".//%s//%s.lifetime.csv"%(filePath, fileName), "w") as file:
            
            for i in range(N_dwells):
                lifetime[i] = list(filter(lambda x: x != 0.0, lifetime[i]))
                file.write("HIDDEN STATE #%d\n"%i)
                for each in lifetime[i]:
                    file.write("%.6e\n"%each)
                
        return 0


    def readRecFile_lifetime(self, filePath, fileName, N_dwells):
        
        lifetime = {i: [] for i in range(N_dwells)}

        with open(".//%s//%s.lifetime.csv"%(filePath, fileName), "r") as file:
            lines = file.readlines()

        for line in lines:
        
            if line[0] == "H":
                s = int(line[-2])
        
            else:
                lifetime[s].append(float(line[:-1]))
        
        return lifetime


class GetProcessedTraj(FileOperation):
    
    
    def findRegularRotateRegion(self, vecObs, std_cutoff, interval_cutoff, N_window):
    
        (lower, upper), obs_aver, obs_std = self.calculateSlideSTD_bs(vecObs, N_window)
        
        index_largeSTD = []
        regularRotateRegion = []
        
        for n, std in enumerate(obs_std):
            if std > std_cutoff:
                index_largeSTD.append(n + lower)
                
                if len(index_largeSTD) >= 2 and index_largeSTD[-1] - index_largeSTD[-2] > interval_cutoff:
                    regularRotateRegion.append([index_largeSTD[-2] + 1, index_largeSTD[-1]])
        
        if len(index_largeSTD) >= 1:
        
            if index_largeSTD[0] > 1:
                regularRotateRegion.append([lower, index_largeSTD[0]+lower])
            
            if index_largeSTD[-1] < len(obs_std) - 2:
                regularRotateRegion.append([index_largeSTD[-1] + 1 + lower, len(obs_std) + lower])
        
        else:
            regularRotateRegion.append([lower, len(obs_std) + lower])
        
        return regularRotateRegion, (lower, upper), obs_aver, obs_std
    
    
    def calculateIntervalAtExpResolution(self, t_camera, fps_exp):
        
        dt = t_camera[1] - t_camera[0]
        dt_exp = 1./fps_exp
        
        self.print_sys(">>>> dt_EXP = %.1e, dt_SIM = %.1e, "%(dt_exp, dt))
        
        if dt <= dt_exp:
            n = round(dt_exp/dt)
            self.print_sys("trajectory filtered to experimental resolution by interval %d\n"%n)
        
        else:
            n = 1
            self.print_sys("trajectory can't reach experimental resolution\n")
        
        return int(n)
    
    
    def preprocessObs(self, filePath, fileNames, fps_exp, sigma_gauss, std_cutoff, interval_cutoff, N_window):
        
        print(">> Start pre-processing...")
        
        #fig, ax = plt.subplots(figsize = (5, 2))

        for fileName in fileNames:
            
            print("* Working on file %s *"%fileName)
            
            t_camera, vecObs = self.readRecFile_simTraj(fileName)
            print(">>>> Reading finished!")
            #vecObs = gaussian_filter1d(vecObs, sigma = sigma_gauss)
            #print(">>>> Filtering finished!")
            
            interval_expRes = self.calculateIntervalAtExpResolution(t_camera, fps_exp)
            t_camera, vecObs = t_camera[::interval_expRes], vecObs[::interval_expRes]
            
            regularRotRegion, (lower, upper), obs_aver, obs_std = self.findRegularRotateRegion(vecObs, std_cutoff, interval_cutoff, N_window)
            
            plt.plot(t_camera, vecObs, lw = 1, zorder = 1, color = "grey")
            plt.plot(t_camera[lower:upper], obs_aver[:(upper-lower)], zorder = 20)
            plt.fill_between(t_camera[lower:upper], obs_aver[:(upper-lower)] + obs_std, obs_aver[:(upper-lower)] - obs_std, facecolor = "lightblue", edgecolor = "blue", zorder = 10)
            
            self.writeOutFile_proc(filePath, fileName, t_camera, vecObs, regularRotRegion)
            
            plt.show()
            plt.close()
        
        return 0
    
    
    def __call__(self, preprocess, outFilePath, recFileNames, fps_exp=1e-4, sigma_gauss=20., std_cutoff=0., interval_cutoff=0., N_window=0):
        
        if preprocess == True:
            self.preprocessObs(outFilePath, recFileNames, fps_exp, sigma_gauss, std_cutoff, interval_cutoff, N_window)
        else:
            print(">> Pre-processed trajectories already exist!")
        
        trajs = self.readRecFile_proc(outFilePath, recFileNames)
        dt = trajs[0][0][1] - trajs[0][0][0]
        
        return dt, trajs


class GetHMMParams(FileOperation):
    
    
    def calculateDwellPosition(self, HMM):
        
        dwellPos = np.zeros(HMM.N_state)
        for i in range(HMM.N_state):
            dwellPos[i] += HMM.vecAsyState[i%HMM.N_asyState] + 120.0*(i//HMM.N_asyState)
        
        return dwellPos
    
    
    def runBaumWelch(self, outFilePath, outFileName, trajs, HMM, N_iter, errorbar, M_step):
    
        print(">> Start running Baum-Welch algorithm...")
        
        # Prepare variable
        L_tot_old, L_tot_new = 0.0, 0.0
        offset = 0.0
        #------------------------------------------------------------------------------
        
        # Optimize HMM parameters
        with open(".//%s//%s_BW.csv"%(outFilePath, outFileName), "w") as file:
                
                file.write("STEP,LIKELIHOOD,OFFSET")
                for i in range(HMM.N_asyState):
                    file.write(",ANGLE#%d,STD#%d"%(i+1, i+1))
                file.write(",TRANS_PROB\n")
                
        k = 0
        while (k <= 2 or\
               (k <= N_iter and (L_tot_new-L_tot_old) > errorbar)):# condition of convergence
                
            print(">>>> Start step %d..."%k)
            self.print_sys("* Working on ")
            
            L_tot_old = L_tot_new
            
            L_tot_new, offset = M_step(HMM, trajs, offset)
            
            self.writeOutFile_BW(outFilePath, outFileName, k, HMM, L_tot_new, offset)
            
            print(">>>> step %d, L_tot = %.6e"%(k, L_tot_new))
            
            k += 1
        #---------------------------------------------------------------------------------
        
        return offset
    
    
    def __call__(self, run_BW, outFilePath, outFileName, trajs, HMM_init, N_bin, c, N_iter, errorbar, BW_lineIndex):
        
        HMM = HiddenMarkovModel(HMM_init.vecAsyState, HMM_init.vecEmitStd, HMM_init.matTransProb)
        M_step = Maximization(N_bin, c)
        
        if run_BW == True:
            
            offset = self.runBaumWelch(outFilePath, outFileName, trajs, HMM, N_iter, errorbar, M_step)
        
        else:
            
            if BW_lineIndex >= 0:
                print(">> Optimized HMM parameters already exist!")
                offset = self.readRecFile_BW(outFilePath, outFileName, BW_lineIndex, HMM)
            
            else:
                print(">> HMM parameters are given!")
                offset = 0.0
        
        print(">>>> Dwells: %s"%(",".join(["%.4f +- %.4f"%(HMM.vecAsyState[i], HMM.vecEmitStd[i]) for i in range(HMM.N_asyState)])))
        print(">>>> Transition probability matrix =")
        print(HMM.matTransProb)
        print(">>>> Offset = %.4f"%offset)
        
        dwellPos = self.calculateDwellPosition(HMM)
        
        return HMM, offset, dwellPos
    


class GetAssignedSeq(FileOperation):
    
    def runViterbi(self, outFilePath, outFileName, w, trajs, HMM, dwellPos, offset):
        
        E_step = Expectation(c = 1e-8)#c value doesn't matter here
        
        print(">> Start state assignment (w = %.1e)..."%w)
        self.print_sys("* Working on ")
        
        assignedState_list = []
        
        for t_camera, vecObs, (fileName, s) in trajs:
            
            self.print_sys("%.2f+%.2f|"%(t_camera[0], t_camera[-1] - t_camera[0]))
            
            vecObs_mod360 = (vecObs + offset) % 360.0
            vecAssignedState = E_step.assignStates_viterbi(HMM, vecObs_mod360, w)
            
            with open(".//%s//%s_infer_%s,w=%.1e.traj.csv"%(outFilePath, fileName, outFileName, w), "a") as file_infer:
                self.writeOutFile_infer(file_infer, HMM, dwellPos, s, t_camera, vecObs + offset, vecAssignedState)
            
            assignedState_list.append(vecAssignedState)
            
        self.print_sys(" *\n")
        
        return assignedState_list
    
    
    def __call__(self, run_viterbi, outFilePath, outFileName, recFileNames, w, HMM, dwellPos, offset):
    
        if run_viterbi == True:# Do state assignment and obtain lifetime
        
            for fileName in recFileNames:
                
                file_infer = open(".//%s//%s_infer_%s,w=%.1e.traj.csv"%(outFilePath, fileName, outFileName, w), "w")
                file_infer.close()

                dt, trajs = GetProcessedTraj()(False, outFilePath, [fileName])
                assignedState = self.runViterbi(outFilePath, outFileName, w, trajs, HMM, dwellPos, offset)
        
        else:
            print(">> Hidden Markov states of the given trajectories have already been assigned!")
            assignedState = self.readRecFile_infer(outFilePath, outFileName, recFileNames, w)
        
        return assignedState
        
    

class AnalyzeAssignedSeq(FileOperation):
    
    
    def partitionAssignedSeq(self, vecAssignedState):
    
        dwellSeq = [[vecAssignedState[0], 0, 0]]
        
        for t in range(1, len(vecAssignedState)):
            
            if vecAssignedState[t] == dwellSeq[-1][0]:
                dwellSeq[-1][2] = t
            
            else:
                dwellSeq.append([vecAssignedState[t], t, t])
        
        return dwellSeq
    
    
    def partitionAssignedSeq_merge(self, vecAssignedState):
    
        dwellSeq = [[(vecAssignedState[0]//2)*2, 0, 0]]
        
        for t in range(1, len(vecAssignedState)):
            
            if (vecAssignedState[t]//2) == (dwellSeq[-1][0]//2):
                
                #print(dwellSeq[-1][0], vecAssignedState[t])
                dwellSeq[-1][2] = t
            
            else:
                dwellSeq.append([(vecAssignedState[t]//2)*2, t, t])
        
        return dwellSeq
   

    def reconstructAssignedSeq(self, vecAssignedState, dwellSeq):
        
        vecAssignedState_re = vecAssignedState[:dwellSeq[0][1]]
        
        for s, t_i, t_f in dwellSeq:
            vecAssignedState_re += [s]*(t_f - t_i + 1)
        
        vecAssignedState_re += vecAssignedState[(dwellSeq[-1][2] + 1):]
        
        return vecAssignedState_re
    
    
    def calculateLifetime_old(self, lifetime, vecAssignedState, dt):
    
        s_now = vecAssignedState[0]
        lifetime[s_now].append(0.0)
        
        for t in range(1, len(vecAssignedState)):
            lifetime[s_now][-1] += dt
            s_next = vecAssignedState[t]
            if s_next != s_now:
                s_now = s_next
                lifetime[s_now].append(0.0)
    
        return 0
        
    
    def calculateLifetime(self, lifetime, dwellSeq, dt):
    
        for s, t_i, t_f in dwellSeq:
            
            dwellTime = (t_f - t_i)*dt
            
            if s in lifetime:
                lifetime[s].append(dwellTime)
            else:
                lifetime[s] = [dwellTime]
        
        return 0
    
    
    def postViterbi(self, lifetime, dwellSeq, dt, shortDwellCutoff):
        
        N_dwellSeq = len(dwellSeq)
        
        dwellSeq_new = []
        
        for m in range(N_dwellSeq):
            if (dwellSeq[m][2] - dwellSeq[m][1]) * dt > 0.0:#0.1*shortDwellCutoff:
                dwellSeq_new.append(dwellSeq[m])
                break
        
        n = m + 1
        
        while n < N_dwellSeq - 1:
            
            if      ((dwellSeq[n][2] - dwellSeq[n][1]) * dt <= shortDwellCutoff)\
                and (dwellSeq[n+1][0] == dwellSeq_new[-1][0]):
                
                dwellSeq_new[-1][2] = dwellSeq[n+1][2]
                n += 2
            
            else:
                dwellSeq_new.append(dwellSeq[n])
                n += 1
        
        self.calculateLifetime(lifetime, dwellSeq_new, dt)
        
        return dwellSeq_new
    
    
    def __call__(self, post_viterbi, outFilePath, outFileName, recFileNames, w, HMM, dwellPos, offset, assignedState, shortDwellCutoff):

        dt, trajs = GetProcessedTraj()(False, outFilePath, recFileNames)
        
        if post_viterbi == True:
            for fileName in recFileNames:
                file_infer = open(".//%s//%s_infer_%s,w=%.1e,cutoff=%.1e.traj.csv"%(outFilePath, fileName, outFileName, w, shortDwellCutoff), "w")
                file_infer.close()
        
        lifetime = {i: [] for i in range(HMM.N_state)}
        
        for n, vecAssignedState in enumerate(assignedState):
            
            dwellSeq = self.partitionAssignedSeq_merge(vecAssignedState)
            
            if post_viterbi == True:
                dwellSeq = self.postViterbi(lifetime, dwellSeq, dt, shortDwellCutoff)
                vecAssignedState_re = self.reconstructAssignedSeq(list(vecAssignedState), dwellSeq)
                
                t_camera, vecObs, (fileName, s) = trajs[n]
                
                with open(".//%s//%s_infer_%s,w=%.1e,cutoff=%.1e.traj.csv"%(outFilePath, fileName, outFileName, w, shortDwellCutoff), "a") as file_infer:
                    self.writeOutFile_infer(file_infer, HMM, dwellPos, s, t_camera, vecObs + offset, vecAssignedState_re)
            
            self.calculateLifetime(lifetime, dwellSeq, dt)
        
        self.writeOutFile_lifetime(outFilePath, "%s_w=%.1e,cutoff=%.1e"%(outFileName, w, shortDwellCutoff), HMM.N_state, lifetime)
        
        return lifetime
    
    
def analyzeTrajectory(recFileNames, HMM_init,
                      outFilePath, outFileName,
                      
                      preprocess = True,
                      fps_exp = 1e4,
                      sigma_gauss = 20.0, 
                      std_cutoff = 240.0, interval_cutoff = 1000, N_window = 100,
                      
                      run_BW = True,
                      BW_lineIndex = -999,
                      N_bin = 360, c = 1e-8,
                      N_iter = 10, errorbar = 1.0,
                      
                      run_viterbi = True,
                      weights = [25.0],
                      
                      post_viterbi = True,
                      short_dwell_cutoff = 0.0):
        
        
        dt, trajs = GetProcessedTraj()(preprocess, outFilePath, recFileNames, fps_exp, sigma_gauss, std_cutoff, interval_cutoff, N_window)
        
        HMM, offset, dwellPos = GetHMMParams()(run_BW, outFilePath, outFileName, trajs, HMM_init, N_bin, c, N_iter, errorbar, BW_lineIndex)
        
        for w in weights:
            assignedState = GetAssignedSeq()(run_viterbi, outFilePath, outFileName, recFileNames, w, HMM, dwellPos, offset)
            AnalyzeAssignedSeq()(post_viterbi, outFilePath, outFileName, recFileNames, w, HMM, dwellPos, offset, assignedState, short_dwell_cutoff)
        
        return 0
