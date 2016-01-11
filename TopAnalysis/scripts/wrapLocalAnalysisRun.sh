#!/bin/bash
date | tee /dev/stderr
#determine CMSSW config
SCRIPT=$(readlink -f $0)
SCRIPTPATH=`dirname $SCRIPT`
ARCH=${SCRIPTPATH##/*/}
WORKDIR=${SCRIPTPATH}/../

#configure environment
cd $WORKDIR
export SCRAM_ARCH=$ARCH
eval `scram r -sh`
ulimit -c 0
#run with the arguments passed
$*
