#!/usr/bin/env bash

# The name of the job:
#SBATCH --job-name="spiral"

#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2

# The maximum running time of the job in days-hours:mins:sec
#SBATCH --time=0-1:0:00

# Batch arrays
#SBATCH --array=0-107

# Send yourself an email when the job:
# aborts abnormally (fails)
#SBATCH --mail-type=FAIL
# begins
#SBATCH --mail-type=BEGIN
# ends successfully
#SBATCH --mail-type=END

# Use this email address:
#SBATCH --mail-user=susan.wei@unimelb.edu.au

# check that the script is launched with sbatch
if [ "x$SLURM_JOB_ID" == "x" ]; then
   echo "You need to submit your job to the queuing system with sbatch"
   exit 1
fi

# Run the job from the directory where it was launched (default)

# The job command(s):
python sweep_clean_spiral.py ${SLURM_ARRAY_TASK_ID}