#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 15/04/2025

*************************************************/

# include "prep.h"
extern char* transTypeName[];


double pair_max(double a, double b)
{
  if (a > b) return a;
  else return b;
}


double calculateSpringPotential(double sprConst, double phi, double theta)
{
	return 0.5 * sprConst * ((phi - theta) / 180.0 * PI) * ((phi - theta) / 180.0 * PI);
}

void updateCumulRate(struct Setting* settings, struct State* states, struct Transition* transitions,
	int state_now, double* cumulRate, double* energy,
	int accumRotAngle, double beadAngle)
{
	int r = 0, i = 0, j = 0, state_next = 0;
	double gammaAngle_now = 0.0,  V_now = 0.0,  E_now_noBead = 0.0,  E_now_withBead = 0.0, 
         gammaAngle_next = 0.0, V_next = 0.0, E_next_noBead = 0.0, E_next_withBead = 0.0, 
	       gammaAngle_TS = 0.0,   V_TS = 0.0,   E_TS_noBead = 0.0,   E_TS_withBead = 0.0,
         rate = 0.0, rate_noBead = 0.0;

	gammaAngle_now = (double)accumRotAngle;
	V_now = calculateSpringPotential(settings->sprConst, gammaAngle_now, beadAngle);
  E_now_noBead = energy[state_now];
  E_now_withBead = E_now_noBead + V_now;

	for (r = 0; r < 2; r++)
	{
		i = transitions->indexRot[state_now][r];

		if (i >= 0)
		{
			state_next = transitions->accSubspace[state_now][i];
      
			if (abs(states->gamma[state_next] - states->gamma[state_now]) <= 80)
			{ gammaAngle_next = gammaAngle_now + states->gamma[state_next] - states->gamma[state_now]; }
			else { gammaAngle_next = gammaAngle_now + states->gamma[state_next] % 360 - states->gamma[state_now] % 360; }
      
      V_next = calculateSpringPotential(settings->sprConst, gammaAngle_next, beadAngle);
      E_next_noBead = energy[state_next % states->numAsyState];
      E_next_withBead = E_next_noBead + V_next;
      
			gammaAngle_TS = gammaAngle_now + factor_TS * (gammaAngle_next - gammaAngle_now);
			V_TS = calculateSpringPotential(settings->sprConst, gammaAngle_TS, beadAngle);
			
      E_TS_noBead = pair_max(E_now_noBead, E_next_noBead) + settings->AG_gamma;
      E_TS_withBead = E_TS_noBead + V_TS;
      
      if (E_TS_withBead > E_now_withBead) rate = ATT_FREQ * exp(-(E_TS_withBead - E_now_withBead));
      else rate = ATT_FREQ;
      
      rate_noBead = cumulRate[i] - cumulRate[i - 1];
			for (j = i; j < states->numAccess[state_now]; j++) { cumulRate[j + 1] += (-rate_noBead + rate); }
		}
	}
}


double EulerMaruyama_1step(struct Setting* settings, double* randPool, double theta_t, double phi_0, double dt)
{
	double u = 0.0, thetaChange = 0.0;

	u = generateGaussRand(randPool, 0.0, 1.0);
	thetaChange = -(settings->sprConst / settings->frictionCoeff) * (theta_t - phi_0) * dt + sqrt(2 / settings->frictionCoeff * dt) * u * (180.0 / PI);

	return thetaChange;
}


double stochasticIntegration_bead(struct Setting* settings, double t_aim, double theta_0, double phi_0, double* randPool)
{
	double theta = theta_0, t = 0.0;

	while (t_aim - t > settings->stepLength)
	{ 
		theta += EulerMaruyama_1step(settings, randPool, theta, phi_0, settings->stepLength);
		t += settings->stepLength;
	}

	theta += EulerMaruyama_1step(settings, randPool, theta, phi_0, t_aim - t);
	
	return theta;
}



int kineticMC(struct Setting* settings, struct State* states, struct Transition* transitions,
	double* cumulRate_original, double* energy, double* randPool, int state_old, 
	struct SingleTrajInfo* trajInfo, struct RecInfo* recInfo, FILE* fp_rec)
{
	double u = 0.0, v = 0.0, holdingTime = 0.0;
	int m = 0, state_new = 0;

	double* cumulRate = malloc((states->numAccess[state_old] + 1) * sizeof(double));
	for (m = 0; m < states->numAccess[state_old] + 1; m++) { cumulRate[m] = cumulRate_original[m]; }
	updateCumulRate(settings, states, transitions, state_old, cumulRate, energy, trajInfo->phi, trajInfo->theta);

	//sample holding time
	u = generateUniformRand(randPool, 0.0, 1.0); v = generateUniformRand(randPool, 0.0, 1.0);
  //printf("v=%.4f, cumulRate=%.6e\n", v, cumulRate[states->numAccess[state_old]]);
	holdingTime = log(1 / v) / cumulRate[states->numAccess[state_old]]; //printf("holding time=%.6e\n", holdingTime);

	//sample the new state
	m = findState(states->numAccess[state_old], transitions->accSubspace[state_old], cumulRate, u);
	state_new = transitions->accSubspace[state_old][m];

	//calculate bead angle at required time points
	double time_lastCal = trajInfo->simTime;
	while (trajInfo->simTime + holdingTime >= recInfo->recTime)
	{
		recInfo->theta = stochasticIntegration_bead(settings, recInfo->recTime - time_lastCal, recInfo->theta, trajInfo->phi, randPool);
		writeRecInfo(fp_rec, settings, recInfo, trajInfo, state_old);
		time_lastCal = recInfo->recTime;

		recInfo->recTime += 1.0 / settings->fps_rec; recInfo->frame += 1;
		//printf("%.1e\n", recInfo->recTime);
	}
	trajInfo->theta = stochasticIntegration_bead(settings, trajInfo->simTime + holdingTime- time_lastCal, recInfo->theta, trajInfo->phi, randPool);

	//update trajInfo-------------------------------------------------------------------------------------------------
	trajInfo->simTime += holdingTime; 
	trajInfo->temporalDistr[state_old % states->numAsyState] += holdingTime;

	if (abs(states->gamma[state_new] - states->gamma[state_old]) <= 80)
	{ trajInfo->phi += states->gamma[state_new] - states->gamma[state_old]; }
	else { trajInfo->phi += states->gamma[state_new] % 360 - states->gamma[state_old] % 360; }
	//--------------------------------------------------------------------------------------------------------------------

	free(cumulRate);

	return state_new;
}



void simulate(struct Setting* settings, struct State* states, struct Transition* transitions,
	double** cumulRate, double* energy, struct SingleTrajInfo* trajInfo, int index, double* randPool)
{
	resetTrajInfo(states->numAsyState, trajInfo);

	// Initialize variables to be used in the function==================================
	int i = 0,
		state_next = 0, 
		state_now = settings->initState;//store the states of two consecutive steps
	int angle_prev = 0, angle_now = 0, angle_next = 0;//angle of gamma (not bead)
	long long step = 0;
	int transType[2] = { 5, -1 };//indicate the transition type & site of the step

	//initialize the monitors of the binding state of the three cat. sites
	int monitor[3] = { 0, 0, 0 }; initializeMonitor(states, state_now, monitor);
	
	//Initialize and prepare the documenting file---------------------------------------------------------------
	char fileName[100], fileName_bind[100], fileName_rec[100];
	createFileNames(settings, fileName, "traj", index);
	createFileNames(settings, fileName_bind, "bind", index);
	createFileNames(settings, fileName_rec, "rec", index);
	
	FILE* fp = fopen(fileName, "w"),
		* fp_bind = fopen(fileName_bind, "w"),
		* fp_rec = fopen(fileName_rec, "w");
	writeTitle(fp, fp_bind, fp_rec);
	fprintf(fp, "%lld,%.12e,%d,%d,%.6f,%d,%d,0,NONE\n",
			step, trajInfo->simTime, state_now, trajInfo->phi, trajInfo->theta,
			trajInfo->eventHyd, trajInfo->eventSyn);
	//====================================================================

	struct RecInfo* recInfo = malloc(sizeof(struct RecInfo)); initializeRecInfo(settings, recInfo);
  
  //printf("Time=%.2e\n", settings->totalSimTime);
  
	// start simulation (reach certain time length of the trajectory)
	while (trajInfo->simTime < settings->totalSimTime)
	{
		step += 1;
    
		// carry out sampling of the new state by kinetic Monte Carlo algorithm-----------------
		// trajInfo is modified
		state_next = kineticMC(settings, states, transitions, cumulRate[state_now], energy, randPool, state_now, trajInfo, recInfo, fp_rec);
		angle_next = trajInfo->phi;

		//monitor the change of binding states of the three cat. sites----------------------
		monitorBindChange(states, state_now, state_next, monitor, transType, trajInfo);

		//Record the Monte Carlo step-------------------------------------------------------
		recordStep(trajInfo, states, step, state_now, angle_prev, angle_now, angle_next, transType, fp, fp_bind);//write into .traj and .bind files
		//--------------------------------------------------------------------------------------------------

		//update for the next step--------------------------------------------------------------
		recInfo->step = step; recInfo->theta = trajInfo->theta;
		recInfo->site = transType[1]; sprintf(recInfo->transType, "%7s", transTypeName[transType[0]]);

		state_now = state_next;
		transType[0] = 5; transType[1] = -1;
		angle_prev = angle_now; angle_now = angle_next;
		
	}

	fclose(fp); fclose(fp_bind); fclose(fp_rec);

	for (i = 0; i < states->numAsyState; i++) { trajInfo->temporalDistr[i] /= trajInfo->simTime; }
}
