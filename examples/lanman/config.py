"""This module contains all configuration information used to run simulations
"""
from multiprocessing import cpu_count
from collections import deque
import copy
from icarus.util import Tree

# GENERAL SETTINGS

# Level of logging output
# Available options: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = 'INFO'

# If True, executes simulations in parallel using multiple processes
# to take advantage of multicore CPUs
PARALLEL_EXECUTION = True

# Number of processes used to run simulations in parallel.
# This option is ignored if PARALLEL_EXECUTION = False
N_PROCESSES = cpu_count()

# Granularity of caching.
# Currently, only OBJECT is supported
CACHING_GRANULARITY = 'OBJECT'

# Format in which results are saved.
# Result readers and writers are located in module ./icarus/results/readwrite.py
# Currently only PICKLE is supported 
RESULTS_FORMAT = 'PICKLE'

# Number of times each experiment is replicated
# This is necessary for extracting confidence interval of selected metrics
N_REPLICATIONS = 1

# List of metrics to be measured in the experiments
# The implementation of data collectors are located in ./icaurs/execution/collectors.py
DATA_COLLECTORS = ['CACHE_HIT_RATIO', 'LATENCY']


# This is a base experiment configuration with all the parameters that won't
# change across experiments of the same campaign
base = Tree()
base['network_model'] = Tree()
base['desc'] = "Base experiment"    # Description shown during execution

# Default experiment parameters
CACHE_POLICY = 'LRU'
ALPHA = 0.8
# Number of content objects
N_CONTENTS = 3*10**4
# Number of content requests generated to prepopulate the caches
# These requests are not logged
N_WARMUP = 2*10**4
# Number of content requests generated after the warmup and logged
# to generate results. 
N_MEASURED = 4*10**4
# Number of requests per second (over the whole network)
REQ_RATE = 10


default = Tree()
default['workload'] = {
    'name':      'STATIONARY',
    'alpha':      ALPHA,
    'n_contents': N_CONTENTS,
    'n_warmup':   N_WARMUP,
    'n_measured': N_MEASURED,
    'rate':       REQ_RATE
                       }
default['content_placement']['name'] = 'UNIFORM'
default['cache_policy']['name'] = CACHE_POLICY

# Instantiate experiment queue
EXPERIMENT_QUEUE = deque()

# C-FIB size sensitivity

base = copy.deepcopy(default)
# Total size of network cache as a fraction of content population
network_cache = 0.01
base['topology']['name'] = 'ROCKET_FUEL'
base['topology']['source_ratio'] = 0.1
base['topology']['ext_delay'] = 34
base['joint_cache_rsn_placement'] = {'network_cache': network_cache}
for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for asn in [3257]:
        #for rsn_cache_ratio in [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]:
        for rsn_cache_ratio in [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]:
            for strategy in ['LIRA_BC', 'LIRA_DFIB']:
                experiment = copy.deepcopy(base)
                experiment['topology']['asn'] = asn
                experiment['strategy']['name'] = strategy
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = rsn_cache_ratio * network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = rsn_cache_ratio
                experiment['desc'] = "RSN size sensitivity -> RSN/cache ratio: %s" % str(rsn_cache_ratio)
                EXPERIMENT_QUEUE.append(experiment)
