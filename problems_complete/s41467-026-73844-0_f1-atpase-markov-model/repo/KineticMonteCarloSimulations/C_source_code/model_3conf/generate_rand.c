#pragma warning(disable : 4996)

/************************************************

By Yixin Chen. Last edited: 04/02/2021

*************************************************/

# include "prep.h"

double generateNormUniformRand()
{
	int i = 0; double x = 0.0;

	while (i == 0) { i = rand(); }
	x = (double)i/RAND_MAX;

	return x;//x in (0, 1]
}

void generateRandPool(double* randPool)
{
	int i = 0; for (i = 0; i < VOL_RAND_POOL; i++)
	{ randPool[i] = generateNormUniformRand(); }
}

void updateRandPool(double* randPool, int j)
{
	randPool[j] = generateNormUniformRand();
}

double generateGaussRand(double* randPool, double mean, double std)
{
	int i = 0; double u = 0.0, v = 0.0;

	i = rand()%VOL_RAND_POOL;
	u = randPool[i]; updateRandPool(randPool, i);

	i = rand()%VOL_RAND_POOL;
	v = randPool[i]; updateRandPool(randPool, i);

	double x = cos(2 * PI * u) * sqrt(-2 * log(v));
	double y = x * std + mean;
	//printf("gauss, x = %.6f, y = %.6f\n", x, y);

	return y;
}

double generateUniformRand(double* randPool, double lower, double upper)
{
	int i = rand() % VOL_RAND_POOL;
	double u = randPool[i]; updateRandPool(randPool, i);

	double x = lower + u * (upper - lower);

	return x;
}