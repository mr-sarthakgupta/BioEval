import numpy as np
from matplotlib import pyplot as plt

from include.concentration_gradient import ConcentrationGradient
from include.CG_pathway import CoarseGrainedPathway


dict_variables = {"G_O":      ["Y", "U", -23.0, 23.0, 0.0, "N"],
                  "G_H":      ["Y", "U", -23.0, 23.0, 0.0, "N"],
                  "G_C":     ["N", "N", -23.0, 23.0, 0.0, "N"],
                  "G_C*":     ["Y", "U", -23.0, 23.0, 0.0, "N"],
                  
                  "AG_BETA":  ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  "AG_GAMMA": ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  "AG_CHEM":  ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  
                  "AG_OT":    ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  "AG_OD":    ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  "AG_HT":    ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  "AG_HD":    ["Y", "U", 0.0, 20.72, 4.6, "N"],
                  "AG_CT":   ["N", "N", 0.0, 20.72, 13.8, "N"],
                  "AG_CD":   ["N", "N", 0.0, 20.72, 13.8, "N"],
                  "AG_C*T":   ["N", "N", 0.0, 20.72,13.8, "N"],
                  "AG_C*D":   ["N", "N", 0.0, 20.72,13.8, "N"],
                  
                  "BG_OT":    ["Y", "U", -69.078, 0.0, -6.27, "N"],
                  "BG_OD":    ["Y", "U", -69.078, 0.0, -6.40, "N"],
                  "BG_HT":    ["Y", "U", -69.078, 0.0, -6.27, "N"],
                  "BG_HD":    ["Y", "U", -69.078, 0.0, -6.40, "N"],
                  "BG_CT":   ["Y", "U", -69.078, 0.0, -12.00, "N"],
                  "BG_CD":   ["Y", "U", -69.078, 0.0, -12.00, "N"],
                  "BG_C*T":   ["Y", "U", -69.078, 0.0, -12.00, "N"],
                  "BG_C*D":   ["Y", "U", -69.078, 0.0, -12.00, "N"],
                  
                  "IG_120-O": ["N", "N", -23.0, 23.0, -2.3026, "N"]}

labels_str = "SET,POINT,G_O,G_H,G_C,G_C*,AG_BETA,AG_GAMMA,AG_CHEM,AG_OT,AG_OD,AG_HT,AG_HD,AG_CT,AG_CD,AG_C*T,AG_C*D,BG_OT,BG_OD,BG_HT,BG_HD,BG_CT,BG_CD,BG_C*T,BG_C*D,IG_120-O,SCORE,K_CAT_1,K_ROT_1,K_CAT_2,K_ROT_2,K_CAT_3,K_ROT_3,K_CAT_4,K_ROT_4"
labels = labels_str.split(",")

instance = ConcentrationGradient(style_exp=dict(fmt="o", lw=0.5, ecolor="blue", capsize=1.5, capthick=0.5,
                                                markeredgewidth=0.8, markersize=2.5,
                                                markeredgecolor="blue", markerfacecolor="white", 
                                                zorder=1000),
                                 style_exp_fit=dict(color="blue", ls=":", dash_capstyle="round", lw=1, zorder=800),
                                 
                                 style_predict=dict(color="#FAD5D8", alpha=0.1, linewidth=0.5),
                                 style_predict_alt=dict(color="lightskyblue", alpha=0.1, linewidth=0.5),
                                 style_predict_fit=dict(ls=":", color="darkred", lw=0.8))


def plot_predictions(param_indices, pred_folder, outfilename, workdir = "."):

    W = 17.18/2.54
    
    fig, ax = plt.subplots(2, 3, figsize=(W, W/3*(9/16)*2))
    plt.subplots_adjust(wspace=0.5, hspace=0)
    
    Kds = []
    
    for k in param_indices:
        
        flag = instance.load("%s/SteadyStates_cD=1.00e-09_set=%d.csv"%(pred_folder, k))
        if flag:
            instance.plotTurnover(ax[0][0], which="ATP")
            instance.plotEfficiency(ax[1][0], which="ATP")
        
        flag = instance.load("%s/SteadyStates_cD=1.00e-18_set=%d.csv"%(pred_folder, k))
        if flag:
            instance.plotTitration(ax[0][1], which="ATP")
        
        flag = instance.load("%s/SteadyStates_cT=1.00e-18_set=%d.csv"%(pred_folder, k))
        if flag:
            r_sq, Kd = instance.plotTitration(ax[1][1], which="ADP", fit=True, plot_fit=False)
            Kds.append([Kd[0][0], Kd[1][0], Kd[2][0]])
    
    instance.plotTurnover_exp(ax[0][0])
    instance.plotEfficiency_exp(ax[1][0])
    instance.plotTitration_exp(ax[0][1], which="ATP")
    instance.plotTitration_exp(ax[1][1], which="ADP")
    
    Kds = np.log10(np.transpose(np.array(Kds)))
    N = len(Kds[0])
    
    ax[0][2].axhline(np.log10(41e-9), zorder=100, color="blue")#"#E9ADCE")
    ax[0][2].axhline(np.log10(6e-6), zorder=100, color="blue")#"#FBC7BD")
    ax[0][2].axhline(np.log10(42e-6), zorder=100, color="blue")#"#94CCCB")
    
    ax[0][2].plot(range(1, N+1), Kds[0], lw=2, zorder=10, color="#E9ADCE")
    ax[0][2].plot(range(1, N+1), Kds[1], lw=2, zorder=20, color="#FBC7BD")
    ax[0][2].plot(range(1, N+1), Kds[2], lw=2, zorder=10, color="#94CCCB")
    
    ax[0][2].set_ylim(-9, -3)
    ax[0][2].set_yticks([-8, -6, -4])
    ax[0][2].set_yticklabels(["$10^{%d}$"%n for n in [-8, -6, -4]], fontsize=9)
    ax[0][2].set_ylabel("$K_{\\mathrm{d}1,2,3}$", labelpad=0)
    
    ax[0][2].set_xlabel("#Parameter set")
    ax[0][2].set_xlim(0, len(param_indices))
    ax[0][2].set_xticks([1, 500])
    
    ax[0][0].set_xticks([])
    ax[0][1].set_xticks([])
    ax[0][0].set_xlabel("")
    ax[0][1].set_xlabel("")
    ax[1][1].set_xlabel("[Nuc] ($\\mathrm{\\mu}$M)")
    
    ax[1][2].set_visible(False)
    pos = ax[1][2].get_position()
    ax[0][2].set_position([pos.x0, pos.y0, pos.width, pos.height*2])
    
    ax[1][0].set_ylabel("Efficiency", labelpad=12)
    ax[0][1].yaxis.set_label_coords(-0.2, -0.05)
    ax[1][1].set_ylabel("")
    
    ax[0][2].set_xlabel("#Parameter set", labelpad=13)

    plt.savefig("%s/predictions_%s.png"%(workdir, outfilename),  dpi = 500, bbox_inches = "tight", transparent = True)
    plt.show()
    plt.close()

    return Kds





def plot_config_pops(param_indices, pred_folder, outfilename, workdir="."):

    W = 17.18/2.54

    fig, ax = plt.subplots(1, 5, figsize=(W, W/5*4/5), sharey=True)

    pops = []

    for k in param_indices:

        flag = instance.load("%s/SteadyStates_cD=1.00e-09_set=%d.csv"%(pred_folder, k))
        if flag:
            instance.plotConfigPopulation(ax[0], which="ATP", configs=["80-hca", "80-hcc", "80-haa"])
            instance.plotConfigPopulation(ax[1], which="ATP", configs=["80-oca", "80-occ", "80-oaa"])
            instance.plotConfigPopulation(ax[3], which="ATP", configs=["120-ohc", "120-oha"])
            instance.plotConfigPopulation(ax[2], which="ATP", configs=["120-ooc", "120-ooa"])
            instance.plotConfigPopulation(ax[4], which="ATP", configs=["120-oaa", "120-oac", "120-oca"])

            pops.append((k, instance.data["120-ohc"][0]+instance.data["120-oha"][0]))

    for i in range(5):
        ax[i].set_xlabel("[ATP] ($\\mathrm{\\mu}$M)", fontsize=10)
        ax[i].set_xscale("log")
        ax[i].set_xlim(10**(-8.5), 10**(-2.5))
        ax[i].set_xticks(10.0**np.arange(-7, -2.2, 1))
        ax[i].set_xticklabels([0.1, 1, 10, "$10^2$", "$10^3$"], fontsize=9, rotation=25)

    plt.savefig("%s/config-pops_%s.png"%(workdir, outfilename),  dpi = 500, bbox_inches = "tight", transparent = True)
    plt.show()
    plt.close()

    return pops




def plot_population_shift(param_indices, pred_folder, outfilename, workdir="."):

    W = 17.18/2.54

    fig, ax = plt.subplots(1, 4, figsize=(W, W/4*4/5), sharey=True)

    count = [0, 0, 0, 0]

    pop_change = []

    for k in param_indices:

        flag = instance.load("%s/SteadyStates_cD=1.00e-09_set=%d.csv"%(pred_folder, k))
        if flag:
            if (instance.data["pop_cat"][0] < instance.data["pop_wait"][0])\
              and (instance.data["pop_cat"][-1] > instance.data["pop_wait"][-1]):
                nax = 0

            elif (instance.data["pop_cat"][0] > instance.data["pop_wait"][0])\
              and (instance.data["pop_cat"][-1] < instance.data["pop_wait"][-1]):
                nax = 1

            elif (instance.data["pop_cat"][0] < instance.data["pop_wait"][0])\
              and (instance.data["pop_cat"][-1] < instance.data["pop_wait"][-1]):
                nax = 2

            elif (instance.data["pop_cat"][0] > instance.data["pop_wait"][0])\
              and (instance.data["pop_cat"][-1] > instance.data["pop_wait"][-1]):
                nax = 3

            count[nax] += 1
            pop_change.append(instance.data["pop_cat"][0] - instance.data["pop_cat"][-1])

            instance.plotDwellPopulation(ax[nax], which="ATP")#wait: pink; cat: blue

    for i in range(4):
        ax[i].set_xlabel("[ATP] ($\\mathrm{\\mu}$M)", fontsize=10)
        ax[i].set_xscale("log")
        ax[i].set_xlim(10**(-7.5), 10**(-2.5))
        ax[i].set_xticks(10.0**np.arange(-7, -2.2, 1))
        ax[i].set_xticklabels([0.1, 1, 10, "$10^2$", "$10^3$"], fontsize=9, rotation=25)
        ax[i].set_ylim(-0.05, 1.05)
        ax[i].set_yticks([0, 0.5, 1])

    plt.savefig("%s/population-shift_%s.png"%(workdir, outfilename),  dpi = 500, bbox_inches = "tight", transparent = True)
    plt.show()

    return np.array(pop_change)


def plot_occ_ratio(param_indices, pred_folder, outfilename, workdir="."):

    W = 17.18/2.54

    fig, ax = plt.subplots(1, 4, figsize=(W, W/4*4/5), sharey=True)

    for k in param_indices:

        flag = instance.load("%s/SteadyStates_cD=1.00e-18_set=%d.csv"%(pred_folder, k))
        if flag:
            instance.plotOcc(ax[0], which_tit="ATP", which_plot="ratio")
            instance.plotTitration(ax[1], which="ATP")
            instance.plotOcc(ax[2], which_tit="ATP", which_plot="ATP")
            instance.plotOcc(ax[3], which_tit="ATP", which_plot="ADP")
            

    for i in range(4):
        ax[i].set_xlabel("[ATP] ($\\mathrm{\\mu}$M)", fontsize=10)
        ax[i].set_xscale("log")
        ax[i].set_xlim(10**(-7.5), 10**(-2.5))
        ax[i].set_xticks(10.0**np.arange(-7, -2.2, 1))
        ax[i].set_xticklabels([0.1, 1, 10, "$10^2$", "$10^3$"], fontsize=9, rotation=25)
        ax[i].set_ylim(-0.5, 3.5)
        ax[i].set_yticks([0, 1, 2, 3])
        ax[i].set_yticklabels([0, 1, 2, 3], fontsize=12)

    plt.savefig("%s/occupancy-ratio_%s.png"%(workdir, outfilename),  dpi = 500, bbox_inches = "tight", transparent = True)
    plt.show()

    return

