# Compile model_3conf
gcc -O3 -o run_bayes_3conf model_3conf/main.c -lm model_3conf/simple_optimize.c model_3conf/calculate_rate.c model_3conf/generate_rand.c model_3conf/read_info.c \
    -I./clapack -L./clapack clapack/lapack_LINUX.a clapack/blas_LINUX.a clapack/libf2c.a

# Compile model_4conf
gcc -O3 -o run_bayes_4conf model_4conf/main.c -lm model_4conf/simple_optimize.c model_4conf/calculate_rate.c model_4conf/generate_rand.c model_4conf/read_info.c \
    -I./clapack -L./clapack clapack/lapack_LINUX.a clapack/blas_LINUX.a clapack/libf2c.a
