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
CACHING_PROBABILITY = 0.25

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
network_cache = 0.30 # 0.95
base['topology']['name'] = 'ROCKET_FUEL'
base['topology']['source_ratio'] = 0.1
base['topology']['ext_delay'] = 0 # XXX Latency penalty for reaching server is implemented in the LATENCY collector
base['topology']['asn'] = 3257
base['joint_cache_rsn_placement'] = {'network_cache': network_cache}
base['warmup_strategy']['name'] = WARMUP_STRATEGY

"""
2. Pick optimal TFIB size for TFIB_DC and TFIB_SC

for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for asn in [3257]:
        for rsn_cache_ratio in [2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]:
            for strategy in ['TFIB_BC', 'TFIB_SC']:
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                if strategy is 'TFIB_SC':
                    experiment['warmup_strategy']['extra_quota'] = 10000
                    experiment['warmup_strategy']['fan_out'] = 100
                experiment['topology']['asn'] = asn
                experiment['strategy']['name'] = strategy
                if strategy is 'TFIB_SC': 
                    experiment['strategy']['extra_quota'] = 1000
                    experiment['strategy']['fan_out'] = 2
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = rsn_cache_ratio * network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = rsn_cache_ratio
                experiment['desc'] = "RSN size sensitivity -> RSN/cache ratio: %s" % str(rsn_cache_ratio)
                EXPERIMENT_QUEUE.append(experiment)

"""

"""
3. Pick optimal network cache size for TFIB_DC and TFIB_SC
"""
"""
for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for strategy in ['TFIB_SC', 'TFIB_DC']:
        for net_cache in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            experiment = copy.deepcopy(base)
            experiment['warmup_strategy']['name'] = strategy
            experiment['warmup_strategy']['extra_quota'] = 10000
            experiment['warmup_strategy']['fan_out'] = 10
            experiment['strategy']['name'] = strategy
            experiment['strategy']['fan_out'] = 1
            experiment['strategy']['extra_quota'] = 2
            experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
            experiment['joint_cache_rsn_placement']['network_rsn'] = 128*net_cache
            experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
            experiment['joint_cache_rsn_placement']['network_cache'] =  net_cache
            experiment['desc'] = "strategy network_cache: %s" % str(net_cache)
            EXPERIMENT_QUEUE.append(experiment)
"""

"""
1. Compare strategies as initial results

for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    #for strategy in ['TFIB_SC', 'NDN_PROB', 'TFIB_BC', 'NRR_PROB']:
    for strategy in ['TFIB_SC']:
        for net_cache in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            if strategy == 'TFIB_SC':
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['warmup_strategy']['extra_quota'] = 10000
                experiment['warmup_strategy']['fan_out'] = 10
                experiment['strategy']['name'] = strategy
                experiment['strategy']['fan_out'] = 2
                experiment['strategy']['extra_quota'] = 10000
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 128*net_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
                experiment['joint_cache_rsn_placement']['network_cache'] =  net_cache
                experiment['desc'] = "strategy network_cache: %s" % str(net_cache)
                EXPERIMENT_QUEUE.append(experiment)
            else:
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['strategy']['name'] = strategy
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 128 * net_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
                experiment['joint_cache_rsn_placement']['network_cache'] =  net_cache
                experiment['desc'] = "strategy network_cache: %s" % str(net_cache)
                EXPERIMENT_QUEUE.append(experiment)
"""

"""
2. Pick optimal TFIB size
"""
"""
for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for asn in [3257]:
        for rsn_cache_ratio in [2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 512.0]:
            for strategy in ['TFIB_DC', 'TFIB_SC']:
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['warmup_strategy']['extra_quota'] = 10000
                experiment['warmup_strategy']['fan_out'] = 10
                experiment['topology']['asn'] = asn
                experiment['strategy']['name'] = strategy
                experiment['strategy']['extra_quota'] = 2
                experiment['strategy']['fan_out'] = 1
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = rsn_cache_ratio * network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = rsn_cache_ratio
                experiment['desc'] = "RSN size sensitivity -> RSN/cache ratio: %s" % str(rsn_cache_ratio)
                EXPERIMENT_QUEUE.append(experiment)
"""

"""
# Compare dynamic and static cost TFIB strategies
"""

"""
for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for strategy in ['TFIB_DC', 'TFIB_SC']:
        for extra_quota in [1, 2, 3, 4]:
            experiment = copy.deepcopy(base)
            experiment['warmup_strategy']['name'] = strategy
            experiment['warmup_strategy']['extra_quota'] = 1000000
            experiment['warmup_strategy']['fan_out'] = 10
            experiment['strategy']['extra_quota'] = extra_quota
            experiment['strategy']['fan_out'] = 1
            experiment['topology']['asn'] = 3257 #3967
            experiment['strategy']['name'] = strategy
            #TODO add quota increment default value of 1
            experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
            experiment['joint_cache_rsn_placement']['network_rsn'] = 128 * network_cache
            experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
            experiment['desc'] = "extra_quota: %s" % str(extra_quota)
            EXPERIMENT_QUEUE.append(experiment)
#"""

#"""
for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    for strategy in ['TFIB_DC']:
        for quota_increment in [0.25, 0.5, 0.75, 1.0, 1.25, 1.50, 1.75, 2.0, 2.25, 2.50, 2.75, 3.0]:
            experiment = copy.deepcopy(base)
            experiment['warmup_strategy']['name'] = strategy
            experiment['warmup_strategy']['extra_quota'] = 1000000
            experiment['warmup_strategy']['fan_out'] = 10
            experiment['topology']['asn'] = 3257 #3967
            experiment['strategy']['name'] = strategy
            #experiment['strategy']['rsn_fresh'] = 5.0
            experiment['strategy']['extra_quota'] = 2
            experiment['strategy']['fan_out'] = 1
            experiment['strategy']['quota_increment'] = quota_increment
            experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
            experiment['joint_cache_rsn_placement']['network_rsn'] = 128* network_cache
            experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
            experiment['desc'] = "quota_increment: %s" % str(quota_increment)
            EXPERIMENT_QUEUE.append(experiment)
#"""
"""
Zipf Tests
"""
"""

for joint_cache_rsn_placement in ['CACHE_ALL_RSN_ALL']:
    #for strategy in ['TFIB_SC', 'NDN_PROB', 'TFIB_BC', 'NRR_PROB', 'TFIB_DC']:
    #for strategy in ['TFIB_SC', 'TFIB_DC']:
    for strategy in ['NRR_PROB']:
        for zipf in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            if strategy == 'TFIB_SC':
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['warmup_strategy']['extra_quota'] = 10000
                experiment['warmup_strategy']['fan_out'] = 10
                experiment['strategy']['name'] = strategy
                experiment['strategy']['fan_out'] = 1
                experiment['strategy']['extra_quota'] = 1
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 128*network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
                experiment['workload']['alpha'] = zipf
                experiment['desc'] = "strategy zipf: %s" % str(zipf)
                EXPERIMENT_QUEUE.append(experiment)
            elif strategy == 'TFIB_DC':
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['warmup_strategy']['extra_quota'] = 10000
                experiment['warmup_strategy']['fan_out'] = 10
                experiment['strategy']['name'] = strategy
                experiment['strategy']['fan_out'] = 1
                experiment['strategy']['extra_quota'] = 1
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 128*network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
                experiment['workload']['alpha'] = zipf
                experiment['desc'] = "strategy zipf: %s" % str(zipf)
                EXPERIMENT_QUEUE.append(experiment)
            else:
                experiment = copy.deepcopy(base)
                experiment['warmup_strategy']['name'] = strategy
                experiment['strategy']['name'] = strategy
                experiment['joint_cache_rsn_placement']['name'] = joint_cache_rsn_placement
                experiment['joint_cache_rsn_placement']['network_rsn'] = 128 * network_cache
                experiment['joint_cache_rsn_placement']['rsn_cache_ratio'] = 128
                experiment['workload']['alpha'] = zipf
                experiment['desc'] = "strategy zipf: %s" % str(zipf)
                EXPERIMENT_QUEUE.append(experiment)
"""
