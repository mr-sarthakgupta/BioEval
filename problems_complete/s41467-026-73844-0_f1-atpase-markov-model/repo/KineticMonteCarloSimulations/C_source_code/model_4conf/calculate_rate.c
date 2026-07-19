/************************************************

By Yixin Chen. Last edited: 15/04/2025

*************************************************/

# include "prep.h"


void assign(struct Parameter* paras, double* values)
/* values = [G_beta_o, G_beta_h, G_beta_c1, G_beta_c2,  //0-3, conformation energy
			 Ga_beta, Ga_gamma, Ga_chem, //4-6, activation energy (energy barrier)
			 Ga_b-s, //7-14, activation energy (energy barrier of binding)
			 dG_b-s, //15-22, binding free energy
			]
*/
{
	int i = 0, j = 0;

	for (i = 0; i < DIM_CONF; i++) { paras->E_beta[i] = values[i]; }

	paras->k_beta = ATT_FREQ * exp(-values[DIM_CONF]);
	paras->k_gamma = ATT_FREQ * exp(-values[DIM_CONF + 1]);
	paras->k_chem = ATT_FREQ * exp(-values[DIM_CONF + 2]);

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


void calculateEnergy(struct Parameter* paras, double concs[2], struct State* states, double* energy)
{
	int n = 0, s = 0;
	for (n = 0; n < states->numAsyState; n++)
	{
		energy[n] = 0.0;//set to zero
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
		if (states->gamma[n] == 120 && states->confState[0][n] == 0) { energy[n] += paras->E_gb; }
	}
}


void calculateCumulTransRate(struct Parameter* paras, double concs[2],
	struct State* states, struct Transition* transitions, double* energy, double** cumulRate)
{
	int n = 0, m = 0, conf = 0, nuc = 0, next = 0; double dE = 0.0;

	//cumulRate[n] is of dimension (states->numAcess[n]+1). The first element will be kept zero.
	//set the first element of cumulRate[n] to zero before iterative computation.
	for (n = 0; n < states->numState; n++) { cumulRate[n][0] = 0.0; }

	//FILE* fp = fopen("rate.txt", "w");

	for (n = 0; n < states->numAsyState; n++)
	{
		for (m = 0; m < states->numAccess[n]; m++)
		{
			if (transitions->transType[n][m] >=1 && transitions->transType[n][m] <= 10)//ATP/ADP binding
			{
				conf = (transitions->transType[n][m] - 1) / 2; nuc = (transitions->transType[n][m] - 1) % 2;
				cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_b[conf][nuc] * concs[nuc];
			}
			
			else if (transitions->transType[n][m] >=11 && transitions->transType[n][m] <= 20)//ATP/ADP unbinding
			{
				conf = (transitions->transType[n][m] - 11) / 2; nuc = (transitions->transType[n][m] - 11) % 2;
				cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_b[conf][nuc] * exp(paras->E_b[conf][nuc]);
			}

			else if (transitions->transType[n][m] >= 21 && transitions->transType[n][m] <= 30)// hydrolysis or synthesis
			{ cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_chem; }

			else if (transitions->transType[n][m] == 31) //rotation
			{
				next = transitions->accSubspace[n][m] % states->numAsyState;
				
				dE = energy[next] - energy[n];
				if (dE > 0) { cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_gamma * exp(-dE); }
				else { cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_gamma; }
			}

			else if (transitions->transType[n][m] == 32) //conformational change
			{
				dE = energy[transitions->accSubspace[n][m]] - energy[n];
				if (dE > 0) { cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_beta * exp(-dE); }
				else { cumulRate[n][m + 1] = cumulRate[n][m] + paras->k_beta; }
			}

			cumulRate[n + states->numAsyState][m + 1] = cumulRate[n][m + 1];
			cumulRate[n + 2 * states->numAsyState][m + 1] = cumulRate[n][m + 1];
			//fprintf(fp, "%d,%d,%d,%f\n", n, transitions->accSubspace[n][m], transitions->transType[n][m], cumulRate[n][m + 1]);
		}
	}
	//fclose(fp);
}

double calculateRate(struct State* states, struct Transition* transitions, 
	struct Variable* vars, double concs[2], double** cumulRate, double* energy)
{
	struct Parameter* paras = malloc(sizeof(struct Parameter));
	
	assign(paras, vars->initVal);
	
	calculateEnergy(paras, concs, states, energy);

	calculateCumulTransRate(paras, concs, states, transitions, energy, cumulRate);//renew cumulRate

	return vars->initVal[DIM_CONF + 1];
}
