for((i=$1;i<$1+$2;i++))
do
  cp -r template "chain_"$i
  cd "chain_"$i
  ./run_bayes_3conf $i 1 $i
  cd ..
done
