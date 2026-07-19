#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 27/08/2024

*************************************************/

# include "prep.h"
# include "f2c.h"
# include "clapack.h"


void calculateEnergy(struct Parameter* paras, double concs[2], struct State* states, double* energy)
{
	int n = 0, s = 0;
	for (n = 0; n < states->numAsyState; n++)
	{
		for (s = 0; s < 3; s++)
		{
			energy[n] += paras->E_beta[states->confState[s][n]];

			if (states->bindState[s][n] < 2)//ATP/ADP-bound
			{
				energy[n] += paras->E_b[states->confState[s][n]][states->bindState[s][n]]
								   - log(concs[states->bindState[s][n]]);
			}
		}
		
		//If beta_1 adopts open conformation at 120-degree, add interaction energy (simulating extra stabilization)
		if (states->gamma[n] == 120 && states->confState[0][n] == 0) { energy[n] += paras->E_gb; }//settings->gbInteractionEnergy; }
	}

	/*FILE* fp = fopen("energy.txt", "w");
	fprintf(fp, "%f,%f\n", paras->E_beta[0], paras->E_beta[1]);
	for (n = 0; n < states->numAsyState; n++)
	{
		fprintf(fp, "%d,%f\n", n, energy[n]);
	}
	fclose(fp);*/
}


void calculateRateMatrix(struct Parameter* paras, double concs[2],
	struct State* states, struct Transition* transitions, double* energy, double** rateMatrix)
{
	int n = 0, m = 0, conf = 0, nuc = 0, now = 0, next = 0; double dE = 0.0;

	/*
	int **count = malloc(states->numAsyState * sizeof(int*));
	for (n = 0; n < states->numAsyState; n++) {
		count[n] = malloc(states->numAsyState * sizeof(int));
		for (m = 0; m < states->numAsyState; m++) { count[n][m] = 0; }
	}
	*/

	//calculate transition rate from state #n to state #accSubspace[n][m]
	for (n = 0; n < transitions->numTransit; n++)
	{
		now = transitions->transType[0][n]; next = transitions->transType[1][n];

		if (transitions->transType[2][n] >= 1 && transitions->transType[2][n] <= 10)//open/closed_1/closed_2 + ATP/ADP
		{
			conf = (transitions->transType[2][n] - 1) / 2; nuc = (transitions->transType[2][n] - 1) % 2;
			rateMatrix[now][next] = paras->k_b[conf][nuc] * concs[nuc];
		}

		else if (transitions->transType[2][n] >= 11 && transitions->transType[2][n] <= 20)//open/closed_1/closed_2 - ATP/ADP
		{
			conf = (transitions->transType[2][n] - 11) / 2; nuc = (transitions->transType[2][n] - 11) % 2;
			rateMatrix[now][next] = paras->k_b[conf][nuc] * exp(paras->E_b[conf][nuc]);
		}

		else if (transitions->transType[2][n] >= 21 && transitions->transType[2][n] <= 30) // hydrolysis or synthesis
		{ rateMatrix[now][next] = paras->k_chem; }


		else if (transitions->transType[2][n] == 31) //rotation
		{
			next = next % states->numAsyState;
			//rateMatrix[now][next] += paras->k_gamma;
			
			dE = energy[next] - energy[now]; //printf("%d,%d,%.2f,%.2e\n", now, next, dE, paras->k_gamma);
			if (dE > 0) { rateMatrix[now][next] += paras->k_gamma * exp(-dE); }
			else { rateMatrix[now][next] += paras->k_gamma; }

			//count[now][next] += 1;

			//if (now==242) {printf("%d,%d,%.2f,%.6e,%.6e\n", now, next, dE, paras->k_gamma, rateMatrix[now][next]);}
		}

		else if (transitions->transType[2][n] == 32) //conformational change
		{
			dE = energy[next] - energy[now];
			if (dE > 0) { rateMatrix[now][next] = paras->k_beta * exp(-dE); }
			else { rateMatrix[now][next] = paras->k_beta; }
		}

	}

	//calculate diagonal elements of the transition rate matrix
	for (n = 0; n < states->numAsyState; n++)
	{
		for (m = 0; m < states->numAsyState; m++)
		{
			if (m != n) { rateMatrix[n][n] -= rateMatrix[n][m]; }
		}
	}

	/*
	for (n = 0; n < transitions->numTransit; n++)
	{
		now = transitions->transType[0][n]; next = transitions->transType[1][n];
		if (transitions->transType[2][n] == 31) //rotation
		{
			nuc = next % states->numAsyState;
			if (count[now][nuc] != 1 && states->confState[0][now]+states->confState[1][now]+states->confState[2][now] != 0) printf("%d,%d,%d\n", now, next, count[now][nuc]);
		}
	}
	*/
}


void calculateStDistr(struct State* states, double** rateMatrix, double* stDistr)
{
	integer n = states->numAsyState;
	integer nrhs= 1;
	integer info = 0;
	integer* ipiv = malloc(states->numAsyState * sizeof(integer));
	double* lhs = malloc(states->numAsyState * states->numAsyState * sizeof(double));

	int i = 0, j = 0;
	for (i = 0; i < states->numAsyState; i++)
	{
		for (j = 0; j < states->numAsyState; j++)
		{
			lhs[i * states->numAsyState + j] = rateMatrix[i][j];
		}
	}
	for (i = 0; i < states->numAsyState; i++) { lhs[i * states->numAsyState + states->numAsyState - 1] = 1.0; }

	dgesv_(&n, &nrhs, lhs, &n, ipiv, stDistr, &n, &info);

	free(ipiv); free(lhs);

	/*FILE* fp = fopen("stDistr.txt", "w");
	for (n = 0; n < states->numAsyState; n++)
	{
		fprintf(fp, "%d,%.4e,\n", n, stDistr[n]);
	}
	fclose(fp);*/
}


void calculateFlux(struct State* states, struct Transition* transitions, double** rateMatrix, double* stDistr, double* k_cat, double* k_rot, int indexExp)
{
	int n = 0, k = 0, now = 0, next = 0;
	double chemFlux[18] = { 0.0 };
	double rotFlux[2] = { 0.0 };

	for (n = 0; n < transitions->numTransit; n++)
	{
		now = transitions->transType[0][n]; next = transitions->transType[1][n] % states->numAsyState;
		
		k = transitions->transType[3][n];
		if (k > 0 && k <= 18) { chemFlux[k-1] += rateMatrix[now][next] * stDistr[now]; }
		else if (k < 0 && k >= -18) { chemFlux[-k - 1] += -rateMatrix[now][next] * stDistr[now]; }

		else if (k == 19) { rotFlux[0] += rateMatrix[now][next] * stDistr[now]; }
		else if (k == -19) { rotFlux[0] += -rateMatrix[now][next] * stDistr[now]; }
		else if (k == 20) { rotFlux[1] += rateMatrix[now][next] * stDistr[now]; }
		else if (k == -20) { rotFlux[1] += -rateMatrix[now][next] * stDistr[now]; }
	}
	
	k_cat[indexExp] = 0.0;
	for (n = 0; n < 6; n++)
	{ k_cat[indexExp] += (chemFlux[3 * n] + chemFlux[3 * n + 1] - chemFlux[3 * n + 2]) / 3; }

	k_rot[indexExp] = (rotFlux[0] + rotFlux[1]) / 2 / 3;// k_rot is the probability flux of rotation
}


void calculateRates(struct State* states, struct Transition* transitions, 
	struct ExpData* exps, struct TempStorage* tempStore, int indexExp)
{
	int n = 0, m = 0;
	// tempStore elements set to zero
	for (n = 0; n < states->numAsyState; n++) {
		tempStore->energy[n] = 0.0; tempStore->stDistr[n] = 0.0;
		for (m = 0; m < states->numAsyState; m++) { tempStore->rateMatrix[n][m] = 0.0; }
	}
	tempStore->stDistr[states->numAsyState - 1] = 1.0;

	double concs[2] = {exps->data[0][indexExp], exps->data[1][indexExp]};

	calculateEnergy(tempStore->paras, concs, states, tempStore->energy);
	calculateRateMatrix(tempStore->paras, concs, states, transitions, tempStore->energy, tempStore->rateMatrix);//renew rate
	calculateStDistr(states, tempStore->rateMatrix, tempStore->stDistr);
	
	calculateFlux(states, transitions, tempStore->rateMatrix, tempStore->stDistr, tempStore->k_cat, tempStore->k_rot, indexExp);
	//tempStore->k_rot[indexExp] *= tempStore->paras->k_gamma/3.0;
	//printf("k_rot=%.2f, k_cat=%.2f\n", tempStore->k_rot[indexExp], tempStore->k_cat[indexExp]);
}


double calculateOcc(struct State* states, struct Transition* transitions,
	struct TempStorage* tempStore, double c_ATP, double c_ADP)
{
	int n = 0, m = 0;
	// tempStore elements set to zero
	for (n = 0; n < states->numAsyState; n++)
	{
		tempStore->energy[n] = 0.0; tempStore->stDistr[n] = 0.0;
		for (m = 0; m < states->numAsyState; m++) { tempStore->rateMatrix[n][m] = 0.0; }
	}
	tempStore->stDistr[states->numAsyState - 1] = 1.0;

	double concs[2] = { c_ATP, c_ADP };

	calculateEnergy(tempStore->paras, concs, states, tempStore->energy);
	calculateRateMatrix(tempStore->paras, concs, states, transitions, tempStore->energy, tempStore->rateMatrix);//renew rate
	calculateStDistr(states, tempStore->rateMatrix, tempStore->stDistr);

	double occ = 0.0;
	for (n = 0; n < states->numAsyState; n++)
	{
		for (m = 0; m < 3; m++)
		{
			if (states->bindState[m][n] < 2)
			{ occ += tempStore->stDistr[n]; }
		}
	}

	return occ;
}
