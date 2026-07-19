#!usr/bin/env python
#-*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 27/03/2023

import numpy as np
from sys import stdout

class HiddenMarkovModel:

  def __init__(self, vecAsyState, vecEmitStd, matTransProb):
    
    self.N_asyState = len(vecAsyState)
    self.N_state = 3*self.N_asyState
    self.vecAsyState = np.array(vecAsyState)
    self.vecEmitStd = np.array(vecEmitStd)
    self.matTransProb = np.array(matTransProb)


class Miscellaneous:
    
    def __init__(self):
        pass
    
    
    def calculateCircularMean(self, angle, w, rad = False):
        
        if rad == False:
            angle_rad = angle*np.pi/180.0
            x, y = np.cos(angle_rad), np.sin(angle_rad)
        else:
            x, y = np.cos(angle), np.sin(angle)
        x_aver, y_aver = np.dot(x, w)/sum(w), np.dot(y, w)/sum(w)
        
        mu = np.arctan(y_aver/x_aver)# unit: rad
        
        if rad == False:# unit of angle: degree
            mu *= 180.0/np.pi
        
        diff = self.calculateAngleDiff(angle, mu, rad)
        sigma = np.sqrt(np.dot(diff**2, w)/sum(w))
        
        return mu, sigma
    
    
    def calculateAngleDiff_univ(self, a1, a2, rad = False):
        
        if rad == False:
            a1 *= np.pi/180.0
            a2 *= np.pi/180.0
        
        x1, y1 = np.cos(a1), np.sin(a1)
        x2, y2 = np.cos(a2), np.sin(a2)
        
        d = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)
        
        angle = 2.0*np.arcsin(d/2.0)
        
        if rad == False:
            angle *= 180.0/np.pi

        return angle
    
    
    def calculateAngleDiff(self, angles, ref, rad = False):
        # unit of angles and ref should be the same
        
        if rad == False:
            angles1, ref1 = angles*1.0, ref*1.0
        else:
            angles1, ref1 = angles*180.0/np.pi, ref*180.0/np.pi
        
        return np.array(list(map(lambda x: abs(x-ref1) if (abs(x-ref1)<180.0) else (360.0-abs(x-ref1)), angles1)))
    
    
    def safelog(self, x):
   
        dims = np.shape(x)

        if len(dims) == 0:

            if x <= 0.0:
                return -1000.0
            else:
                return np.log(x)
        
        elif len(dims) == 1:
            
            return np.array(list(map(lambda a: -1000.0 if a <= 0.0 else np.log(a), x)))
            
        elif len(dims) == 2:
            
            return np.array([list(map(lambda a: -1000.0 if a <= 0.0 else np.log(a), x[i])) for i in range(dims[0])])
    
    
    def discretizeData(self, data, bins):
        
        indices = np.digitize(data, bins) - 1
        
        dataGroup = {n: [] for n in range(len(bins) - 1)}
        for t in range(len(data)):
            n = indices[t]
            dataGroup[n].append(t)
            
        return dataGroup
    
    
    def periodicGaussian(self, x, mu, sigma):
        
        diff = self.calculateAngleDiff(x, mu)
        return 1.0/(np.sqrt(2.0*np.pi)*sigma)*np.exp(-diff**2/(2*sigma**2))
    
    
    def calculateSlideSTD_rs(self, data, window):
        
        slideAverage = np.convolve(data, np.ones(window)/window, mode = "valid")
        slideSTD = np.sqrt(np.convolve((data[:-(window-1)] - slideAverage)**2, np.ones(window)/window, mode = "valid"))
        
        return (0, len(data)-(2*window-2)), slideAverage, slideSTD
    
    
    def calculateSlideSTD_ls(self, data, window):
        
        slideAverage = np.convolve(data, np.ones(window)/window, mode = "valid")
        slideSTD = np.sqrt(np.convolve((data[:-(window-1)] - slideAverage)**2, np.ones(window)/window, mode = "valid"))
        
        return (window-1, len(data)-(window-1)), slideAverage, slideSTD
        
    
    def calculateSlideSTD_bs(self, data, window):
        
        slideAverage = np.convolve(data, np.ones(window)/window, mode = "valid")
        slideSTD = np.sqrt(np.convolve((data[:-(window-1)] - slideAverage)**2, np.ones(window)/window, mode = "valid"))
        
        w_half = window//2
        
        return (w_half, len(data)-(2*window-2)+w_half), slideAverage, slideSTD
    
    
    def print_sys(self, text):
        
        stdout.write(text)
        stdout.flush()
        
        return 0
