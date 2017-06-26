appKernelRunEnvironmentTemplate="""
#Load application environment
module load nwchem/6.1.1
module list

ulimit -s unlimited

export I_MPI_PMI_LIBRARY=/usr/lib64/libpmi.so

#set executable location
EXE=$NWCHEM_HOME/bin/nwchem-mva2-qlc

#set how to run app kernel
RUN_APPKERNEL="srun --mpi=pmi2 $EXE $INPUT >> $AKRR_APP_STDOUT_FILE 2>&1
"""