#! usr/bin/env python
# -*- coding: utf-8 -*-

# By Yixin Chen. Last edited: 25/12/2024

class Variant:
    
    def __init__(self, confs, v_index, activeConf):
        
        if confs == "ohc":
            self.confStates = [0, 1, 2]
            self.cStatesTag = {0: "open", 1: "half-closed", 2: "closed"}
            self.varNames = ["G_O", "G_H", "G_C",
                             "AG_BETA", "AG_GAMMA", "AG_CHEM",
                             "AG_OT", "AG_OD", "AG_HT", "AG_HD", "AG_CT", "AG_CD",
                             "BG_OT", "BG_OD", "BG_HT", "BG_HD", "BG_CT", "BG_CD"]
            
            self.stepwiseConfTrans = {0: [1],
                                      1: [0, 2],
                                      2: [1]}
            
            if v_index == 1:

                self.gbCoupling_cat = {0: [0],
                                       1: [0, 1, 2],
                                       2: [0, 1]}
                self.gbCoupling_wait = {0: [0],
                                        1: [0, 1],
                                        2: [0, 1, 2]}

            elif v_index == 2:

                self.gbCoupling_cat = {0: [0, 1],
                                       1: [0, 1, 2],
                                       2: [0, 1, 2]}
                self.gbCoupling_wait = {0: [0],
                                        1: [0, 1, 2],
                                        2: [0, 1, 2]}
            
            elif v_index == 3:

                self.gbCoupling_cat = {0: [0, 1],
                                       1: [0, 1, 2],
                                       2: [0, 1, 2]}
                self.gbCoupling_wait = {0: [0],
                                        1: [0, 1],
                                        2: [0, 1, 2]}
                                        
            elif v_index == 4:

                self.gbCoupling_cat = {0: [0],
                                       1: [0, 1],
                                       2: [0, 1, 2]}
                self.gbCoupling_wait = {0: [0],
                                        1: [0],
                                        2: [0, 1, 2]}

            elif v_index in [5, 6, 7]:
                
                self.gbCoupling_cat = {0: [0, 1],
                                       1: [0, 1, 2],
                                       2: [0]}

                if v_index == 5:

                    self.gbCoupling_wait = {0: [0],
                                            1: [0, 1],
                                            2: [0]}

                elif v_index == 6:

                    self.gbCoupling_wait = {0: [0],
                                            1: [0, 1],
                                            2: [0, 1]}
            
                elif v_index == 7:

                    self.gbCoupling_wait = {0: [0],
                                            1: [0, 1],
                                            2: [0, 1, 2]}

            
            elif v_index in [8, 9]:

                self.gbCoupling_cat = {0: [0, 1],
                                       1: [0, 1, 2],
                                       2: [0, 1]}
                
                if v_index == 8:
                    self.gbCoupling_wait = {0: [0],
                                            1: [0, 1],
                                            2: [0, 1]}
                
                elif v_index == 9:
                    self.gbCoupling_wait = {0: [0],
                                            1: [0, 1],
                                            2: [0, 1, 2]}
            
        
        elif confs == "ohca":
            self.confStates = [0, 1, 2, 3]
            self.cStatesTag = {0: "open", 1: "half-closed", 2: "closed", 3: "closed*"}
            self.varNames = ["G_O", "G_H", "G_C", "G_C*",
                             "AG_BETA", "AG_GAMMA", "AG_CHEM",
                             "AG_OT", "AG_OD", "AG_HT", "AG_HD", "AG_CT", "AG_CD", "AG_C*T", "AG_C*D", 
                             "BG_OT", "BG_OD", "BG_HT", "BG_HD", "BG_CT", "BG_CD", "BG_C*T", "BG_C*D"]

            self.stepwiseConfTrans = {0: [1],
                                      1: [0, 2, 3],
                                      2: [1, 3],
                                      3: [1, 2]}
            
            i, j, k = v_index//100, (v_index%100)//10, v_index%10

            if i == 1:
              self.gbCoupling_cat = {0: [0, 1],
                                     1: [0, 1, 2],
                                     2: [0, 1, 2, 3]}
            
            elif i == 2:
              self.gbCoupling_cat = {0: [0, 1],
                                     1: [0, 1, 2],
                                     2: [0, 1, 3]}
            
            elif i == 3:
              self.gbCoupling_cat = {0: [0, 1],
                                     1: [0, 1, 2, 3],
                                     2: [0, 1, 3]}

            if k == 0:
                  self.gbCoupling_wait = {0: [0],
                                          1: [0, 1],
                                          2: [0, 1]}
            elif k == 1:
                  self.gbCoupling_wait = {0: [0],
                                          1: [0, 1],
                                          2: [0, 1, 2]}

            elif k == 2:
                  self.gbCoupling_wait = {0: [0],
                                          1: [0, 1],
                                          2: [0, 1, 3]}

            elif k == 3:
                  self.gbCoupling_wait = {0: [0],
                                          1: [0, 1],
                                          2: [0, 1, 2, 3]}
            
            if j == 2:
                  self.gbCoupling_wait[1].append(3)

            #elif j == 1: nothing changes
        
        self.activeConf = activeConf
        self.inactiveConf = [each for each in self.confStates if each not in activeConf]
        self.version = "%s-v%d-%s"%(confs, v_index, "".join([confs[c] for c in activeConf]))
