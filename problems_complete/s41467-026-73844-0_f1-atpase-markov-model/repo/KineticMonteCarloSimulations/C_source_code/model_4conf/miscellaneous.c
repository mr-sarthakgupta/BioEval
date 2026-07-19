#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 28/09/2022

*************************************************/

# include "prep.h"
extern char* transTypeName[];


void resetTrajInfo(int numAsyState, struct SingleTrajInfo* trajInfo)
{
	trajInfo->simTime = 0.0; trajInfo->phi = 0; trajInfo->theta = 0.;
	trajInfo->eventHyd = 0; trajInfo->eventSyn = 0;
	int i = 0; for (i = 0; i < DIM_CONF; i++)
	{
		trajInfo->eventBindATP[i] = 0; trajInfo->eventBindADP[i] = 0;
		trajInfo->eventUnbindATP[i] = 0; trajInfo->eventUnbindADP[i] = 0;
	}
	for (i = 0; i < numAsyState; i++) trajInfo->temporalDistr[i] = 0.0;
}


int findState(int N, int* accSubspace, double* cumulRate, double u)
{
	int a = 0, b = N, c = 0;
	double uR = u * cumulRate[N];
	if (u == 1.0) return (N - 1);
	else
	{
		while (a <= b)
		{
			c = a + (b - a) / 2;
			if (uR > cumulRate[c]) { a = c + 1; }
			else if (uR < cumulRate[c]) { b = c - 1; }
			else { return (c - 1); }
		}
		return (a - 1);
	}
}


void initializeMonitor(struct State* states, int state, int monitor[3])
{
	int i = 0; for (i = 0; i < 3; i++)
	{
		if (states->bindState[i][state] == 0) { monitor[i] = 1; }
		else if (states->bindState[i][state] == 1) { monitor[i] = -1; }
	}
}


void monitorBindChange(struct State* states, int state_now, int state_next, 
	int monitor[3], int transType[2], struct SingleTrajInfo* trajInfo)
{
	int s = 0;

	for (s = 0; s < 3; s++)
	{
		transType[1] = s;

		if (states->bindState[s][state_now] == 2)//empty
		{
			if (states->bindState[s][state_next] == 0)//empty->ATP-bound
			{
				monitor[s] = 1; transType[0] = 1;
				trajInfo->eventBindATP[states->confState[s][state_now]] += 1;
				break;
			}

			else if (states->bindState[s][state_next] == 1)//empty->ADP-bound
			{
				monitor[s] = -1; transType[0] = 3;
				trajInfo->eventBindADP[states->confState[s][state_now]] += 1;
				break;
			}
		}

		else if (states->bindState[s][state_now] == 1)//ADP-bound
		{
			if (states->bindState[s][state_next] == 2)//ADP-bound->empty
			{
				if (monitor[s] == 1) trajInfo->eventHyd += 1;
				monitor[s] = 0; transType[0] = 4;
				trajInfo->eventUnbindADP[states->confState[s][state_now]] += 1;
				break;
			}
			else if (states->bindState[s][state_next] == 0) break;
		}

		else//ATP-bound
		{
			if (states->bindState[s][state_next] == 2)//ATP-bound->empty
			{
				if (monitor[s] == -1) trajInfo->eventSyn += 1;
				monitor[s] = 0; transType[0] = 2;
				trajInfo->eventUnbindATP[states->confState[s][state_now]] += 1;
				break;
			}
			else if (states->bindState[s][state_next] == 1) break;
		}
	}
}


void createFileNames(struct Setting* settings, char fileName[100], char fileType[], int index)
{
	sprintf(fileName, "F1-ATPase_time=%.2e,initState=%d,index=%d.%s.csv",
			1.0 * settings->totalSimTime, settings->initState, index, fileType);
}


void writeTitle(FILE* fp, FILE* fp_bind, FILE* fp_rec)
{
	fprintf(fp, "STEP,TIME,STATE_NOW,PHI,THETA,#HYD,#SYN,SITE,TRANSITION\n");
	fprintf(fp_bind, "STEP,TIME,STATE_NOW,PHI,THETA,#HYD,#SYN,SITE,BINDING\n");
	fprintf(fp_rec, "TIME_CAMERA,PHI,THETA,STATE_NOW,#NET_HYD\n");
}


void recordStep(struct SingleTrajInfo* trajInfo, struct State* states,
	long long step, int state_now,
	int angle_prev, int angle_now, int angle_next,
	int transType[2], FILE* fp, FILE* fp_bind)
{

	if (transType[0] >= 1 && transType[0] <= 4)//change of binding state (omit ATP<=>ADP in closed beta)
	{
                /*
		fprintf(fp, "%lld,%.12e,%d,%d,%.6f,%d,%d,%d,%s\n",
			step, trajInfo->simTime, state_now,
			trajInfo->phi, trajInfo->theta,
			trajInfo->eventHyd, trajInfo->eventSyn,
			transType[1] + 1, transTypeName[transType[0]]);
                */
		fprintf(fp_bind, "%lld,%.12e,%d,%d,%.6f,%d,%d,%d,%s\n",
			step, trajInfo->simTime, state_now,
			trajInfo->phi, trajInfo->theta,
			trajInfo->eventHyd, trajInfo->eventSyn,
			transType[1] + 1, transTypeName[transType[0]]);
	}
        
        /*
	else// no change of binding state
	{
		if (angle_next != angle_now && (angle_now - angle_prev) * (angle_next - angle_now) >= 0)//gamma rotates
		{
			fprintf(fp, "%lld,%.12e,%d,%d,%.6f,%d,%d,%d,%s\n",
				step, trajInfo->simTime, state_now,
				trajInfo->phi, trajInfo->theta,
				trajInfo->eventHyd, trajInfo->eventSyn,
				transType[1] + 1, transTypeName[0]);
		}
	}
        */
}


void initializeRecInfo(struct Setting* settings, struct RecInfo* recInfo)
{
	recInfo->frame = 1;
	recInfo->recTime = settings->lagTime_rec;
	recInfo->step = 0;
	recInfo->theta = 0.0;
	recInfo->site = 0;
	sprintf(recInfo->transType, "%7s", "a");
}


void writeRecInfo(FILE* fp_rec, struct Setting* settings, struct RecInfo* recInfo, struct SingleTrajInfo* trajInfo, int state_now)
{
	/*fprintf(fp_rec, "%d,%.6e,%lld,%.12e,%d,%d,%.6f,%d,%d,%d,%s\n",
		recInfo->frame, recInfo->recTime - settings->lagTime_rec, recInfo->step, trajInfo->simTime,
		state_now,
		trajInfo->phi, recInfo->theta,
		trajInfo->eventHyd, trajInfo->eventSyn,
		recInfo->site, recInfo->transType);*/
	fprintf(fp_rec, "%.6f,%d,%.6f,%d,%d\n",
		recInfo->recTime - settings->lagTime_rec,
		trajInfo->phi, recInfo->theta,
        state_now,
		trajInfo->eventHyd - trajInfo->eventSyn);
}
