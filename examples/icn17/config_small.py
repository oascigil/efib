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
N_PROCESSES = cpu_count()/2 #1

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
DATA_COLLECTORS = ['SAT_RATE', 'CACHE_HIT_RATIO', 'LATENCY', 'OVERHEAD']

# Strategy that will be executed during warm-up phase
WARMUP_STRATEGY = 'LIRA_DFIB_OPH'

#Probability of caching
CACHING_PROBABILITY = 0.1

# This is a base experiment configuration with all the parameters that won't
# change across experiments of the same campaign
base = Tree()
base['network_model'] = Tree()
base['desc'] = "Base experiment"    # Description shown during execution

# Default experiment parameters
CACHE_POLICY = 'LRU'
# Alpha determines content selection (Zipf parameter)
ALPHA = 0.7
# Beta determines the zipf parameter determining how sources are selected
BETA = 0.9
# Number of content objects
N_CONTENTS = 10**4
# Number of content requests generated to prepopulate the caches
# These requests are not logged
N_WARMUP = 2*36*10**4 # two hours
# Number of content requests generated after the warmup and logged
# to generate results. 
N_MEASURED = 36*10**4 # one hour
# Number of requests per second (over the whole network)
REQ_RATE = 100

default = Tree()
default['workload'] = {
    'name':      'STATIONARY',
    'alpha':      ALPHA,
    'n_contents': N_CONTENTS,
    'n_warmup':   N_WARMUP,
    'n_measured': N_MEASURED,
    'rate':       REQ_RATE
    # 'beta':       BETA
                       }
default['content_placement']['name'] = 'UNIFORM'
default['cache_policy']['name'] = CACHE_POLICY

# Instantiate experiment queue
EXPERIMENT_QUEUE = deque()

# C-FIB size sensitivity

base = copy.deepcopy(default)
# Total size of network cache as a fraction of content population
network_cache = 0.95 # 0.01
base['topology']['name'] = 'ROCKET_FUEL'
base['topology']['source_ratio'] = 0.1
base['topology']['ext_delay'] = 5 # 34
base['joint_cache_rsn_placement'] = {'network_cache': network_cache}
base['warmup_strategy']['name'] = WARMUP_STRATEGY
base['warmup_strategy']['p'] = CACHING_PROBABILITY



"""
1. Extra Quota with fan_out (fixed probability of 0.5)
"""

"""
for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for strategy in ['LIRA_DFIB_OPH', 'LIRA_DFIB_SC']:    
        for fan_out in [1, 2, 3]:
            for extra_quota in [0, 1, 2, 3, 4, 5]:
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['warmup_strategy']['extra_quota'] = 10
                experiment['warmup_strategy']['fan_out'] = 100
                experiment['topology']['asn'] = 3257 #3967
                experiment['strategy']['name'] = strategy
                #experiment['strategy']['rsn_fresh'] = 5.0
                experiment['strategy']['p'] = 0.5
                experiment['strategy']['extra_quota'] = extra_quota
                experiment['strategy']['fan_out'] = fan_out
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 64* network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 64
                experiment['desc'] = "fan out: %s" % str(fan_out)
                EXPERIMENT_QUEUE.append(experiment)
"""

for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for strategy in ['LIRA_DFIB_OPH']:    
        for fan_out in [1, 2]:
            for quota_increment in [0.25, 0.5, 0.75, 1.0, 1.25, 1.50, 1.75, 2.0, 2.25, 2.50, 2.75, 3.0]:
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['warmup_strategy']['extra_quota'] = 10
                experiment['warmup_strategy']['fan_out'] = 100
                experiment['topology']['asn'] = 3257 #3967
                experiment['strategy']['name'] = strategy
                #experiment['strategy']['rsn_fresh'] = 5.0
                experiment['strategy']['p'] = 0.5
                experiment['strategy']['extra_quota'] = 2
                experiment['strategy']['fan_out'] = fan_out
                experiment['strategy']['quota_increment'] = quota_increment
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 64* network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 64
                experiment['desc'] = "quota_increment: %s" % str(quota_increment)
                EXPERIMENT_QUEUE.append(experiment)
