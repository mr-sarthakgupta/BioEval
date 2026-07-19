#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 27/08/2024
*************************************************/

# include "prep.h"


void assign(struct Parameter* paras, double* values)
/* values = [G_beta_o, G_beta_h, G_beta_c1, G_beta_c2,  //0-3, conformation energy
			 Ga_beta, Ga_gamma, Ga_chem, //4-6, activation energy (energy barrier)
			 Ga_b-s, //7-14, activation energy (energy barrier of binding)
			 dG_b-s, //15-22, binding free energy
			 iG, //23, interaction energy between gamma and beta_1 when gamma@120 && beta_1 is open
			]
*/
{
	int i = 0, j = 0;

	for (i = 0; i < DIM_CONF; i++) { paras->E_beta[i] = values[i]; }

	paras->k_beta = ATT_FREQ * exp(-values[DIM_CONF]);
	paras->k_gamma = ATT_FREQ * exp(-values[DIM_CONF+1]);
	paras->k_chem = ATT_FREQ * exp(-values[DIM_CONF+2]);
	
	for (i = 0; i < DIM_CONF; i++)
	{
		for (j = 0; j < 2; j++)
		{
			paras->k_b[i][j] = ATT_FREQ * exp(-values[(DIM_CONF + 3) + 2 * i + j]);
			paras->E_b[i][j] = values[(3*DIM_CONF + 3) + 2 * i + j];
		}
	}

	paras->E_gb = values[5*DIM_CONF + 3]; //printf("E_gb=%.2f\n", paras->E_gb);
	//printf("%.1f,%.1f,%.1f,%.1f\n", paras->E_beta[0], paras->E_beta[2], paras->E_b[0][1], paras->E_b[1][1]);
}

double calculateZeta(double k_cat, double catRate_exp)// k_cat compared with experimental value
{
	double zeta = 0.0;

	if (k_cat <= 0.0) { zeta = log10(1.0e-10); }
	else { zeta = log10(k_cat / catRate_exp); }

	return zeta;
}

double calculateEta(double k_cat, double k_rot)// (3*k_rot)/k_cat
{
	double eta = 0.0;

	if (k_cat == 0.0) { eta = 0.0; }
	else { eta = (k_rot * 3.0) / k_cat; }

	return eta;
}



double calculateScore(struct Setting* settings, struct State* states, struct Transition* transitions,
	struct Variable* vars,
	double val[DIM_VAL],
	struct ExpData* exps, struct TempStorage* tempStore)
{
	int i = 0; double score = 0.0, occ = 0.0, eta = 0., zeta = 0.;
	
    for (i = 0; i < vars->numVar; i++)
	{
		if (vars->prior[0][i] > 0.0)//Gaussian distribution
		{
			score += - (val[vars->indexVar[i]] - vars->prior[1][i]) * (val[vars->indexVar[i]] - vars->prior[1][i]) 
				/ (STD_FACTOR * STD_FACTOR * vars->prior[2][i] * vars->prior[2][i]);
		}
		// else, uniform distribution, no contribution to the score function
	}
	

    for (i = 0; i < exps->numGroup; i++)
	{		
		calculateRates(states, transitions, exps, tempStore, i);

		zeta = calculateZeta(tempStore->k_cat[i], exps->data[2][i]);
		eta = calculateEta(tempStore->k_cat[i], tempStore->k_rot[i]);
		
                score += - zeta * zeta / (settings->stdZeta * settings->stdZeta);
		score += - (eta - 1.0) * (eta - 1.0) / (settings->stdEta * settings->stdEta);

		//printf("(%10.4f,%10.4f)\n", tempStore->k_cat[j], tempStore->k_rot[j]);
	}


	if (settings->occ_on == 1)
	{
		for (i = 0; i < exps->numOccData; i++)
		{
			occ = calculateOcc(states, transitions, tempStore, pow(10.0, exps->occ[0][i]), pow(10.0, exps->occ[1][i]));
			score += -(occ - exps->occ[2][i]) * (occ - exps->occ[2][i]) / (settings->stdOcc * settings->stdOcc);
		}
	}

	return score;
}


void writeFile(FILE* fp, double val[DIM_VAL], double score, double* k_cat, double* k_rot, int numExp, int step, int trial, int title)
{
	int i = 0;
	
	if (title == 1)
	{
		if (DIM_VAL == 19)
		{
			fprintf(fp, "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,",
					"STEP", "TRIAL",
					"G_O", "G_H", "G_C",
					"GA_BETA", "GA_GAMMA", "GA_CHEM",
					"GA_OT", "GA_OD", "GA_HT", "GA_HD", "GA_CT", "GA_CD",
					"BG_OT", "BG_OD", "BG_HT", "BG_HD", "BG_CT", "BG_CD",
					"IG_120-O",
					"SCORE");//change with model
		}

		else if (DIM_VAL == 24)
		{
			fprintf(fp, "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,",
				"STEP", "TRIAL",
				"G_O", "G_H", "G_C", "G_C*",
				"GA_BETA", "GA_GAMMA", "GA_CHEM",
				"GA_OT", "GA_OD", "GA_HT", "GA_HD", "GA_CT", "GA_CD", "GA_C*T", "GA_C*D",
				"BG_OT", "BG_OD", "BG_HT", "BG_HD", "BG_CT", "BG_CD", "BG_C*T", "BG_C*D",
				"IG_120-O",
				"SCORE");//change with model
		}

		for (i = 0; i < numExp; i++) { fprintf(fp, "K_CAT_%d,K_ROT_%d,", i + 1, i + 1); }
		fprintf(fp, "\n");
	}

	fprintf(fp, "%d,%d,", step, trial);
	for (i = 0; i < DIM_VAL; i++) { fprintf(fp, "%.4f,", val[i]); }
	fprintf(fp, "%.7f,", score);
	for (i = 0; i < numExp; i++) { fprintf(fp, "%.2e,%.2e,", k_cat[i], k_rot[i]); }
	fprintf(fp, "\n");
}


void sampleRandomSet(struct Setting* settings, struct Variable* vars, double val[DIM_VAL], struct TempStorage* tempStore)
{
	int i = 0; for (i = 0; i < vars->numVar; i++)
	{
		if (vars->prior[0][i] < 0.0)//uniform distribution
		{
			val[vars->indexVar[i]] = generateUniformRand(tempStore->randPool,
				vars->prior[1][i], vars->prior[2][i]);
		}
		else if (vars->prior[0][i] > 0.0)//Gaussian distribution
		{
			val[vars->indexVar[i]] = generateUniformRand(tempStore->randPool,
				vars->prior[1][i] - GAUSSIAN_CUTOFF * vars->prior[2][i],
				vars->prior[1][i] + GAUSSIAN_CUTOFF * vars->prior[2][i]);
		}
	}
      
        printf("%d\n", settings->N_activeConf);
	if (settings->constHydrEnergy == 1)
	{
		for (i = 0; i < settings->N_activeConf; i++)
		{ 
                    val[(3*DIM_CONF + 3) + 2 * settings->activeConf[i]] = val[(3*DIM_CONF + 3) + 2 * settings->activeConf[i] + 1] - HYDR_ENERGY;
        
                    printf("%d", settings->activeConf[i]);
	            for (int k = 0; k < DIM_VAL; k++) { printf(",%.4f,", val[k]); }
                    printf("\n");
                }
	}
}


void sampleInitialGuess(struct Setting* settings, struct State* states, struct Transition* transitions,
	struct Variable* vars, struct ExpData* exps, struct TempStorage* tempStore)
{
	// Initialize variables needed in the function================================
	int i = 0, j = 0;
	double score = 0.0, score_best = -1.0e5;
	double val_try[DIM_VAL] = { 0.0 };
	for (i = 0; i < DIM_VAL; i++) { val_try[i] = vars->initVal[i]; }// IMPORTANT! Ensure that the variables that are not changed come from the input file rather than remain zero

	char fileName[50]; sprintf(fileName, "F1-ATPase_stdeta=%.2f.init.csv", settings->stdEta);
	FILE* fp = fopen(fileName, "w");
	//================================================================
	
	assign(tempStore->paras, vars->initVal);
	score = calculateScore(settings, states, transitions, vars, vars->initVal, exps, tempStore);
	writeFile(fp, vars->initVal, score, tempStore->k_cat, tempStore->k_rot, exps->numGroup, 0, 0, 1);
	printf("INITIAL GUESS = %d, SCORE = %.4e\n", 0, score);

	for (i = 1; i < settings->N_initGuess + 1; i++)
	{
		sampleRandomSet(settings, vars, val_try, tempStore);
		assign(tempStore->paras, val_try);
		
		score = calculateScore(settings, states, transitions, vars, val_try, exps, tempStore);
		writeFile(fp, val_try, score, tempStore->k_cat, tempStore->k_rot, exps->numGroup, 0, i + 1, 0);
		printf("INITIAL GUESS = %d, SCORE = %.4e\n", i + 1, score);

		if (score > score_best)
		{
			score_best = score;
			for (j = 0;j < DIM_VAL; j++)
			{ vars->initVal[j] = val_try[j]; }
		}
	}
	
	fclose(fp);
}


void sampleNewGuess(struct Setting* settings, struct Variable* vars, double val_try[DIM_VAL], double val_old[DIM_VAL], struct TempStorage* tempStore, double stdSearch)
{
	//generate Gaussian-distributed new guesses within the given range

	int i = 0, j = 0, v = 0, v_activeConf = 0, flag = 0;

	for (i = 0; i < vars->numVar; i++)
	{
		v = vars->indexVar[i];
            	
                if (settings->constHydrEnergy == 1) {
                    flag = 0;
		    for (j = 0; j < settings->N_activeConf; j++) {
			v_activeConf = (3*DIM_CONF + 3) + 2 * settings->activeConf[j];
                        if (v == v_activeConf) { flag = 1; break; }
		    }
               
                    if (flag) continue;
	        }
                
                val_try[v] = generateGaussRand(tempStore->randPool, val_old[v], stdSearch);
		
                if (vars->prior[0][i] < 0.0)//uniform distribution
		{
			while (val_try[v]<vars->prior[1][i] || val_try[v]>vars->prior[2][i]) {
				val_try[v] = generateGaussRand(tempStore->randPool,
					val_old[v], stdSearch);
			}
		}

		else if (vars->prior[0][i] > 0.0)//Gaussian distribution
		{
			while (val_try[v]<(vars->prior[1][i] - GAUSSIAN_CUTOFF * vars->prior[2][i]) || val_try[v]>(vars->prior[1][i] + GAUSSIAN_CUTOFF * vars->prior[2][i])) {
				val_try[v] = generateGaussRand(tempStore->randPool,
					val_old[v], stdSearch);
			}
		}
	}

	if (settings->constHydrEnergy == 1)
	{
                //printf("%d\n", settings->N_activeConf);

		for (i = 0; i < settings->N_activeConf; i++) {
			val_try[(3*DIM_CONF + 3) + 2 * settings->activeConf[i]] = val_try[(3*DIM_CONF + 3) + 2 * settings->activeConf[i] + 1] - HYDR_ENERGY;
                    
                        //printf("%d", settings->activeConf[i]);
	                //for (int k = 0; k < DIM_VAL; k++) { printf(",%.4f,", val_try[k]); }
                        //printf("\n");
		}
	}
}


double tryOneSearch(struct Setting* settings, struct State* states, struct Transition* transitions, 
	struct Variable* vars, struct ExpData* exps, struct TempStorage* tempStore, 
	double val_old[DIM_VAL], double val_try[DIM_VAL], double stdSearch)
{
	int i = 0, v = 0;
	double score_try = 0.0;

	//generate Gaussian-distributed new guesses within the given range
	sampleNewGuess(settings, vars, val_try, val_old, tempStore, stdSearch);

	assign(tempStore->paras, val_try);

	score_try = calculateScore(settings, states, transitions, vars, val_try, exps, tempStore);
	//printf(">>>>>> TRIAL = %6d, SCORE = %12.4e\n", k + 1, score_try);
	
	return score_try;
}


void simpleOptimize(struct Setting* settings, struct State* states, struct Transition* transitions,
	struct Variable* vars, struct ExpData* exps, struct TempStorage* tempStore, int label)
{
	// Initialize variables needed in the function================================
	int i = 0, search = 0, v = 0, choice = 0, flag_found=0;
	char fileName_opt[50], fileName_trial[50];
	double score_old = 0.0, score_new = 0.0, score_try = 0.0;
    double STD_search = settings->std_search;

	double* k_cat_opt = malloc(exps->numGroup * sizeof(double));
	double* k_rot_opt = malloc(exps->numGroup * sizeof(double));

	double val_old[DIM_VAL], val_try[DIM_VAL], val_new[DIM_VAL];
	for (i = 0; i < DIM_VAL; i++) {
	    val_new[i] = vars->initVal[i]; val_old[i] = vars->initVal[i]; val_try[i] = vars->initVal[i];
	}// IMPORTANT! Ensure that the variables that are not changed come from the input file rather than remain zero
	//========================================================================

	// Initialize optimization================================================
	assign(tempStore->paras, val_new);
	score_new = calculateScore(settings, states, transitions, vars, val_new, exps, tempStore);
	for (i = 0; i < exps->numGroup; i++) { k_cat_opt[i] = tempStore->k_cat[i]; k_rot_opt[i] = tempStore->k_rot[i]; }

	sprintf(fileName_trial, "F1-ATPase_%d.trial.csv", label);
	FILE* fp_trial = fopen(fileName_trial, "w");
	writeFile(fp_trial, val_new, score_new, tempStore->k_cat, tempStore->k_rot, exps->numGroup, 0, 1, 1);
	fclose(fp_trial);

	sprintf(fileName_opt, "F1-ATPase_%d.opt.csv", label);
	FILE* fp_opt = fopen(fileName_opt, "w");
	writeFile(fp_opt, val_new, score_new, tempStore->k_cat, tempStore->k_rot, exps->numGroup, 0, 1, 1);
	fclose(fp_opt);
	//================================================================

	// Start iteration======================================================
	int optStep = 0;
	while (optStep == 0 || optStep < settings->N_goodSetStep || (score_new < settings->score_goodSetCriterion && optStep < settings->N_maxStep))
	{
		optStep += 1;
		score_old = score_new;
		for (i = 0; i < vars->numVar; i++) { v = vars->indexVar[i]; val_old[v] = val_new[v];}

		printf(">>>> STEP = %6d, STD_SEARCH=%.4f\n", optStep, STD_search);

		fp_trial = fopen(fileName_trial, "a");
		flag_found = 0;

		for (search = 0; search < settings->N_search; search++)// try numSearch of points around the current guess and move to the maximum
		{
			score_try = tryOneSearch(settings, states, transitions, vars, exps, tempStore, val_old, val_try, STD_search);
			writeFile(fp_trial, val_try, score_try, tempStore->k_cat, tempStore->k_rot, exps->numGroup, optStep, search + 1, 0);

			if (score_try >= score_new)
			{
				score_new = score_try;
				for (i = 0; i < vars->numVar; i++) { v = vars->indexVar[i]; val_new[v] = val_try[v]; choice = search + 1; }
				for (i = 0; i < exps->numGroup; i++) { k_cat_opt[i] = tempStore->k_cat[i]; k_rot_opt[i] = tempStore->k_rot[i]; }
				flag_found = 1;
			}
		}

		fclose(fp_trial);

		fp_opt = fopen(fileName_opt, "a");
		writeFile(fp_opt, val_new, score_new, k_cat_opt, k_rot_opt, exps->numGroup, optStep, choice, 0);
		fclose(fp_opt);
        
		if (!flag_found) STD_search *= settings->f_shrink;
		else STD_search = settings->std_search;
	}
	//==============================================================

	free(k_cat_opt); free(k_rot_opt);
}
