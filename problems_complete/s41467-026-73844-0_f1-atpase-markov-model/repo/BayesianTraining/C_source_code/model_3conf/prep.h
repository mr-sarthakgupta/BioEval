#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 27/08/2024

*************************************************/

# ifndef CLASS_H
# define CLASS_H

# include <stdio.h>
# include <stdlib.h>
# include <string.h>
# include <math.h>
# define DIM_VAL 19//change with model
# define DIM_CONF 3//change with model
# define DIM_SETTING 17
# define ATT_FREQ 1.0e9
# define E_UNIT 0.592
# define PI 3.1415926536
# define VOL_RAND_POOL 1000000
# define GAUSSIAN_CUTOFF 9.0//in terms of STD
# define STD_FACTOR 3.0
# define HYDR_ENERGY 12.3311

struct Parameter {
	double E_beta[DIM_CONF];//open, half-closed, closed_1, closed_2
	double k_beta;
	double k_gamma;
	double k_chem;
	double k_b[DIM_CONF][2];
	double E_b[DIM_CONF][2];
	double E_gb;
};

struct State {
	int numAsyState;
	int* gamma;
	int* bindState[3];
	int* confState[3];
};

struct Transition {
	int numTransit;
	int* transType[4];
};


struct ExpData {
	int numGroup;
	double* data[3];
	int numOccData;
	double* occ[3];
};

struct Setting {
	
    int mode; 

    int N_initGuess;
	int N_indepTrial;

    int N_goodSetStep;
    int N_maxStep;
    double score_goodSetCriterion;
    double errorbar;
	
    //int N_fastSearch;
    int N_search;
    //double std_fastSearch;
    double std_search;
    double f_shrink;

    double stdZeta;
	double stdEta;
    int occ_on;
	double stdOcc;

    int constHydrEnergy;
	int N_activeConf;
	int activeConf[2];

	//double gbInteractionEnergy;
};

struct Variable {
	int numVar;
	int* indexVar;
	double* prior[3];
	double initVal[DIM_VAL];
};

struct TempStorage {
	double* energy;
	double* stDistr;
	double** rateMatrix;
	double* randPool;
	double* k_cat;
	double* k_rot;
	struct Parameter* paras;
};

struct InitValue {
	int numInit;
	double** initVal;
};


//generate_rand.c
double generateGaussRand(double* randPool, double mean, double std);
double generateUniformRand(double* randPool, double lower, double upper);
void generateRandPool(double* randPool);

//read_info.c
void readVariables(FILE* fp, struct Variable* vars);
void readExpData(FILE* fp, struct ExpData* exps);
void readStates(FILE* fp, struct State* states);
void readTransitions(FILE* fp, struct Transition* transitions);
void readSettings(FILE* fp, struct Setting* settings);
void initializeTempStorage(struct TempStorage* tempStore, int numExp, int numAsyState);
void readInitValues(struct InitValue* inits);
void readBindingCurve(struct ExpData* exps);

//calculate_rate.c
void calculateRates(struct State* states, struct Transition* transitions,
	struct ExpData* exps, struct TempStorage* tempStore, int indexExp);
double calculateOcc(struct State* states, struct Transition* transitions,
	struct TempStorage* tempStore, double c_ATP, double c_ADP);

//simple_optimize.c
void sampleRandomSet(struct Setting* settings, struct Variable* vars, double val[DIM_VAL], struct TempStorage* tempStore);
void sampleInitialGuess(struct Setting* settings, struct State* states, struct Transition* transitions,
	struct Variable* vars, struct ExpData* exps, struct TempStorage* tempStore);
void simpleOptimize(struct Setting* settings, struct State* states, struct Transition* transitions,
	struct Variable* vars, struct ExpData* exps, 
	struct TempStorage* tempStore, int label);

# endif
