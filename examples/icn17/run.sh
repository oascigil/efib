#!/home/uceeoas/.local/bin/python

# Enable command echo
set -v

# Directory where this script is located
CURR_DIR=`pwd`

# Icarus main folder
ICARUS_DIR=${CURR_DIR}/../..

# Dir where plots will be saved 
PLOTS_DIR=${CURR_DIR}/plots

# Config file
CONFIG_FILE=${CURR_DIR}/config.py

# FIle where results will be saved
#RESULTS_FILE=${CURR_DIR}/results_efib_size_last.pickle
#RESULTS_FILE=${CURR_DIR}/results_efib_budget_last.pickle
#RESULTS_FILE=${CURR_DIR}/results_efib_netcache_last.pickle
#RESULTS_FILE=${CURR_DIR}/results_efib_zipf_last.pickle
#RESULTS_FILE=${CURR_DIR}/results_strategies_last.pickle
RESULTS_FILE=${CURR_DIR}/results_efib_additive_last.pickle
#RESULTS_FILE=${CURR_DIR}/results_nrr_netcache.pickle

# Add Icarus code to PYTHONPATH
export PYTHONPATH=${ICARUS_DIR}:$PYTHONPATH

# Run experiments
echo "Run experiments"
/home/uceeoas/.local/bin/python ${ICARUS_DIR}/icarus.py --results ${RESULTS_FILE} ${CONFIG_FILE}

# Plot results
echo "Plot results"
/home/uceeoas/.local/bin/python ${CURR_DIR}/plotresults.py --results ${RESULTS_FILE} --output ${PLOTS_DIR}
