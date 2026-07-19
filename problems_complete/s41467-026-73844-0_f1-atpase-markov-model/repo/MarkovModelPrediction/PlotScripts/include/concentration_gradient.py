#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 25/12/2024

import numpy as np
from scipy.optimize import curve_fit


class BindingModel:
    
    @staticmethod
    def f1(x, kd1, n1):
        return n1*x/(x+kd1)
    
    @staticmethod
    def f2(x, kd1, kd2, n1, n2):
        return n1*x/(x+kd1)+n2*x/(x+kd2)

    @staticmethod
    def f2a(x, kd1, kd2):
        return 2.0*x/(x+kd1)+x/(x+kd2)
        
    @staticmethod
    def f3(x, kd1, kd2, kd3, n1, n2, n3):
        return n1*x/(x+kd1)+n2*x/(x+kd2)+n3*x/(x+kd3)
        
    @staticmethod
    def f3a(x, kd1, kd2, kd3):
        return x/(x+kd1)+x/(x+kd2)+x/(x+kd3)



class ConcentrationGradient:

    def __init__(self, angle_cat=80, expDataDir = "./include/ExpDataLib",
                 style_exp=dict(fmt="o", ecolor="blue", capsize=2,
                              markeredgewidth=0.5, markersize=3,
                              markeredgecolor="black", markerfacecolor="white", 
                              zorder=1000),
                 style_exp_fit=dict(color="grey", ls=":", lw=0.8),
                 
                 style_predict=dict(color="tab:blue", alpha=0.6, linewidth=0.8),
                 style_predict_alt=dict(color="tab:orange", alpha=0.6, linewidth=0.8),
                 style_predict_fit=dict(ls=":", color="darkred", lw=0.8)):
        
        self.titration_exp = dict()
        for which in ["ATP", "ADP", "mix"]:
            self.titration_exp[which] = self.__readExpTitCurve(which, expDataDir)
            
        self.turnover_exp = [np.array([-6, -5, -4, -3]), np.array([1.951, 16.00, 57.14, 76.92])]

        self.__trans_modes = ["+ATP", "-ADP", "HYD"]
        self.__rot_dwells = [angle_cat, 120, angle_cat+120, 240, angle_cat+240, 360]
        
        self.log_c = dict()
        self.data = dict()

        self.configs = []

        self.style_exp = style_exp
        self.style_exp_fit = style_exp_fit
        
        self.style_predict = style_predict
        self.style_predict_alt = style_predict_alt
        self.style_predict_fit = style_predict_fit

    
    def __readExpTitCurve(self, which, expDataDir):
        
        log_conc, occ = [], []

        with open("%s/F1-ATPase_%s.bind.csv"%(expDataDir, which), "r") as file:
            lines = file.readlines()
        for line in lines[1:]:
            line = line.split(",")
            log_conc.append(float(line[0]))
            occ.append(float(line[1]))
        
        return [np.array(log_conc), np.array(occ)]


    def __calculateTheoreticalOccupancy(self, conc, which, 
                                        Kd1 = {"ATP": 16e-9, "ADP": 41e-9},
                                        Kd2 = {"ATP": 1.5e-6, "ADP": 6e-6},
                                        Kd3 = {"ATP": 29e-6, "ADP": 42e-6}):
        
        if which in ["ATP", "ADP"]:
            return conc/(conc+Kd1[which]) + conc/(conc+Kd2[which]) + conc/(conc+Kd3[which])
        
        else:
            return np.zeros(len(log_conc))-1.0
            

    def estimateExpTitrationError(self, which):

        concs = list(10**self.titration_exp[which][0][::3]) + [10**self.titration_exp[which][0][-1]]
        occ_exp = list(self.titration_exp[which][1][::3]) + [self.titration_exp[which][1][-1]]
        
        occ_model = self.__calculateTheoreticalOccupancy(np.array(concs), which)
        std = np.sqrt(sum((occ_model - np.array(occ_exp))**2)/len(occ_model))
        print(std)
        
        return std

    
    def plotTitration_exp(self, ax, which):
        ax.errorbar(10**self.titration_exp[which][0], self.titration_exp[which][1], 0.1,
                   label = "experimental data", **self.style_exp)
        
        ax.plot(np.logspace(-9, 0, 91), 
                self.__calculateTheoreticalOccupancy(np.logspace(-9, 0, 91), which),
                **self.style_exp_fit)
        
        ax.set_ylabel("Occupancy", fontsize = 10)
        ax.set_ylim(0, 3.5)
        ax.set_yticks([0, 1, 2, 3])
        ax.set_yticklabels([0, 1, 2, 3], fontsize = 9)
        
        ax.set_xlabel("[%s] ($\\mathrm{\\mu}$M)"%which, fontsize=10)
        ax.set_xscale("log")
        ax.set_xlim(10**(-7.5), 10**(-2.5))
        ax.set_xticks(10.0**np.arange(-7, -2.2, 1))
        ax.set_xticklabels([0.1, 1, 10, "$10^2$", "$10^3$"], fontsize=9, rotation=25)
        
        return


    def plotTurnover_exp(self, ax, v_max=80., K_M=4.0e-5):

        ax.errorbar(10.0**self.turnover_exp[0], np.log10(self.turnover_exp[1]), 1.,
                   **self.style_exp)

        x = np.logspace(-9, 0, 91)
        ax.plot(np.logspace(-9, 0, 91), np.log10(v_max*x/(x+K_M)),
                **self.style_exp_fit)
        
        ax.set_ylabel("$k_\\mathrm{cat}$ (s$^{-1}$)", fontsize = 10)
        ax.set_yticks(np.linspace(-1, 3, 5))
        ax.set_yticklabels(["$10^{%.0f}$"%y for y in np.linspace(-1, 3, 5)], fontsize=9)
        ax.set_ylim(-1.5, 3.)
        
        ax.set_xlabel("[ATP] ($\\mathrm{\\mu}$M)", fontsize=10)
        ax.set_xscale("log")
        ax.set_xlim(10**(-7.5), 10**(-2.5))
        ax.set_xticks(10.0**np.arange(-7, -2.2, 1))
        ax.set_xticklabels([0.1, 1, 10, "$10^2$", "$10^3$"], fontsize=9, rotation=25)
        
        return


    def plotEfficiency_exp(self, ax):
        
        ax.errorbar(10.0**self.turnover_exp[0], np.ones(np.shape(self.turnover_exp[0])), 0.2,
                   **self.style_exp)

        ax.axhline(1., **self.style_exp_fit)

        ax.set_ylabel("Efficiency", fontsize=10)
        ax.set_yticks(np.linspace(0.5, 1.5, 3))
        ax.set_ylim(0.25, 1.75)
        
        ax.set_xlabel("[ATP] ($\\mathrm{\\mu}$M)", fontsize=10)
        ax.set_xscale("log")
        ax.set_xlim(10**(-7.5), 10**(-2.5))
        ax.set_xticks(10.0**np.arange(-7, -2.2, 1))
        ax.set_xticklabels([0.1, 1, 10, "$10^2$", "$10^3$"], fontsize=9, rotation=25)

        return
        
    
    def load(self, filePath):

        try:
            with open(filePath, "r") as file:
                lines = file.readlines()
        except FileNotFoundError:
            print("! Warning: %s not Found"%filePath)
            return 0
        
        self.log_c.clear()
        self.data.clear()
        
        self.log_c["ATP"] = []
        self.log_c["ADP"] = []
        
        for each in ["k_cat", "k_rot",
                     "occ_tot", "occ_ATP", "occ_ADP",
                     "pop_cat", "pop_wait"]:
            self.data[each] = []
            
        for trans in self.__trans_modes:
            for dwell in self.__rot_dwells:
                self.data["%s_%d"%(trans, dwell)] = []
       
        if len(self.configs) == 0:
            labels = lines[0].strip().split(",")
            for n, label in enumerate(labels):
                if label.startswith("80-") or label.startswith("120-"):
                    self.configs.append((n, label))
       
        for _, config in self.configs:
            self.data[config] = []
        
        for line in lines[1:]:
            
            line = np.array((line.strip()).split(","), dtype = float)
            
            self.log_c["ATP"].append(line[0])
            self.log_c["ADP"].append(line[1])
            
            self.data["k_cat"].append(line[2])
            self.data["k_rot"].append(line[3])
            
            self.data["occ_tot"].append(line[4])
            self.data["occ_ATP"].append(line[5])
            self.data["occ_ADP"].append(line[6])

            self.data["pop_cat"].append(line[7])
            self.data["pop_wait"].append(line[8])
            
            for i, trans in enumerate(self.__trans_modes):
                for j, dwell in enumerate(self.__rot_dwells):
                    self.data["%s_%d"%(trans, dwell)].append(line[9+i*6+j])
            
            for (n, config) in self.configs:
                self.data[config].append(line[n])

        for each in self.log_c:
            self.log_c[each] = np.array(self.log_c[each])
            
        for each in self.data:
            self.data[each] = np.array(self.data[each])

        return 1
    
    
    def plotTurnover(self, ax, which, fit=False):
        
        concs = 10.00**self.log_c[which]
        ax.plot(concs, np.log10(self.data["k_cat"]), **self.style_predict)

        if fit:
            res = self.__fit_turnover(concs, self.data["k_cat"])
            if res != 0:
                ax.plot(res[0], res[1], **self.style_predict_fit)
        
        return
    
    
    def plotDwellPopulation(self, ax, which):
        
        concs = 10.0**self.log_c[which]
        
        ax.plot(concs, self.data["pop_wait"], **self.style_predict)
        ax.plot(concs, self.data["pop_cat"], **self.style_predict_alt)
        
        return


    def plotTitration(self, ax, which, fit=False, plot_fit=False):
        
        concs = 10.0**self.log_c[which]
        ax.plot(concs, self.data["occ_tot"], label = "model prediction", **self.style_predict)
        
        #ax.scatter(10.0**model_tit[0], model_tit[1]["ATP"], label = "occ. by ATP", marker = "^", edgecolor = "darkblue", color = "white", s = 60, linewidth = 2)
        #ax.scatter(10.0**model_tit[0], model_tit[1]["ADP"], label = "occ. by ADP", marker = "D", edgecolor = "darkblue", color = "white", s = 60, linewidth = 2)

        if fit:
            res, r_sq, Kd = self.__fit_titration_curve(concs, self.data["occ_tot"])
            if plot_fit and res != 0:
                ax.plot(res[0], res[1], **self.style_predict_fit)
        
            return r_sq, Kd

        return

    
    def plotEfficiency(self, ax, which):

        concs = 10.00**self.log_c[which]
        ax.plot(concs, 3*self.data["k_rot"]/self.data["k_cat"], **self.style_predict)

        return
        

    def plotOcc(self, ax, which_tit, which_plot):
        
        concs = 10.0**self.log_c[which_tit]

        if which_plot in ["ATP", "ADP"]:
            ax.plot(concs, self.data["occ_%s"%which_plot], label = "model prediction", **self.style_predict)

        elif which_plot == "ratio":
            ax.plot(concs, self.data["occ_ADP"]/self.data["occ_ATP"], label = "model prediction", **self.style_predict)
        
        return


    
    def plotConfigPopulation(self, ax, which, configs=None):
        
        concs = 10.0**self.log_c[which]
        
        if configs is None:
            return

        pops = np.zeros(np.shape(concs))

        for config in configs:
            if config in self.data:
                pops += self.data[config]
        
        ax.plot(concs, pops, label="+".join(configs), **self.style_predict)
        
        return

    
    @staticmethod
    def __MichaelisMenten(x, v_max, K_M):
        return v_max*x/(x+K_M)
    
    
    def __fit_turnover(self, conc, rate):
        
        func = self.__MichaelisMenten
        
        try:
            popt, pcov = curve_fit(func, conc, rate, p0 = [80.0, 1e-5], bounds = (0.0, 1e3))
            y_fit = func(conc, *popt)
            y_aver = np.average(rate)
            r_sq = 1 - np.dot(y_fit - rate, y_fit - rate)/np.dot(y_aver - rate, y_aver - rate)
            
            params_MM = [(popt[i], np.sqrt(np.diag(pcov))[i]) for i in range(2)]
            
            print("R^2=%.4f"%r_sq)
            
            print("v_max=%.2f +- %.2f"%(params_MM[0][0], params_MM[0][1]))
            print("K_M=%.1e +- %.1e"%(params_MM[1][0], params_MM[1][1]))
            
            return [np.logspace(-9, 0, 51), func(np.logspace(-9, 0, 51), *popt)]
        
        except RuntimeError:
        
            print("Curve fit failed")
            return np.logspace(-9, 0, 51), func(np.logspace(-9, 0, 51), 0., 0.)



    def __fit_titration_curve(self, conc, occ):
        
        func = BindingModel.f3a
        
        try:
            popt, pcov = curve_fit(func, conc, occ, bounds = (0.0, 1.0), p0 = [41e-9, 6e-6, 42e-6])
            y_fit = func(conc, *popt)
            y_aver = np.average(occ)
            r_sq = 1 - np.dot(y_fit - occ, y_fit - occ)/np.dot(y_aver - occ, y_aver - occ)
            
            Kd = [(popt[i], np.sqrt(np.diag(pcov))[i]) for i in range(3)]
            Kd.sort(key = lambda x: x[0])

            '''
            print("R^2=%.4f"%r_sq)
            
            for i in range(3):
                print("K_d%d=%.2e +- %.2e"%(i+1, Kd[i][0], Kd[i][1]))
            '''
            
            return [conc, func(conc, *popt)], r_sq, Kd
        
        except RuntimeError:
        
            print("Curve fit failed")
            return 0, 0, 0
