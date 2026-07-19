# Compile model_3conf
gcc -O3 -o run_HMC_3conf model_3conf/main.c model_3conf/mc_simulate.c model_3conf/miscellaneous.c model_3conf/calculate_rate.c model_3conf/generate_rand.c model_3conf/read_info.c -lm

# Compile model_4conf
gcc -O3 -o run_HMC_4conf model_4conf/main.c model_4conf/mc_simulate.c model_4conf/miscellaneous.c model_4conf/calculate_rate.c model_4conf/generate_rand.c model_4conf/read_info.c -lm