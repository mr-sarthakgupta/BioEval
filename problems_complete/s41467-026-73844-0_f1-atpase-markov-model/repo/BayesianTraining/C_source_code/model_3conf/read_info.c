
#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 27/08/2024

*************************************************/

# include "prep.h"

void readVariables(FILE* fp, struct Variable* vars)
{
	char title[11], buff[75], varc1[11], varc2[11], varc3[11];
	double varn1 = 0.0, varn2 = 0.0, varn3 = 0.0;
	int v = 0, i = 0;
  
        fscanf(fp, "%10s%s\n", title, buff);//read version and pass to the next line
        printf("VERSION=%s\n", buff);
  
        fscanf(fp, "%10s%s\n", title, buff);
        vars->numVar = atoi(buff);

	vars->indexVar = malloc(vars->numVar * sizeof(int));
	for (i = 0; i < 3; i++) { vars->prior[i] = malloc(vars->numVar * sizeof(double)); }

	v = 0;
	for (i = 0; i < DIM_VAL; i++)
	{
		fscanf(fp, "%10s%10s%10s", title, buff, varc1);

		if (strcmp(varc1, "TRUE") == 0)
		{
			fscanf(fp, "%10s%lf%lf%lf%10s\n", varc2, &varn1, &varn2, &varn3, varc3);
			vars->indexVar[v] = i;

			if (strcmp(varc3, "kT") == 0) { vars->prior[1][v] = varn1; vars->prior[2][v] = varn2; vars->initVal[i] = varn3; }
			else { vars->prior[1][v] = varn1 / E_UNIT; vars->prior[2][v] = varn2 / E_UNIT; vars->initVal[i] = varn3 / E_UNIT; }//all values in initVal with unit kT

			if (strcmp(varc2, "UNIFORM") == 0) { vars->prior[0][v] = -1.0; }
			else if (strcmp(varc2, "GAUSSIAN") == 0) { vars->prior[0][v] = 1.0; }
			
			v += 1;
		}

		else
		{
			fscanf(fp, "%10s%lf%10s\n", varc2, &varn1, varc3);

			if (strcmp(varc3, "kT") == 0) { vars->initVal[i] = varn1; }
			else { vars->initVal[i] = varn1 / E_UNIT; }//all values in initVal with unit kT
		}
	}
}

void readExpData(FILE* fp, struct ExpData* exps)//[ATP]-dependent turnovers
{
	char title[11], buff[75];

	int i = 0;

	fscanf(fp, "%10s%s\n", title, buff);
	exps->numGroup = atoi(buff);
	for (i = 0; i < 3; i++) { exps->data[i] = malloc(exps->numGroup * sizeof(double)); }
	for (i = 0; i < exps->numGroup; i++)
	{
		fscanf(fp, "%10s%10s%lf%lf%lf\n", title, buff,
			&(exps->data[0][i]), &(exps->data[1][i]), &(exps->data[2][i]));
	}
}

void readStates(FILE* fp, struct State* states)
{
	char title[11], buff[75];
	int n = 0, angle = 0, c1 = 0, c2 = 0, c3 = 0, b1 = 0, b2 = 0, b3 = 0, s = 0;
	int t = 0, d = 0;

	fscanf(fp, "%10s%s\n", title, buff);
	states->numAsyState = atoi(buff);

	states->gamma = malloc(states->numAsyState * sizeof(int));
	for (n = 0; n < 3; n++)
	{
		states->bindState[n] = malloc(states->numAsyState * sizeof(int));
		states->confState[n] = malloc(states->numAsyState * sizeof(int));
	}

	for (n = 0; n < states->numAsyState; n++)//states
	{
		fscanf(fp, "%10s%10s%6d%4d%4d%4d%4d%4d%4d%4d\n",
			title, buff, &n, &angle, &c1, &c2, &c3, &b1, &b2, &b3);
		
		states->gamma[n] = angle;
		states->confState[0][n] = c1; states->confState[1][n] = c2; states->confState[2][n] = c3;
		states->bindState[0][n] = b1; states->bindState[1][n] = b2; states->bindState[2][n] = b3;
	}
}

void readTransitions(FILE* fp, struct Transition* transitons)
{
	char title[11], buff[75];
	int n = 0, i = 0, now = 0, next = 0, type = 0, flux = 0;
	fscanf(fp, "%10s%s\n", title, buff);
	transitons->numTransit = atoi(buff);

	for (n = 0; n < 4; n++) { transitons->transType[n] = malloc(transitons->numTransit * sizeof(int)); }

	for (n = 0; n < transitons->numTransit; n++)
	{
		fscanf(fp, "%10s%10s%6d%6d%4d%4d\n", title, buff, &now, &next, &type, &flux);
		
		transitons->transType[0][n] = now; transitons->transType[1][n] = next;
		transitons->transType[2][n] = type; transitons->transType[3][n] = flux;
	}
}

void readSettings(FILE* fp, struct Setting* settings)
{
	int i = 0; char title[11], buff[21], buffActiveConf[21];

	for (i = 0; i < DIM_SETTING; i++)
	{
		fscanf(fp, "%10s%20s", title, buff);

		if (strcmp(buff, "MODE") == 0) { fscanf(fp, "%d\n", &(settings->mode)); }
        
		else if (strcmp(buff, "N_INIT") == 0) { fscanf(fp, "%d\n", &(settings->N_initGuess)); }
		else if (strcmp(buff, "N_TRIAL") == 0) { fscanf(fp, "%d\n", &(settings->N_indepTrial)); }
		
		//else if (strcmp(buff, "N_SEARCH_FAST") == 0) { fscanf(fp, "%d\n", &(settings->N_fastSearch)); }
		else if (strcmp(buff, "N_SEARCH") == 0) { fscanf(fp, "%d\n", &(settings->N_search)); }
        //else if (strcmp(buff, "STD_SEARCH_FAST") == 0) { fscanf(fp, "%lf\n", &(settings->std_fastSearch)); }
		else if (strcmp(buff, "STD_SEARCH") == 0) { fscanf(fp, "%lf\n", &(settings->std_search)); }
		else if (strcmp(buff, "SHRINK_FACTOR") == 0) { fscanf(fp, "%lf\n", &(settings->f_shrink)); }
		

		else if (strcmp(buff, "N_STEP_GOODSET") == 0) { fscanf(fp, "%d\n", &(settings->N_goodSetStep)); }
        else if (strcmp(buff, "N_STEP_MAX") == 0) { fscanf(fp, "%d\n", &(settings->N_maxStep)); }
        else if (strcmp(buff, "SCORE_CRITERION") == 0) { fscanf(fp, "%lf\n", &(settings->score_goodSetCriterion)); }
        else if (strcmp(buff, "ERRORBAR") == 0) { fscanf(fp, "%lf\n", &(settings->errorbar)); }
                
        else if (strcmp(buff, "STD_ZETA") == 0) { fscanf(fp, "%lf\n", &(settings->stdZeta)); }
		else if (strcmp(buff, "STD_ETA") == 0) { fscanf(fp, "%lf\n", &(settings->stdEta)); }
		else if (strcmp(buff, "OCC_ON") == 0) { fscanf(fp, "%d\n", &(settings->occ_on)); }
		else if (strcmp(buff, "STD_OCC") == 0) { fscanf(fp, "%lf\n", &(settings->stdOcc)); }
		
        else if (strcmp(buff, "CONST_HYDR_ENERGY") == 0) { fscanf(fp, "%d\n", &(settings->constHydrEnergy)); }

		//else if (strcmp(buff, "INTERACTION_ENERGY") == 0) { fscanf(fp, "%lf\n", &(settings->gbInteractionEnergy)); }
		
		else if (strcmp(buff, "N_ACTIVE_CONF") == 0) { fscanf(fp, "%d\n", &(settings->N_activeConf)); }
		else if (strcmp(buff, "ACTIVE_CONF") == 0) { fscanf(fp, "%s\n", buffActiveConf); }
	}

	
        
        if (settings->N_activeConf == 1) { sscanf(buffActiveConf, "%d", &(settings->activeConf[0])); settings->activeConf[1] = -1; }
	else if (settings->N_activeConf == 2) { sscanf(buffActiveConf, "%d-%d", &(settings->activeConf[0]), &(settings->activeConf[1])); }
	printf("Number of active conformation(s): %d\n", settings->N_activeConf);
	printf("Active conformation(s): %d,%d\n", settings->activeConf[0], settings->activeConf[1]);
}

void initializeTempStorage(struct TempStorage* tempStore, int numExp, int numAsyState)
{
	int n = 0, i = 0;

	tempStore->energy = malloc(numAsyState * sizeof(double));
	tempStore->stDistr = malloc(numAsyState * sizeof(double));
	tempStore->rateMatrix = malloc(numAsyState * sizeof(double*));
	for (n = 0; n < numAsyState; n++) {
		tempStore->energy[n] = 0.0; tempStore->stDistr[n] = 0.0;
		tempStore->rateMatrix[n] = malloc(numAsyState * sizeof(double));
		for (i = 0; i < numAsyState; i++) { tempStore->rateMatrix[n][i] = 0.0; }
	}

	tempStore->randPool = malloc(VOL_RAND_POOL * sizeof(double));
	generateRandPool(tempStore->randPool);

	tempStore->k_cat = malloc(numExp*sizeof(double));	
	tempStore->k_rot = malloc(numExp * sizeof(double));
	for (n = 0; n < numExp; n++) { tempStore->k_cat[n] = 0.0; tempStore->k_rot[n] = 0.0; }

	tempStore->paras = malloc(sizeof(struct Parameter));
}


void readInitValues(struct InitValue* inits)
{
	char buff[75];
	int i = 0, j = 0;
	
	FILE* fp = fopen("F1-ATPase.init.csv", "r");
	
	fscanf(fp, "%s\n", buff); 
	inits->numInit = atoi(buff);
	inits->initVal = malloc(inits->numInit * sizeof(double*));
	for (i = 0; i < inits->numInit; i++) { inits->initVal[i] = malloc(DIM_VAL * sizeof(double)); }
	
	for (i = 0; i < inits->numInit; i++)
	{
		for (j = 0; j < DIM_VAL - 1; j++)
		{
			fscanf(fp, "%lf,", &(inits->initVal[i][j]));
		}
		fscanf(fp, "%lf\n", &(inits->initVal[i][DIM_VAL-1]));
	}

	fclose(fp);
}


void readBindingCurve(struct ExpData* exps)//titration curves
{
	char buff[75];
	int i = 0;

	FILE* fp = fopen("F1-ATPase.bind.csv", "r");

	fscanf(fp, "%s\n", buff);
	exps->numOccData = atoi(buff);
	for (i = 0; i < 3; i++) { exps->occ[i] = malloc(exps->numOccData * sizeof(double)); }

	for (i = 0; i < exps->numOccData; i++)
	{
		fscanf(fp, "%lf,%lf,%lf\n", &(exps->occ[0][i]), &(exps->occ[1][i]), &(exps->occ[2][i]));
		//printf("%.2f,%.2f,%.2f\n", exps->occ[0][i], exps->occ[1][i], exps->occ[2][i]);
	}

	fclose(fp);
}
