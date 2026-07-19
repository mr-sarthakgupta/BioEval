#!/bin/bash

export MPD_TMPDIR=$TMPDIR
source /home/ychen3/.bashrc

cd prepareInputFile
python runme.py
cd ..

for dir in $(ls -d param_file=*/)
do
  
  fileCount=`ls -l $dir|grep "^-"|wc -l`

  if [ "$fileCount" -eq "1" ];then
  
    cp ./template/* $dir

    cd $dir
    ./run_KMC_4conf
    cd ..

  fi

done
