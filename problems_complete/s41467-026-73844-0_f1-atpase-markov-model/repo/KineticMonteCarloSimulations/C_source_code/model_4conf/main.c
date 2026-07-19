#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 04/02/2025

*************************************************/

# include <stdio.h>
# include <time.h>
# include "prep.h"

void srand(unsigned int seed);
char* transTypeName[] = { "GROT", "#+ATP", "#-ATP", "#+ADP", "#-ADP", "OTHER" };

int main(int argc, char* argv[])
{
	// Read information
	printf(">> START READING INFORMATION...\n");

	FILE* fp = fopen("F1-ATPase.input", "r");

	struct Variable* vars = malloc(sizeof(struct Variable)); readVariables(fp, vars); printf("Variables...\n");
	struct State* states = malloc(sizeof(struct State)); readStates(fp, states); printf("States...\n");
  struct Transition* transitions = malloc(sizeof(struct Transition)); readTransitions(fp, states, transitions); printf("Transitions...\n");
	struct Setting* settings = malloc(sizeof(struct Setting)); readSettings(fp, settings); printf("Settings...\n");

	fclose(fp);
	//==============================================================

	int ex1 = atoi(argv[1]); int ex2 = atoi(argv[2]);
	srand((unsigned int)time(NULL) * ex1 * ex2);//make sure that the random numbers sampled for each run are different
	
	struct SingleTrajInfo* trajInfo; trajInfo = malloc(sizeof(struct SingleTrajInfo));
	trajInfo->temporalDistr = malloc(states->numAsyState * sizeof(double));

	double* randPool = malloc(VOL_RAND_POOL * sizeof(double)); generateRandPool(randPool);
	
	int i = 0, j = 0, s = 0;

  double* energy = malloc(states->numAsyState * sizeof(double));
	double** cumulRate = malloc(states->numState * sizeof(double*));
	for (i = 0; i < states->numState; i++) { cumulRate[i] = malloc((states->numAccess[i] + 1) * sizeof(double)); }
	double concs[2] = { settings->c_ATP, settings->c_ADP };
  
	settings->AG_gamma = calculateRate(states, transitions, vars, concs, cumulRate, energy);

	//printf("kappa=%.4e, xi=%.4e, c_ATP=%.4e, c_ADP=%.4e, k_gamma=%.4e\n", settings->sprConst, settings->frictionCoeff, settings->c_ATP, settings->c_ADP, settings->k_gamma);

	char fileName[100]; sprintf(fileName, "F1-ATPase_time=%.2e,sample=%d,initState=%d.out.csv", settings->totalSimTime, settings->numSample, settings->initState);
	FILE* fp_out = fopen(fileName, "w");
	fprintf(fp_out, "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n", 
			        "SAMPLE", "TIME_TOT", "PHI", "THETA", "#HYD", "#SYN",
					"#OPEN+ATP", "#HC+ATP", "#CLOSED_1+ATP", "#CLOSED_2+ATP",
					"#OPEN+ADP", "#HC+ADP", "#CLOSED_1+ADP", "#CLOSED_2+ADP",
					"#OPEN-ATP", "#HC-ATP", "#CLOSED_1-ATP", "#CLOSED_2-ATP",
					"#OPEN-ADP", "#HC-ADP", "#CLOSED_1-ADP", "#CLOSED_2-ADP");
	fclose(fp_out);

	if (settings->totalSimTime >= settings->lagTime_rec)
	{
		for (s = 0; s < settings->numSample; s++)
		{
			simulate(settings, states, transitions, cumulRate, energy, trajInfo, s, randPool);

			fp_out = fopen(fileName, "a");
			fprintf(fp_out, "%d,%.6e,%d,%.6f,%d,%d,",
				s, trajInfo->simTime, trajInfo->phi, trajInfo->theta,
				trajInfo->eventHyd, trajInfo->eventSyn);
			for (j = 0; j < DIM_CONF; j++) fprintf(fp_out, "%d,", trajInfo->eventBindATP[j]);
			for (j = 0; j < DIM_CONF; j++) fprintf(fp_out, "%d,", trajInfo->eventBindADP[j]);
			for (j = 0; j < DIM_CONF; j++) fprintf(fp_out, "%d,", trajInfo->eventUnbindATP[j]);
			for (j = 0; j < DIM_CONF; j++) fprintf(fp_out, "%d,", trajInfo->eventUnbindADP[j]);
      //for (j = 0; j < states->numAsyState - 1; j++) fprintf(fp_out, "%.6e,", trajInfo->temporalDistr[j]);
			//fprintf(fp_out, "%.6e", trajInfo->temporalDistr[j + 1]);
			fprintf(fp_out, "\n"); fclose(fp_out);
		}
	}

	else printf("Recording starts too late!\n");
	
	return 0;
}
