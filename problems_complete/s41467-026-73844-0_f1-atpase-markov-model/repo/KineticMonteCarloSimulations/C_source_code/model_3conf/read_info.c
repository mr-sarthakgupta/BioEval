
#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 28/09/2022

*************************************************/

# include "prep.h"

void readVariables(FILE* fp, struct Variable* vars)
{
	char title[11], buff[11], buff1[11];
	double var = 0.0;
	int i = 0;
	
	for (i = 0; i < DIM_VAL; i++)
    {
        fscanf(fp, "%10s%10s%lf%10s\n", title, buff, &var, buff1);

		vars->initVal[i] = var;

        //printf("%10s = %10.2f kT\n", buff, var);
	}
}


void readStates(FILE* fp, struct State* states)
{
	char title[11], dum[11];
	int n = 0, angle = 0, c1 = 0, c2 = 0, c3 = 0, b1 = 0, b2 = 0, b3 = 0, p = 0;

	fscanf(fp, "%10s%10s\n", title, dum);
	states->numAsyState = atoi(dum);
	states->numState = states->numAsyState * 3;
        //printf("%d Markov states\n", states->numState);
        //printf("%d asymmetric Markov states\n", states->numAsyState);

	states->gamma = malloc(states->numState * sizeof(int));
	states->numAccess = malloc(states->numState * sizeof(int));
	for (n = 0; n < 3; n++)
	{
		states->bindState[n] = malloc(states->numState * sizeof(int));
		states->confState[n] = malloc(states->numState * sizeof(int));
	}

	for (n = 0; n < states->numState; n++)//states
	{
		fscanf(fp, "%10s%10s%6d%4d%4d%4d%4d%4d%4d%4d%6d\n",
			title, dum, &n, &angle, &c1, &c2, &c3, &b1, &b2, &b3, &p);
		states->gamma[n] = angle;
		states->confState[0][n] = c1; states->confState[1][n] = c2; states->confState[2][n] = c3;
		states->bindState[0][n] = b1; states->bindState[1][n] = b2; states->bindState[2][n] = b3;
		states->numAccess[n] = p;
	}
}

void readTransitions(FILE* fp, struct State* states, struct Transition* transits)
{
	char title[11], dum[11];
	int n = 0, i = 0, r = 0, now = 0, next = 0, type = 0;

	transits->accSubspace = malloc(states->numState * sizeof(int*));
	transits->transType = malloc(states->numState * sizeof(int*));
	transits->indexRot = malloc(states->numState * sizeof(int*));

	for (n = 0; n < states->numState; n++)
	{
		r = 0;

		fscanf(fp, "%10s%10s%6d", title, dum, &now);

        transits->accSubspace[now] = malloc(states->numAccess[now] * sizeof(int));
		transits->transType[now] = malloc(states->numAccess[now] * sizeof(int));

		transits->indexRot[now] = malloc(2 * sizeof(int));
		transits->indexRot[now][0] = -1; transits->indexRot[now][1] = -1;

		for (i = 0; i < states->numAccess[now]; i++)
		{
			fscanf(fp, "%6d%4d", &next, &type);
			transits->accSubspace[now][i] = next;
			transits->transType[now][i] = type;

			if (type == 31)//rotation
			{
				transits->indexRot[now][r] = i;
				r += 1;
			}
		}
		fscanf(fp, "\n");
	}
}

void readSettings(FILE* fp, struct Setting* settings)
{
	int i = 0; char title[11], dum[13];

	for (i = 0; i < DIM_SETTING; i++)
	{
		fscanf(fp, "%10s%12s", title, dum);//printf(title); printf(dum);
		if (strcmp(dum, "N_SAMPLE") == 0) { fscanf(fp, "%d\n", &(settings->numSample)); }
		//else if (strcmp(dum, "N_STEP") == 0) { fscanf(fp, "%lld\n", &(settings->numStep)); }
		else if (strcmp(dum, "SIM_TIME") == 0) { fscanf(fp, "%lf\n", &(settings->totalSimTime)); }
		else if (strcmp(dum, "INIT_STATE") == 0) { fscanf(fp, "%d\n", &(settings->initState)); }
		else if (strcmp(dum, "C_ATP") == 0) { fscanf(fp, "%lf\n", &(settings->c_ATP)); }
		else if (strcmp(dum, "C_ADP") == 0) { fscanf(fp, "%lf\n", &(settings->c_ADP)); }
		else if (strcmp(dum, "KAPPA") == 0) { fscanf(fp, "%lf\n", &(settings->sprConst)); }
		else if (strcmp(dum, "XI") == 0) { fscanf(fp, "%lf\n", &(settings->frictionCoeff)); }
		//else if (strcmp(dum, "DIFFUSION") == 0) { fscanf(fp, "%d\n", &(settings->diffusion)); }
		//else if (strcmp(dum, "INTEGRATE") == 0) { fscanf(fp, "%d\n", &(settings->integrateStep)); }
		else if (strcmp(dum, "STEP_LENGTH") == 0) { fscanf(fp, "%lf\n", &(settings->stepLength)); }
		else if (strcmp(dum, "LAG_TIME") == 0) { fscanf(fp, "%lf\n", &(settings->lagTime_rec)); }
		else if (strcmp(dum, "FPS") == 0) { fscanf(fp, "%lf\n", &(settings->fps_rec)); }
	}
        //printf("%12s = %16d\n", "N_SAMPLE", settings->numSample);  
        //printf("%12s = %16d\n", "N_STEP", settings->numStep);
        //printf("%12s = %16.2f\n", "SIM_TIME", settings->simTime);
}
