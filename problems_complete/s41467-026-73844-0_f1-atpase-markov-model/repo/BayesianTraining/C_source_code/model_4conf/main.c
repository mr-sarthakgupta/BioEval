#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 03/08/2022

*************************************************/

# include <stdio.h>
# include <time.h>
# include "prep.h"

void srand(unsigned int seed);

int main(int argc, char** argv)
{
	// Read input file============================================
	printf(">> READING INFORMATION...\n");
	FILE* fp = fopen("F1-ATPase.input", "r");
	struct Variable* vars = malloc(sizeof(struct Variable)); readVariables(fp, vars); printf("N_VARIABLE=%d\n", vars->numVar);
    //for (int i=0;i<DIM_VAL;i++) { printf("%d,%f\n", i, vars->initVal[i]);}
  
	struct ExpData* exps = malloc(sizeof(struct ExpData)); readExpData(fp, exps);
  
	struct State* states = malloc(sizeof(struct State)); readStates(fp, states); printf("N_STATE=%d\n", states->numAsyState);
	struct Transition* transitions = malloc(sizeof(struct Transition)); readTransitions(fp, transitions);
	
	struct Setting* settings = malloc(sizeof(struct Setting)); readSettings(fp, settings);
	
	fclose(fp);

	if (settings->constHydrEnergy == 1)
	{
		for (int i = 0; i < settings->N_activeConf; i++)
		{
			vars->initVal[(3*DIM_CONF + 3) + 2 * settings->activeConf[i]] = vars->initVal[(3*DIM_CONF + 3) + 2 * settings->activeConf[i] + 1] - HYDR_ENERGY;
		}
	}
	//========================================================
	
	
	readBindingCurve(exps); printf("N_CAT=%d, N_TIT=%d\n", exps->numGroup, exps->numOccData);

	// Prepare for optimization======================================
	int ex1 = atoi(argv[1]); int ex2 = atoi(argv[2]);
	srand((unsigned int)time(NULL) * ex1 * ex2);//make sure that the random numbers sampled for each run are different
        
	struct TempStorage* tempStore = malloc(sizeof(struct TempStorage));
	initializeTempStorage(tempStore, exps->numGroup, states->numAsyState);
	//=========================================================
        

	if (settings->mode == 1)//sample (settings->N_initGuess) of random guesses of the parameter sets (do not run optimization)
	{
		printf(">> RANDOM SAMPLING...\n");

		sampleInitialGuess(settings, states, transitions, vars, exps, tempStore);
	}
	

	else if (settings->mode == 2)//run (settings->N_indepTrial) of optimation, started from the given initial values in .input file
	{
		printf(">> RUNNING OPTIMIZATION (GIVEN INITIAL VALUE)...\n");

		int i = 0; for (i = 0; i < settings->N_indepTrial; i++)
		{ simpleOptimize(settings, states, transitions, vars, exps, tempStore, i); }
	}

	
	else if (settings->mode == 3)
	{
		printf(">> RUNNING OPTIMATION (INITIAL VALUE PROVIDED BY F1-ATPase.INIT.CSV)...\n");

		struct InitValue* inits = malloc(sizeof(struct InitValue));
		readInitValues(inits);
		int i = atoi(argv[3]);
                
		int j = 0;
		for (j = 0; j < DIM_VAL; j++) { vars->initVal[j] = inits->initVal[i][j]; }
		if (settings->constHydrEnergy == 1)
		{
			for (int n = 0; n < settings->N_activeConf; n++)
			{
				vars->initVal[(3 * DIM_CONF + 3) + 2 * settings->activeConf[n]] = vars->initVal[(3 * DIM_CONF + 3) + 2 * settings->activeConf[n] + 1] - HYDR_ENERGY;
			}
		}

		int k = 0; for (k = 0; k < settings->N_indepTrial; k++) simpleOptimize(settings, states, transitions, vars, exps, tempStore, k);
	}


	else {printf("MODE %d CHOSEN. WRONG CHOICE OF MODE!", settings->mode);}
}
