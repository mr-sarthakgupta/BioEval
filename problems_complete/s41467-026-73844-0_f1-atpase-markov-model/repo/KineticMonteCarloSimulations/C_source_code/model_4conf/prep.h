/************************************************

By Yixin Chen. Last edited: 15/04/2025

*************************************************/

# ifndef CLASS_H
# define CLASS_H

# include <stdio.h>
# include <stdlib.h>
# include <string.h>
# include <math.h>
# define DIM_VAL 24
# define DIM_CONF 4
# define DIM_SETTING 10
# define ATT_FREQ 1.0e9
# define PI 3.141592653589
# define E_UNIT 0.592
# define VOL_RAND_POOL 1000000
# define factor_TS 0.5


struct Parameter {
	double E_beta[DIM_CONF];//open, closed
	double k_beta;
	double k_gamma;
	double k_chem;
	double k_b[DIM_CONF][2];
	double E_b[DIM_CONF][2];
	double E_gb;
};

struct State {
	int numState;
	int numAsyState;
	int* gamma;
	int* bindState[3];
	int* confState[3];
	int* numAccess;
};

struct Transition {
	int** accSubspace;
	int** transType;
	int** indexRot;
};


struct Setting {
	int numSample;
	int initState;
	double totalSimTime;
	double c_ATP;
	double c_ADP;
	double frictionCoeff;
	double sprConst;
	double AG_gamma;
	//int diffusion;
    //int integrateStep;
	double stepLength;
	double lagTime_rec;
	double fps_rec;
};

struct Variable {
	double initVal[DIM_VAL];
};

struct SingleTrajInfo {
	double simTime;
	int phi;//accumulated rotation of gamma-subunit
	double theta;//accumulated rotation of bead
	int eventHyd;
	int eventSyn;
	int eventBindATP[DIM_CONF];
	int eventBindADP[DIM_CONF];
	int eventUnbindATP[DIM_CONF];
	int eventUnbindADP[DIM_CONF];
	double* temporalDistr;
};


struct RecInfo
{
	int frame;
	double recTime;
	long long step;
	//double simTime;
	//int state_now;
	//int phi;//accumulated rotation of gamma-subunit
	double theta;//accumulated rotation of bead
	//int hyd;
	//int syn;
	int site;
	char transType[8];
};

//read_info.c
void readVariables(FILE* fp, struct Variable* vars);
void readStates(FILE* fp, struct State* states);
void readTransitions(FILE* fp, struct State* states, struct Transition* transitions);
void readSettings(FILE* fp, struct Setting* settings);

//generate_rand.c
void generateRandPool(double* randPool);
double generateUniformRand(double* randPool, double lower, double upper);
double generateGaussRand(double* randPool, double mean, double std);

//calculate_rate.c
double calculateRate(struct State* states, struct Transition* transitions,
	struct Variable* vars, double concs[2], double** cumulRate, double* energy);

//miscellaneous.c
void resetTrajInfo(int numAsyState, struct SingleTrajInfo* trajInfo);

int findState(int N, int* accSubspace, double* cumulRate, double u);
void updateCumulRate(struct Setting* settings, struct State* states, struct Transition* transitions,
	int state_now, double* cumulRate, double* energy,
	int accumRotAngle, double beadAngle);

void initializeMonitor(struct State* states, int state, int monitor[3]);
void monitorBindChange(struct State* states, int state_now, int state_next, 
	int monitor[3], int transType[2], struct SingleTrajInfo* trajInfo);

void createFileNames(struct Setting* settings, char fileName[100], char fileType[], int index);
void writeTitle(FILE* fp, FILE* fp_bind, FILE* fp_rec);
void recordStep(struct SingleTrajInfo* trajInfo, struct State* states,
	long long step, int state_now,
	int angle_prev, int angle_now, int angle_next,
	int transType[2], FILE* fp, FILE* fp_bind);

void initializeRecInfo(struct Setting* settings, struct RecInfo* recInfo);
void writeRecInfo(FILE* fp_rec, struct Setting* settings, struct RecInfo* recInfo, struct SingleTrajInfo* trajInfo, int state_now);


//mc_simulate.c
void simulate(struct Setting* settings, struct State* states, struct Transition* transitions,
	double** cumulRate, double* energy, struct SingleTrajInfo* trajInfo, int index, double* randPool);

# endif
