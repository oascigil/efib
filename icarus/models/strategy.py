# -*- coding: utf-8 -*-
"""Implementations of all caching and routing strategies
"""
from __future__ import division
import random
import abc
import collections

import networkx as nx

from icarus.registry import register_strategy
from icarus.util import inheritdoc, multicast_tree, path_links


__all__ = [
       'Strategy',
       'Hashrouting',
       'HashroutingSymmetric',
       'HashroutingAsymmetric',
       'HashroutingMulticast',
       'HashroutingHybridAM',
       'HashroutingHybridSM',
       'NoCache',
       'Edge',
       'LeaveCopyEverywhere',
       'LeaveCopyDown',
       'CacheLessForMore',
       'RandomBernoulli',
       'RandomChoice',
       'LiraLce',
       'LiraProbCache',
       'LiraChoice',
       'NearestReplicaRouting',
       'LiraDfib',
       'LiraDfibOph',
       'LiraDfibSc',
       'Tfib_sc',
       'Tfib_dc',
       'TfibBC',
       'NdnProb'
           ]

#TODO: Implement BaseOnPath to reduce redundant code
#TODO: In Hashrouting, implement request routing phase under in single function

class RsnNexthop(object):
    """ 
    A nexthop entry along with its properties such as timestamp of insertion, 
    distance to the serving node, etc.
    """
    def __init__(self, nexthop, dest, distance, time_stamp, used=False):
        """Constructor

        Parameters
        _________
        nexthop : nexthop node to get to the cache node
        destination : cache node identifier 
        distance : distance (i.e., number of hops) to the cache node
        timestamp : time of insertion to Rsn OR time of last successfull content retrieval using this nexthop 
        """
        self.nexthop = nexthop
        self.destination = dest
        self.distance = distance
        self.time_stamp = time_stamp
        self.used_before = used # has this next_hop been used before ?
    
    def __hash__():
        """ 
        Make RsnNexthop a hashable type
        """
        return hash(repr(self))

    def age(self, time_now):
        age = time_now - self.time_stamp
        if age < 0:
            raise ValueError("Age must be >= 0")
        return age
        
    def is_expired(self, time_now, expiration_interval):
        """
        Determines whether the nexthop entry is expired
        """
        if (time_now - self.time_stamp) > expiration_interval:
           return True
        return False

    def is_used(self):
        return self.used_before

    def set_is_used(self):
        self.used_before = True

    def unset_is_used(self):
        self.used_before = False

    def is_used_and_fresh(self, time_now, fresh_interval):
        if self.used_before and ((time_now - self.time_stamp) <= fresh_interval):
            return True

        return False
    
    def is_fresher(self, nexthop_obj):
        """
        Determines if self is fresher than nexthop_obj

        Parameter
        ---------
        nexthop_obj : instance of a RsnNexthop class

        Returns
        -------
        True if self is fresher than nexthop_obj
        False if nexthop_obj is None or older than self
        """
        if nexthop_obj is None:
            return False
        
        if self.timestamp > nexthop_obj.timestamp:
            return True
        else:
            return False
            
    def is_fresh(self, time_now, fresh_interval):
        """
        Determines whether the nexthop entry is fresh
        """
        if (time_now - self.time_stamp) > fresh_interval:
            return False
        return True

def get_timestamp(rsn_nexthop_obj):
    return rsn_nexthop_obj.time_stamp

class RsnEntry(object):
    """An entry in the RSN table retrieved by using a content name as the index"""
    # self.expiration_interval = 0

    def __init__(self, fresh_interval = float("inf"), expiration_interval = float("inf")):
        """Constructor 
        
        Parameters
        ----------
        nexthops : a list of RsnNexthop objects,
        fresh_interval : the limit on the age of an entry for it to be considered fresh
        expiration_interval : the limit on the age of an entry; entry considered stale if age > expiration_interval
        """
        self.nexthops = []
        self.fresh_interval = fresh_interval
        self.expiration_interval = expiration_interval
        #RsnEntry.expiration_interval = expiration_interval
    
    def __hash__():
        """ 
        Make RsnEntry a hashable type
        """
        return hash(repr(self))

    def get_nexthop(self, node):
        """
        Fetch the nexthop entry whose next-hop field is node
        Parameter:
        ---------
        node : node identifier

        Return:
        ------
        Return RsnNexthop whose nexthop property is node
        If there is no such RnsNexthop, then return None
        """
        for nh in self.nexthops:
            if nh.nexthop == node:
                return nh
        else:
            return None


    def delete_nexthop(self, nh):
        """ Delete a nexthop from the entry

        Parameters
        ----------
        nh : node identifier; delete nexthop entry whose nexthop is nh
        """
        self.nexthops = [x for x in self.nexthops if x.nexthop != nh] 

    def insert_nexthop(self, nexthop, dest, distance, time, is_used=False):
        """insert a nexthop entry along with distance and time of insertion attributes
        Parameters
        ---------
        nexthop : nexthop node identifier
        dest : destination cache node identifier
        distance : number of hops to the cache node
        time : time of insertion or tiem of last access to the entry

        Return
        ------
        if an entry exists with the same nexthop attr, update attr. and return the entry
        otherwise return the new entry inserted
        """
        self.nexthops = [x for x in self.nexthops if not x.is_expired(time, self.expiration_interval)]
        # check if there is a nexthop entry
        for nh in self.nexthops:
            if nh.nexthop == nexthop:
                nh.time_stamp = time
                nh.destination = dest
                nh.distance = distance
                nh.is_used = is_used
                return nh

        nexthop = RsnNexthop(nexthop, dest, distance, time, is_used)
        self.nexthops.append(nexthop)
        return nexthop
 
    # this method prefers a "used" nexthop over other unused nexthop entries
    def get_best_k_entry(self, time, node, num_entries):
        """
        Parameters
        ----------
        time : current time

        Returns 
        -------
        return the nexthop (i.e., with min age) entry as follows: entries that are both used and fresh have priority over unused entries. 
        
        Used entry means that the trail has been used to retrieve content before.

        """

        self.nexthops = [x for x in self.nexthops if not x.is_expired(time, self.expiration_interval)] # remove stale entries
        
        # list comprehension is a nice tool!
        best_nexthops = [x for x in self.nexthops if x.is_used_and_fresh(time, self.fresh_interval)]
        best_nexthops = [x for x in best_nexthops if x.nexthop != node]
        
        best_nexthops.sort(key=get_timestamp, reverse=True)
        if (len(best_nexthops) >= num_entries):
            return best_nexthops[0:num_entries]
        
        # Add freshest nexthops if there is still space 
        filtered_nexthops = [x for x in self.nexthops if not x.is_used_and_fresh(time, self.fresh_interval)]
        filtered_nexthops = [x for x in filtered_nexthops if x.nexthop != node]
        
        filtered_nexthops.sort(key=get_timestamp, reverse=True)
        len_best_nexthops = len(best_nexthops)
        for nh in filtered_nexthops[0:(num_entries-len_best_nexthops)]:
            best_nexthops.append(nh)
        
        return best_nexthops

    def get_freshest_entry(self, time):
        """ 
        Parameters
        ----------
        time : current time

        Returns 
        -------
        freshest nexthop (i.e., with min age) entry that is not stale
        Otherwise, it returns None
        """
        self.nexthops = [x for x in self.nexthops if not x.is_expired(time, self.expiration_interval)] # remove stale entries
        
        freshest = None
        for n in self.nexthops:
            if freshest is None or n.age(time) < freshest.age(time):
                freshest = n

        return freshest
    
    def get_freshest_except_node(self, time, node):
        """ 
        Parameters
        ----------
        time : current time

        Returns 
        -------
        freshest nexthop : freshest (i.e., with min age) entry that is not stale and whose node attr is not equal to node
        Otherwise, it returns None
        """
        self.nexthops = [x for x in self.nexthops if not x.is_expired(time, self.expiration_interval)]
        freshest = None
        for n in self.nexthops:
            if freshest is None or (n.age(time) < freshest.age(time) and n.nexthop != node):
                freshest = n

        if freshest is not None and freshest.nexthop == node:
            freshest = None

        return freshest
    
    def get_topk_freshest_except_node(self, time, node, k):
        """ 
        Parameters
        ----------
        time : current time
        node : nexthop node that is not considered when finding the freshest entry
        k : max. number of nexthops returned

        Returns 
        -------
        list of k most freshest nexthops : freshest (i.e., with min age) entry that is not stale and whose node attr is not equal to node
        """
        
        self.nexthops = [x for x in self.nexthops if not x.is_expired(time, self.expiration_interval)]
        # Sort the list of nexthops by their age
        self.nexthops.sort(key=get_timestamp, reverse=True)
        
        filtered_nexthops = self.nexthops[:]
        filtered_nexthops = [x for x in filtered_nexthops if x.nexthop != node]
        return filtered_nexthops[0:k]

        #nexthop_obj = self.nexthops[0] if len(self.nexthops) > 0 else None
        #if nexthop_obj is not None and nexthop_obj.is_fresh(time, self.fresh_interval):
        #    return [nexthop_obj]
        #else:
        #    return self.nexthops[0:k]

    def get_freshest_except_nodes(self, time, nodes):
        """ 
        Parameters
        ----------
        time : current time
        nodes : list of nodes that are not considered when finding the freshest entry

        Returns 
        -------
        freshest nexthop : freshest (i.e., with min age) entry that is not stale and whose node attr is not equal to node
        Otherwise, it returns None
        """
        self.nexthops = [x for x in self.nexthops if not x.is_expired(time, self.expiration_interval)]
        freshest = None
        for n in self.nexthops:
            if freshest is None or (n.age(time) < freshest.age(time) and n.nexthop not in nodes):
                freshest = n
        
        if freshest is not None and freshest.nexthop in nodes:
            freshest = None

        return freshest


class Strategy(object):
    """Base strategy imported by all other strategy classes"""
    
    __metaclass__ = abc.ABCMeta

    def __init__(self, view, controller, **kwargs):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        kwargs : keyworded arguments, optional
            Additional strategy parameters
        """
        self.view = view
        self.controller = controller
        
    @abc.abstractmethod
    def process_event(self, time, receiver, content, log):
        """Process an event received from the simulation engine.
        
        This event is processed by executing relevant actions of the network
        controller, potentially based on the current status of the network
        retrieved from the network view.
        
        Parameters
        ----------
        time : int
            The timestamp of the event
        receiver : any hashable type
            The receiver node requesting a content
        content : any hashable type
            The content identifier requested by the receiver
        log : bool
            Indicates whether the event must be registered by the data
            collectors attached to the network.
        """
        raise NotImplementedError('The selected strategy must implement '
                                  'a process_event method')



class Hashrouting(Strategy):
    """Base class for all hash-routing implementations. Hash-routing
    implementations are described in [1]_.
        
    References
    ----------
    .. [1] L. Saino, I. Psaras and G. Pavlou, Hash-routing Schemes for
    Information-Centric Networking, in Proceedings of ACM SIGCOMM ICN'13
    workshop. Available:
    https://www.ee.ucl.ac.uk/~lsaino/publications/hashrouting-icn13.pdf
    
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(Hashrouting, self).__init__(view, controller)
        self.cache_nodes = view.cache_nodes()
        # Allocate results of hash function to caching nodes 
        self.cache_assignment = dict((i, self.cache_nodes[i]) 
                                      for i in range(len(self.cache_nodes)))

    def authoritative_cache(self, content):
        """Return the authoritative cache node for the given content
        
        Parameters
        ----------
        content : any hashable type
            The identifier of the content
            
        Returns
        -------
        authoritative_cache : any hashable type
            The node on which the authoritative cache is deployed
        """
        return self.cache_assignment[self.hash(content)]

    def hash(self, content):
        """Return a hash code of the content for hash-routing purposes
        
        
        Parameters
        ----------
        content : any hashable type
            The identifier of the content
            
        Returns
        -------
        hash : int
            The hash code of the content
        """
        #TODO: This hash function needs revision because it does not return
        # equally probably hash codes
        n = len(self.cache_nodes)
        h = content % n
        return h if (content/n) % 2 == 0 else (n - h - 1)


@register_strategy('HR_SYMM')
class HashroutingSymmetric(Hashrouting):
    """Hash-routing with symmetric routing (HR SYMM)
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(HashroutingSymmetric, self).__init__(view, controller)

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        cache = self.authoritative_cache(content)
        # handle (and log if required) actual request
        self.controller.start_session(time, receiver, content, log)
        # Forward request to authoritative cache
        self.controller.forward_request_path(receiver, cache)
        if self.controller.get_content(cache):
            # We have a cache hit here
            self.controller.forward_content_path(cache, receiver)
        else:
            # Cache miss: go all the way to source
            self.controller.forward_request_path(cache, source)
            if not self.controller.get_content(source):
                raise RuntimeError('The content is not found the expected source')
            self.controller.forward_content_path(source, cache)
            # Insert in cache
            self.controller.put_content(cache)
            # Forward to receiver
            self.controller.forward_content_path(cache, receiver)
        self.controller.end_session()    


@register_strategy('HR_ASYMM')
class HashroutingAsymmetric(Hashrouting):
    """Hash-routing with asymmetric routing (HR ASYMM) 
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(HashroutingAsymmetric, self).__init__(view, controller)
        
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        cache = self.authoritative_cache(content)
        # handle (and log if required) actual request
        self.controller.start_session(time, receiver, content, log)
        # Forward request to authoritative cache
        self.controller.forward_request_path(receiver, cache)
        if self.controller.get_content(cache):
            # We have a cache hit here
            self.controller.forward_content_path(cache, receiver)
        else:
            # Cache miss: go all the way to source
            self.controller.forward_request_path(cache, source)
            if not self.controller.get_content(source):
                raise RuntimeError('The content was not found at the expected source')   
            if cache in self.view.shortest_path(source, receiver):
                # Forward to cache
                self.controller.forward_content_path(source, cache)
                # Insert in cache
                self.controller.put_content(cache)
                # Forward to receiver
                self.controller.forward_content_path(cache, receiver)
            else:
                # Forward to receiver straight away
                self.controller.forward_content_path(source, receiver)
        self.controller.end_session()


@register_strategy('HR_MULTICAST')
class HashroutingMulticast(Hashrouting):
    """
    Hash-routing implementation with multicast delivery of content packets.
    
    In this strategy, if there is a cache miss, when contant packets return in
    the domain, the packet is multicast, one copy being sent to the
    authoritative cache and the other to the receiver. If the cache is on the
    path from source to receiver, this strategy behaves as a normal symmetric
    hash-routing strategy.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(HashroutingMulticast, self).__init__(view, controller)
        # map id of content to node with cache responsibility

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        cache = self.authoritative_cache(content)
        # handle (and log if required) actual request
        self.controller.start_session(time, receiver, content, log)
        # Forward request to authoritative cache
        self.controller.forward_request_path(receiver, cache)
        if self.controller.get_content(cache):
            # We have a cache hit here
            self.controller.forward_content_path(cache, receiver)
        else:
            # Cache miss: go all the way to source
            self.controller.forward_request_path(cache, source)
            if not self.controller.get_content(source):
                raise RuntimeError('The content is not found the expected source') 
            if cache in self.view.shortest_path(source, receiver):
                self.controller.forward_content_path(source, cache)
                # Insert in cache
                self.controller.put_content(cache)
                # Forward to receiver
                self.controller.forward_content_path(cache, receiver)
            else:
                # Multicast
                cache_path = self.view.shortest_path(source, cache)
                recv_path = self.view.shortest_path(source, receiver)
                
                # find what is the node that has to fork the content flow
                for i in range(1, min([len(cache_path), len(recv_path)])):
                    if cache_path[i] != recv_path[i]:
                        fork_node = cache_path[i-1]
                        break
                else: fork_node = cache
                self.controller.forward_content_path(source, fork_node, main_path=True)
                self.controller.forward_content_path(fork_node, receiver, main_path=True)
                self.controller.forward_content_path(fork_node, cache, main_path=False)
                self.controller.put_content(cache)
        self.controller.end_session()


@register_strategy('HR_HYBRID_AM')
class HashroutingHybridAM(Hashrouting):
    """
    Hash-routing implementation with hybrid asymmetric-multicast delivery of
    content packets.
    
    In this strategy, if there is a cache miss, when content packets return in
    the domain, the packet is delivered to the receiver following the shortest
    path. If the additional number of hops required to send a copy to the
    authoritative cache is below a specific fraction of the network diameter,
    then one copy is sent to the authoritative cache as well. If the cache is
    on the path from source to receiver, this strategy behaves as a normal
    symmetric hash-routing strategy.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, max_stretch=0.2):
        super(HashroutingHybridAM, self).__init__(view, controller)
        self.max_stretch = nx.diameter(view.topology()) * max_stretch

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        cache = self.authoritative_cache(content)
        # handle (and log if required) actual request
        self.controller.start_session(time, receiver, content, log)
        # Forward request to authoritative cache
        self.controller.forward_request_path(receiver, cache)
        if self.controller.get_content(cache):
            # We have a cache hit here
            self.controller.forward_content_path(cache, receiver)
        else:
            # Cache miss: go all the way to source
            self.controller.forward_request_path(cache, source)
            if not self.controller.get_content(source):
                raise RuntimeError('The content was not found at the expected source') 
            
            if cache in self.view.shortest_path(source, receiver):
                # Forward to cache
                self.controller.forward_content_path(source, cache)
                # Insert in cache
                self.controller.put_content(cache)
                # Forward to receiver
                self.controller.forward_content_path(cache, receiver)
            else:
                # Multicast
                cache_path = self.view.shortest_path(source, cache)
                recv_path = self.view.shortest_path(source, receiver)
                
                # find what is the node that has to fork the content flow
                for i in range(1, min([len(cache_path), len(recv_path)])):
                    if cache_path[i] != recv_path[i]:
                        fork_node = cache_path[i-1]
                        break
                else: fork_node = cache
                self.controller.forward_content_path(source, receiver, main_path=True)
                # multicast to cache only if stretch is under threshold
                if len(self.view.shortest_path(fork_node, cache)) - 1 < self.max_stretch:
                    self.controller.forward_content_path(fork_node, cache, main_path=False)
                    self.controller.put_content(cache)
        self.controller.end_session()
        

@register_strategy('HR_HYBRID_SM')
class HashroutingHybridSM(Hashrouting):
    """
    Hash-routing implementation with hybrid symmetric-multicast delivery of
    content packets.
    
    In this implementation, the edge router receiving a content packet decides
    whether to deliver the packet using multicast or symmetric hash-routing
    based on the total cost for delivering the Data to both cache and receiver
    in terms of hops.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(HashroutingHybridSM, self).__init__(view, controller)

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        cache = self.authoritative_cache(content)
        # handle (and log if required) actual request
        self.controller.start_session(time, receiver, content, log)
        # Forward request to authoritative cache
        self.controller.forward_request_path(receiver, cache)
        if self.controller.get_content(cache):
            # We have a cache hit here
            self.controller.forward_content_path(cache, receiver)
        else:
            # Cache miss: go all the way to source
            self.controller.forward_request_path(cache, source)
            if not self.controller.get_content(source):
                raise RuntimeError('The content is not found the expected source') 
            
            if cache in self.view.shortest_path(source, receiver):
                self.controller.forward_content_path(source, cache)
                # Insert in cache
                self.controller.put_content(cache)
                # Forward to receiver
                self.controller.forward_content_path(cache, receiver)
            else:
                # Multicast
                cache_path = self.view.shortest_path(source, cache)
                recv_path = self.view.shortest_path(source, receiver)
                
                # find what is the node that has to fork the content flow
                for i in range(1, min([len(cache_path), len(recv_path)])):
                    if cache_path[i] != recv_path[i]:
                        fork_node = cache_path[i-1]
                        break
                else: fork_node = cache
                
                symmetric_path_len = len(self.view.shortest_path(source, cache)) + \
                                     len(self.view.shortest_path(cache, receiver)) - 2
                multicast_path_len = len(self.view.shortest_path(source, fork_node)) + \
                                     len(self.view.shortest_path(fork_node, cache)) + \
                                     len(self.view.shortest_path(fork_node, receiver)) - 3
                
                self.controller.put_content(cache)
                # If symmetric and multicast have equal cost, choose symmetric
                # because of easier packet processing
                if symmetric_path_len <= multicast_path_len: # use symmetric delivery
                    # Symmetric delivery
                    self.controller.forward_content_path(source, cache, main_path=True)
                    self.controller.forward_content_path(cache, receiver, main_path=True)
                else:
                    # Multicast delivery
                    self.controller.forward_content_path(source, receiver, main_path=True)
                    self.controller.forward_content_path(fork_node, cache, main_path=False)
                self.controller.end_session()


@register_strategy('NO_CACHE')
class NoCache(Strategy):
    """Strategy without any caching
    
    This corresponds to the traffic in a normal TCP/IP network without any
    CDNs or overlay caching, where all content requests are served by the 
    original source.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(NoCache, self).__init__(view, controller)
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source
        self.controller.start_session(time, receiver, content, log)
        self.controller.forward_request_path(receiver, source)
        self.controller.get_content(source)
        # Route content back to receiver
        path = list(reversed(path))
        self.controller.forward_content_path(source, receiver, path)
        self.controller.end_session()


@register_strategy('EDGE')
class Edge(Strategy):
    """Edge caching strategy.
    
    In this strategy only a cache at the edge is looked up before forwarding
    a content request to the original source.
    
    In practice, this is like an LCE but it only queries the first cache it
    finds in the path. It is assumed to be used with a topology where each
    PoP has a cache but it simulates a case where the cache is actually further
    down the access network and it is not looked up for transit traffic passing
    through the PoP but only for PoP-originated requests.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller):
        super(Edge, self).__init__(view, controller)

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        edge_cache = None
        for u, v in path_links(path):
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                edge_cache = v
                if self.controller.get_content(v):
                    serving_node = v
                else:
                    # Cache miss, get content from source
                    self.controller.forward_request_path(v, source)
                    self.controller.get_content(source)
                    serving_node = source
                break
        else:
            # No caches on the path at all, get it from source
            self.controller.get_content(v)
            serving_node = v
            
        # Return content
        path = list(reversed(self.view.shortest_path(receiver, serving_node)))
        self.controller.forward_content_path(serving_node, receiver, path)
        if serving_node == source:
            self.controller.put_content(edge_cache)
        self.controller.end_session()


@register_strategy('LCE')
class LeaveCopyEverywhere(Strategy):
    """Leave Copy Everywhere (LCE) strategy.
    
    In this strategy a copy of a content is replicated at any cache on the
    path between serving node and receiver.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(LeaveCopyEverywhere, self).__init__(view, controller)

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        for u, v in path_links(path):
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break
            # No cache hits, get content from source
            self.controller.get_content(v)
            serving_node = v
        # Return content
        path = list(reversed(self.view.shortest_path(receiver, serving_node)))
        for u, v in path_links(path):
            self.controller.forward_content_hop(u, v)
            if self.view.has_cache(v):
                # insert content
                self.controller.put_content(v)
        self.controller.end_session()


@register_strategy('LCD')
class LeaveCopyDown(Strategy):
    """Leave Copy Down (LCD) strategy.
    
    According to this strategy, one copy of a content is replicated only in
    the caching node you hop away from the serving node in the direction of
    the receiver. This strategy is described in [2]_.
    
    Rereferences
    ------------
    ..[2] N. Laoutaris, H. Che, i. Stavrakakis, The LCD interconnection of LRU
          caches and its analysis. 
          Available: http://cs-people.bu.edu/nlaout/analysis_PEVA.pdf 
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(LeaveCopyDown, self).__init__(view, controller)

    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        for u, v in path_links(path):
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break
        else:
            # No cache hits, get content from source
            self.controller.get_content(v)
            serving_node = v
        # Return content
        path = list(reversed(self.view.shortest_path(receiver, serving_node)))
        # Leave a copy of the content only in the cache one level down the hit
        # caching node
        copied = False
        for u, v in path_links(path):
            self.controller.forward_content_hop(u, v)
            if not copied and v != receiver and self.view.has_cache(v):
                self.controller.put_content(v)
                copied = True
        self.controller.end_session()


@register_strategy('PROB_CACHE')
class ProbCache(Strategy):
    """ProbCache strategy [4]_
    
    This strategy caches content objects probabilistically on a path with a
    probability depending on various factors, including distance from source
    and destination and caching space available on the path.
    
    This strategy was originally proposed in [3]_ and extended in [4]_. This
    class implements the extended version described in [4]_. In the extended
    version of ProbCache the :math`x/c` factor of the ProbCache equation is
    raised to the power of :math`c`.
    
    References
    ----------
    ..[3] I. Psaras, W. Chai, G. Pavlou, Probabilistic In-Network Caching for
          Information-Centric Networks, in Proc. of ACM SIGCOMM ICN '12
          Available: http://www.ee.ucl.ac.uk/~uceeips/prob-cache-icn-sigcomm12.pdf
    ..[4] I. Psaras, W. Chai, G. Pavlou, In-Network Cache Management and
          Resource Allocation for Information-Centric Networks, IEEE
          Transactions on Parallel and Distributed Systems, 22 May 2014
          Available: http://doi.ieeecomputersociety.org/10.1109/TPDS.2013.304
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, t_tw=10):
        super(ProbCache, self).__init__(view, controller)
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break
        else:
            # No cache hits, get content from source
            self.controller.get_content(v)
            serving_node = v
        # Return content
        path = list(reversed(self.view.shortest_path(receiver, serving_node)))
        c = len([v for v in path if self.view.has_cache(v)])
        x = 0.0
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]    
            N = sum([self.cache_size[n] for n in path[hop - 1:]
                     if n in self.cache_size])
            if v in self.cache_size:
                x += 1
            self.controller.forward_content_hop(u, v)
            if v != receiver and v in self.cache_size:
                # The (x/c) factor raised to the power of "c" according to the
                # extended version of ProbCache published in IEEE TPDS
                prob_cache = float(N)/(self.t_tw * self.cache_size[v])*(x/c)**c
                if random.random() < prob_cache:
                    self.controller.put_content(v)
        self.controller.end_session()


@register_strategy('CL4M')
class CacheLessForMore(Strategy):
    """Cache less for more strategy [5]_.
    
    References
    ----------
    ..[5] W. Chai, D. He, I. Psaras, G. Pavlou, Cache Less for More in
          Information-centric Networks, in IFIP NETWORKING '12
          Available: http://www.ee.ucl.ac.uk/~uceeips/centrality-networking12.pdf
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, use_ego_betw=False, **kwargs):
        super(CacheLessForMore, self).__init__(view, controller)
        topology = view.topology()
        if use_ego_betw:
            self.betw = dict((v, nx.betweenness_centrality(nx.ego_graph(topology, v))[v])
                             for v in topology.nodes_iter())
        else:
            self.betw = nx.betweenness_centrality(topology)
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        for u, v in path_links(path):
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break
        # No cache hits, get content from source
        else:
            self.controller.get_content(v)
            serving_node = v
        # Return content
        path = list(reversed(self.view.shortest_path(receiver, serving_node)))
        # get the cache with maximum betweenness centrality
        # if there are more than one cache with max betw then pick the one
        # closer to the receiver
        max_betw = -1
        designated_cache = None
        for v in path[1:]:
            if self.view.has_cache(v):
                if self.betw[v] >= max_betw:
                    max_betw = self.betw[v]
                    designated_cache = v
        # Forward content
        for u, v in path_links(path):
            self.controller.forward_content_hop(u, v)
            if v == designated_cache:
                self.controller.put_content(v)
        self.controller.end_session()  
        
@register_strategy('NRR_PROB')
class NearestReplicaRoutingProb(Strategy):
    """Ideal Nearest Replica Routing (NRR) strategy with probabilistic caching.
    
    In this strategy, a request is forwarded to the topologically close node
    holding a copy of the requested item. This strategy is ideal, as it is
    implemented assuming that each node knows the nearest replica of a content
    without any signalling
    
    On the return path, content is cached with probabilistic caching
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, t_tw=10): # Onur default value of metacaching set to LCE
        super(NearestReplicaRoutingProb, self).__init__(view, controller)
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
        
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        locations = self.view.content_locations(content)
        source = self.view.content_source(content)
        if len(locations) > 1:
            locations.remove(source) # Do not go to the source if there is a cached copy!
            nearest_replica = min(locations, key=lambda s: self.view.path_delay(self.view.shortest_path(receiver, s)))
        else:
            nearest_replica = source

        # Route request to nearest replica
        self.controller.start_session(time, receiver, content, log)
        self.controller.forward_request_path(receiver, nearest_replica)
        self.controller.get_content(nearest_replica)
        # Now we need to return packet and we have options
        path = list(reversed(self.view.shortest_path(receiver, nearest_replica)))
        placement = False
        if source == nearest_replica:
            c = len([v for v in path if self.view.has_cache(v)])
            x = 0.0
            for hop in range(1, len(path)):
                u = path[hop - 1]
                v = path[hop]    
                N = sum([self.cache_size[n] for n in path[hop - 1:]
                     if n in self.cache_size])
                if v in self.cache_size:
                    x += 1
                self.controller.forward_content_hop(u, v)
                if not placement:
                    if v != receiver and v in self.cache_size:
                        # The (x/c) factor raised to the power of "c" according to the
                        # extended version of ProbCache published in IEEE TPDS
                        prob_cache = float(N)/(self.t_tw * self.cache_size[v])*(x/c)**c
                        if random.random() < prob_cache:
                            self.controller.put_content(v)
                            placement = True
                        elif hop == (len(path)-1): # force put if it is last hop
                            self.controller.put_content(curr_hop)
                            placement = True
        else:
            for u, v in path_links(path):
                self.controller.forward_content_hop(u, v)

        self.controller.end_session()


@register_strategy('NRR')
class NearestReplicaRouting(Strategy):
    """Ideal Nearest Replica Routing (NRR) strategy.
    
    In this strategy, a request is forwarded to the topologically close node
    holding a copy of the requested item. This strategy is ideal, as it is
    implemented assuming that each node knows the nearest replica of a content
    without any signalling
    
    On the return path, content can be caching according to a variety of
    metacaching policies. LCE and LCD are currently supported.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, metacaching='LCD', **kwargs): # Onur default value of metacaching set to LCE
        super(NearestReplicaRouting, self).__init__(view, controller)
        if metacaching not in ('LCE', 'LCD'):
            raise ValueError("Metacaching policy %s not supported" % metacaching)
        self.metacaching = metacaching
        
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        locations = self.view.content_locations(content)
        nearest_replica = min(locations, 
                              key=lambda s: len(self.view.shortest_path(receiver, s)))
        # Route request to nearest replica
        self.controller.start_session(time, receiver, content, log)
        self.controller.forward_request_path(receiver, nearest_replica)
        self.controller.get_content(nearest_replica)
        # Now we need to return packet and we have options
        path = list(reversed(self.view.shortest_path(receiver, nearest_replica)))
        if self.metacaching == 'LCE':
            for u, v in path_links(path):
                self.controller.forward_content_hop(u, v)
                if self.view.has_cache(v) and not self.view.cache_lookup(v, content):
                    self.controller.put_content(v)
        elif self.metacaching == 'LCD':
            copied = False
            for u, v in path_links(path):
                self.controller.forward_content_hop(u, v)
                if not copied and v != receiver and self.view.has_cache(v):
                    self.controller.put_content(v)
                    copied = True
        else:
            raise ValueError('Metacaching policy %s not supported'
                             % self.metacaching)
        self.controller.end_session()


@register_strategy('RAND_BERNOULLI')
class RandomBernoulli(Strategy):
    """Bernoulli random cache insertion.
    
    In this strategy, a content is randomly inserted in a cache on the path
    from serving node to receiver with probability *p*.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, p=0.2, **kwargs):
        super(RandomBernoulli, self).__init__(view, controller)
        self.p = p
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        for u, v in path_links(path):
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break
        else:
            # No cache hits, get content from source
            self.controller.get_content(v)
            serving_node = v
        # Return content
        path =  list(reversed(self.view.shortest_path(receiver, serving_node)))
        for u, v in path_links(path):
            self.controller.forward_content_hop(u, v)
            if v != receiver and self.view.has_cache(v):
                if random.random() < self.p:
                    self.controller.put_content(v)
        self.controller.end_session()

@register_strategy('RAND_CHOICE')
class RandomChoice(Strategy):
    """Random choice strategy
    
    This strategy stores the served content exactly in one single cache on the
    path from serving node to receiver selected randomly.
    """

    @inheritdoc(Strategy)
    def __init__(self, view, controller, **kwargs):
        super(RandomChoice, self).__init__(view, controller)
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        # get all required data
        source = self.view.content_source(content)
        path = self.view.shortest_path(receiver, source)
        # Route requests to original source and queries caches on the path
        self.controller.start_session(time, receiver, content, log)
        for u, v in path_links(path):
            self.controller.forward_request_hop(u, v)
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break
        else:
            # No cache hits, get content from source
            self.controller.get_content(v)
            serving_node = v
        # Return content
        path =  list(reversed(self.view.shortest_path(receiver, serving_node)))
        caches = [v for v in path[1:-1] if self.view.has_cache(v)]
        designated_cache = random.choice(caches) if len(caches) > 0 else None
        for u, v in path_links(path):
            self.controller.forward_content_hop(u, v)
            if v == designated_cache:
                self.controller.put_content(v)
        self.controller.end_session() 

@register_strategy('NDN_PROB')
class NdnProb(Strategy):
    """NDN strategy with PROB CACHE placement

    """

    def __init__(self, view, controller, t_tw=10):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        """
        super(NdnProb, self).__init__(view, controller)
        #ProbCache related:
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path

        path = self.view.shortest_path(curr_hop, source)
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            serving_node = v
     
        # Return content:
        path = self.view.shortest_path(serving_node, receiver)
        c = len([v for v in path if self.view.has_cache(v)])
        x = 0.0
        placement = False
        for hop in range(1, len(path)):
            prev_hop = path[hop - 1]
            curr_hop = path[hop]
            if not placement:
                N = sum([self.cache_size[n] for n in path[hop - 1:] if n in self.cache_size])
                if curr_hop in self.cache_size:
                    x += 1
                if self.view.has_cache(curr_hop):
                    prob_cache = float(N)/(self.t_tw * self.cache_size[curr_hop])*(x/c)**c
                    if random.random() < prob_cache:
                        self.controller.put_content(curr_hop)
                        placement = True
                    elif hop == (len(path)-1):
                        self.controller.put_content(curr_hop)
                        placement = True
            self.controller.forward_content_hop(prev_hop, curr_hop)

        self.controller.end_session()

@register_strategy('NDN')
class Ndn(Strategy):
    """NDN strategy with shortest path routing and RSN routing up to a
    certain number of detour trails.

    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, p=1.0):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        """
        super(Ndn, self).__init__(view, controller)
        self.p = p
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path

        path = self.view.shortest_path(curr_hop, source)
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    serving_node = v
                    break

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            serving_node = v
     
        # Return content:
        path = self.view.shortest_path(serving_node, receiver)
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            if self.view.has_cache(v):
                if self.p == 1.0 or random.random() <= self.p:
                    self.controller.put_content(v)
            # Insert/update rsn entry
            if self.view.has_rsn_table(u):    
                rsn_entry = self.controller.get_rsn(u)
                rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                rsn_entry.insert_nexthop(v, v, len(path) - hop, time) 
                self.controller.put_rsn(u, rsn_entry)
            self.controller.forward_content_hop(u, v)

        self.controller.end_session()


@register_strategy('LIRA_BC_HYBRID')
class LiraBcHybrid(Strategy):
    """DFIB strategy mixed with BC routing.

       rsn_fresh is a threshold used to identify fresh rsn nexthop entry. When such a fresh entry is found, the algorithm switches to Breadcrumb and 
       "waits" the original request while a copy of the request explores the downstream trail. 
    """

    def __init__(self, view, controller, p=1.0, rsn_fresh=0.0, rsn_timeout=360.0, extra_quota=3, fan_out=2, onpath_hint=False):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        max_detour : int, optional
            The max number of hop that can be performed following an RSN trail
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        rsn_on_evict : bool, optional
            If True content evicted from cache are inserted in the RSN
        """
        super(LiraBcHybrid, self).__init__(view, controller)
        self.p = p
        self.rsn_fresh = rsn_fresh
        self.rsn_timeout = rsn_timeout
        self.extra_quota = extra_quota
        self.fan_out = fan_out
        self.onpath_hint = onpath_hint


    def get_path_delay(path):
        path_delay = 0.0
        for hop in range(1, len(path)):
            u = path[hop-1]
            v = path[hop]
            path_delay += self.view.link_delay(u,v)
        return path_delay

    def lookup_rsn_at_node(self, v):
        rsn_entry = self.controller.get_rsn(v) if self.view.has_rsn_table(v) else None
        return rsn_entry
    
    # *** LIRA_BC_HYBRID ***
    def follow_offpath_trail(self, prev_hop, curr_hop, rsn_hop, fresh_trail, on_path_trail, off_path_trails, source, time):
        off_path_serving_node = None
        trail = [curr_hop]
        # This loop is guaranteed to execute at least once, as rsn_hop is not None
        while rsn_hop is not None:
            prev_hop = curr_hop
            curr_hop = rsn_hop

            if curr_hop in trail:
            # loop in the explored off-path trail
                self.controller.invalidate_trail(trail)
                if  fresh_trail:
                    for hop in range(1, len(trail)):
                        self.controller.forward_request_hop(trail[hop-1], trail[hop])
                    trail.reverse()
                    for hop in range(1, len(trail)):
                        self.controller.forward_request_hop(trail[hop-1], trail[hop])
                
                break

            else:
                trail.append(curr_hop)
                if curr_hop == source or self.view.has_cache(curr_hop):
                    if self.controller.get_content(curr_hop):
                        trail = on_path_trail[:-1] + trail
                        off_path_trails.append(trail)
                        off_path_serving_node = curr_hop
                        break

                rsn_entry = self.lookup_rsn_at_node(curr_hop)
                if rsn_entry is not None:
                    rsn_nexthop_obj = rsn_entry.get_freshest_except_node(time, prev_hop)
                    rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None

                    if not len(rsn_entry.nexthops):
                    # if the rsn entry's nexthops are  expired, remove
                        self.controller.remove_rsn(curr_hop)
                                    
                else:
                    rsn_hop = None
        else: # else of while
        # Onur: if break is executed above, this else is skipped
        # This point is reached when I did explore an RSN
        # trail but failed. 
        # Invalidate the trail here and return to on-path node
            self.controller.invalidate_trail(trail)
            if  fresh_trail:
                for hop in range(1, len(trail)):
                    self.controller.forward_request_hop(trail[hop-1], trail[hop])
                trail.reverse()
                for hop in range(1, len(trail)):
                    self.controller.forward_request_hop(trail[hop-1], trail[hop])
            #TODO if, afer invalidation, there is no nexthop entries
            # then delete the rsn entry
            return None
        
        return off_path_serving_node

    
    # *** LIRA_BC_HYBRID ***
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # Hop counter of RSN routing
        rsn_hop_count = 0
        # Quota used by the packet (flow)
        packet_quota = 0 
        # Are we following a fresh (off-path) trail?
        fresh_trail = False
        # List of trails followed by the successful (off-path) requests, (more than one trails in the case of request multicasting)
        off_path_trails = []
        # On-path trail followed my the main request
        on_path_trail = [curr_hop]

        path = self.view.shortest_path(curr_hop, source)
        # Quota Limit on the request
        quota_limit = len(path) - 1 + self.extra_quota
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            on_path_trail.append(v)
            # self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            packet_quota += 1
            if packet_quota >= quota_limit and v != source:
                # we spent the quota without either reaching the source or finding a cached copy
                break
            rsn_entry = self.lookup_rsn_at_node(v)
            if packet_quota <= quota_limit and rsn_entry is not None and v != source:
                off_path_serving_node = None
                off_path_fresh_trail = False
                next_hop = path[hop + 1]
                rsn_nexthop_objs = rsn_entry.get_best_k_entry(time, u, self.fan_out)
                # if the rsn entry's nexthops are  expired, remove
                if not len(rsn_entry.nexthops):
                    self.controller.remove_rsn(v)
                for rsn_nexthop_obj in rsn_nexthop_objs:
                    rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None
                    if rsn_hop is not None and rsn_hop == next_hop:
                        # we just found an "on-path" hint: continue with the FIB nexthop if hint is "fresh", otherwise explore the next offpath trail
                            continue 
                    elif rsn_hop is not None and packet_quota < quota_limit: 
                    # If entry in RSN table, then start detouring to get cached
                    # content, if any
                        packet_quota += 1
                        fresh_trail = True if rsn_nexthop_obj.is_used_and_fresh(time, self.rsn_fresh) else False
                        prev_hop = u
                        curr_hop = v
                        off_path_serving_node = self.follow_offpath_trail(prev_hop, curr_hop, rsn_hop, fresh_trail, on_path_trail, off_path_trails, source, time)
                        if off_path_serving_node is not None and fresh_trail:
                            off_path_fresh_trail = True
                            break

                if off_path_fresh_trail:
                    # If I hit a content via a fresh off-path trail, I need to break
                    # the for loop,
                    # the on_path_serving_node will be None 
                    break

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v
     
        # Return content: *** LIRA_BC_HYBRID ***
        # Sort return paths by length, TODO replace this by: sort by path latency
        sorted_paths = sorted(off_path_trails, key=len)
        if on_path_serving_node is not None: 
            sorted_paths.append(on_path_trail)
        visited = {} # keep track of the visited nodes to eliminate duplicate data packets arriving at a hop (simulating PIT forwarding)
        first = False
        for path in sorted_paths:
            if not first: # only forward the request of the shortest path
                first = True
                for hop in range(1, len(path)):
                    u = path[hop - 1]
                    v = path[hop]
                    self.controller.forward_request_hop(u, v)
            path.reverse()
            if path[0] == source:
                for hop in range(1, len(path)):
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if visited.get(prev_hop):
                        break
                    visited[prev_hop] = True
                    # Insert/update rsn entry towards the direction of user
                    rsn_entry = self.controller.get_rsn(prev_hop) if self.view.has_rsn_table(prev_hop) else None
                    rsn_entry = RsnEntry(self.rsn_fresh, self.rsn_timeout) if rsn_entry is None else rsn_entry
                    rsn_entry.insert_nexthop(curr_hop, curr_hop, len(path) - hop, time) 
                    self.controller.put_rsn(prev_hop, rsn_entry)
                    # Insert content to cache
                    if self.view.has_cache(curr_hop):
                        if self.p == 1.0 or random.random() <= self.p:
                            self.controller.put_content(curr_hop)
                    # Forward the content
                    self.controller.forward_content_hop(prev_hop, curr_hop)
            else: 
            # Content coming from a cache 
                for hop in range(1, len(path)):
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if visited.get(prev_hop):
                        break
                    visited[prev_hop] = True
                    # Insert/Update the rsn entry towards the direction of cache if such an entry existed (in the case of off-path hit)
                    rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None
                    rsn_entry = RsnEntry(self.rsn_fresh, self.rsn_timeout) if rsn_entry is None else rsn_entry
                    rsn_entry.insert_nexthop(prev_hop, prev_hop, len(path) - hop, time, True)
                    self.controller.put_rsn(curr_hop, rsn_entry)
                    # Forward the content
                    self.controller.forward_content_hop(prev_hop, curr_hop)
        self.controller.end_session()

@register_strategy('LIRA_DFIB_OPH')
class LiraDfibOph(Strategy):
    """DFIB strategy with forwarding budget. A dynamic cost (AIMD-based) mechanism is used to deduct a cost amount for each 
    downstream trail. The run-time of this strategy is higher than the others (LIRA_DFIB_SC), because a linear search is required to 
    determine the rank of a SIT table entry.

    """

    def __init__(self, view, controller, p=1.0, extra_quota=3, fan_out=1, quota_increment=1.0, limit_replica = True):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
               An instance of the network view

        controller : NetworkController
                     An instance of the network controller

        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy

        quota_increment : increment parameter (in AIMD) cost setting. The amount to deduct from the forwarding budget
                          is decided dynamically based on the success of the off-path requests. 

        limit_replica : content placement policy to limit the replicas of items. 

        extra_quota : extra ``forwarding budget'' (beyond what is necessary for the Interest to reach the producer) 
                      to create off-path copies of request.
        """
        super(LiraDfibOph, self).__init__(view, controller)
        self.p = p
        self.fan_out = fan_out
        self.extra_quota = extra_quota
        self.n_requests = 0
        self.first = False
        self.quota_increment = quota_increment
        self.limit_replica = limit_replica

    def get_path_delay(path):
        path_delay = 0.0
        for hop in range(1, len(path)):
            u = path[hop-1]
            v = path[hop]
            path_delay += self.view.link_delay(u,v)
        return path_delay

    def form_key(self, content, node):
        """ form key to lookup content from RSN table
        """
        key = repr(content) + "-" + repr(node)
        return key

    # LIRA_DFIB_OPH
    def lookup_rsn_at_node(self, node, content=None, ignore=[], fan_out=1):
        """lookup the rsn table at node 

        Parameters
        ----------
        node : node id of the node with rsn table
        content : the content id to lookup
        ignore : list of nexthop nodes to ignore
        fan_out : max number of next-hops returned 

        Return
        ------
        A list of rsn entries each represented as a triple; first index is the 
        next-hop node id, second index id the success rate of the entry 
        in the RSN table, third index is the position (i.e., rank) of the entry
        in the RSN table. 
        """
        
        if content is None:
            content = self.controller.session['content']

        neighbors = self.view.get_neighbors(node)
        neighbors = [n for n in neighbors if n not in ignore]
        neighbors = [n for n in neighbors if n not in self.view.topology().sources()]
        neighbors = [n for n in neighbors if n not in self.view.topology().receivers()]
        
        rsn_entries = []
        for n in neighbors:
            key = self.form_key(content, n) #repr(content) + "/" + repr(n)
            nexthop = self.view.peek_rsn(node, key)
            if nexthop is not None:
                if nexthop != n:
                    #print "Current node: " + repr(node) + " neighbor: " + repr(n) + " and nexthop: " + repr(nexthop) + " key: " + repr(key)
                    #print "Neighbors: " + repr(neighbors)
                    raise RuntimeError('This should not happen in lookup_rsn_at_node')
                position = self.view.get_rsn_position(node, key)
                rsn_table = self.view.get_rsn_table(node)
                #n_lookups = rsn_table.get_nlookups()
                #n_success = rsn_table.get_nsuccess()
                n_quotas = rsn_table.get_quota()
                self.controller.get_rsn(node, key) #lookup to change the position now
                success = 0.0
                quota = n_quotas[position]
                rsn_entries.append([nexthop, position, quota])

                """
                if n_lookups[position] < 3: # TODO create a parameter for a threshold
                    dfib_size = rsn_table.get_size()
                    success = 0.0 #(1.0 - ((1.0*position)/dfib_size))
                    rsn_entries.append([nexthop, success, position])
                else:
                    success = (1.0*n_success[position])/n_lookups[position]
                    rsn_entries.append([nexthop, success, position])
                    if not self.first:
                        print "Accumulated enough statistics!"
                        self.first = True
                    #print "Nexthop: " + repr(nexthop) + " pos: " + repr(position) + " succ: " + repr(success)
                """

        # sort the entries by success rate (increasing order -- head is 0 and tail is size-1)
        rsn_entries.sort(key = lambda x : x[1])
        
        return rsn_entries[0:fan_out]
        
    # LIRA_DFIB_OPH
    def invalidate_tr(self, trail, content=None):
        """invalidate trail of DFIB
        """
        #print "invalidating trail " + repr(trail) 
        content = self.controller.session['content'] if content is None else content
        for hop in range(0, len(trail)-1):
            curr_hop = trail[hop]
            next_hop = trail[hop+1]
            if not self.view.has_rsn_table(curr_hop):
                continue
            key = self.form_key(content, next_hop) 
            is_removed = self.controller.remove_rsn(curr_hop, key)
            #print "Removing trail: " + repr(curr_hop) + " -> " + repr(next_hop)
            if is_removed is None:
                print "Error: " + " Trail: " + repr(trail) + " key " + repr(key) + " at node " + repr(curr_hop) + " nexthop " + repr(next_hop)
                print "is_removed: " + repr(is_removed)
                raise RuntimeError('This should not happen in invalidate_tr')
            #else:
            #    print "Trail is removed at node: " + repr(curr_hop)

    # LIRA_DFIB_OPH
    def follow_offpath_trail(self, prev_hop, curr_hop, rsn_hop, on_path_trail, off_path_trails, source, position, quota):
        """ Follow an offpath trail all the way until either you find the content, or 
        arrive at a node with no SIT trail (i.e., dead-end)
        """
        off_path_serving_node = None
        trail = [curr_hop]
        positions = [position]
        # This loop is guaranteed to execute at least once, as rsn_hop is not None
        while rsn_hop is not None:
            prev_hop = curr_hop
            curr_hop = rsn_hop
            if curr_hop in trail:
            # loop in the explored off-path trail
                #print "Loop in the trail, calling invalidate " + repr(trail) + " / " + repr(rsn_hop)
                self.invalidate_tr(trail)
                break
            else:
                trail.append(curr_hop)
                if curr_hop == source or self.view.has_cache(curr_hop):
                    if self.controller.get_content(curr_hop):
                        off_path_serving_node = curr_hop
                        #print "Off path search successful: Found content at node " + repr(off_path_serving_node)
                        break
                
                rsn_entries = self.lookup_rsn_at_node(curr_hop, None, [prev_hop], 1) # returns an array of [[nexthop, position, quota]...]
                if not len(rsn_entries):
                    rsn_hop = None
                else:
                    rsn_entry = rsn_entries[0]
                    positions.append(rsn_entry[1])
                    rsn_hop = rsn_entry[0]
        else: # else of while
        # Onur: if break is executed above, this else is skipped
        # This point is reached when I did explore an RSN
        # trail but failed. 
        # Invalidate the trail here and return to on-path node
            #print "Followed an RSN, but failed: " + repr(trail)
            #print "on-path trail " + repr(on_path_trail)
            self.invalidate_tr(trail)

        indx = 0
        #print "Trail: " + repr(trail) 
        for position in positions:
            rsn = self.view.get_rsn_table(trail[indx])
            #if rsn is None:
                #print "Node: " + repr(trail[indx]) + " has no rsn table "
            n_success = rsn.get_nsuccess()
            n_lookups = rsn.get_nlookups()
            n_quotas = rsn.get_quota()
            if off_path_serving_node is None:
                #n_quotas[position] /= 2
                n_quotas[position] = max(1, n_quotas[position]/2) #XXX Lower bound is 1
                n_lookups[position] += 1
            else:
                n_quotas[position] += self.quota_increment
                n_success[position] += 1
                n_lookups[position] += 1
            indx += 1

        if off_path_serving_node is not None:
            trail = on_path_trail[:-1] + trail
            off_path_trails.append(trail)
            success = True
            self.controller.follow_trail(quota, success)
        else:
            success = False
            self.controller.follow_trail(quota, success)

        return off_path_serving_node

    # LIRA_DFIB_OPH
    def print_quotas(self, num):
        """
        Print the quotas for a router (for debugging purposes)
        """
        topo = self.view.topology()
        routers = [v for v in topo.nodes_iter()
                     if topo.node[v]['stack'][0] == 'router']
        
        fname = "./Data/quota_stats_" + repr(num)
        aFile = open(fname, 'w')
        for v in routers:
            rsn = self.view.get_rsn_table(v)
            n_quotas = rsn.get_quota()
            n_lookups = rsn.get_nlookups()
            n_success = rsn.get_nsuccess()
            size = self.view.model.rsn_size[v]
            num_neighbors = len(self.view.get_neighbors(v))
            s = "Printing rsn table Quotas for " + repr(v) + " with " + repr(num_neighbors) + " neighbors\n"
            aFile.write(s)
            for index in range(0, size):
                s =  "\t" + repr(index) + ": " + repr(n_quotas[index]) + " : " + repr(n_success[index]) + " : " + repr(n_lookups[index]) +  "\n"
                aFile.write(s)

        aFile.close()

    # LIRA_DFIB_OPH
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        """
        if self.n_requests == 0:
            self.print_quotas(0)
        elif self.n_requests == 300000:
            self.print_quotas(1)
        elif self.n_requests == 600000:
            self.print_quotas(2)
        self.n_requests += 1
        """
        #    print "Done with: " + repr(self.n_requests)
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # Hop counter of RSN routing
        rsn_hop_count = 0
        # Quota used by the packet (flow)
        packet_quota = 0 
        # Are we following a fresh (off-path) trail?
        fresh_trail = False
        # List of trails followed by the successful (off-path) requests, (more than one trails in the case of request multicasting)
        off_path_trails = []
        # On-path trail followed my the main request
        on_path_trail = [curr_hop]

        path = self.view.shortest_path(curr_hop, source)
        # Quota Limit on the request
        remaining_quota = len(path) - 1 + self.extra_quota
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            on_path_trail.append(v)
            # self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            remaining_quota-=1.0
            if remaining_quota <= 0 and v != source:
                # we spent the quota without either reaching the source or finding a cached copy
                #print "Out of Quota for content: " + repr(content)
                break

            rsn_entries = self.lookup_rsn_at_node(v, None, [u], self.fan_out)
            #print "Lookup returned: " + repr(len(rsn_entries)) + " entries at node: " + repr(v) + " for content: " + repr(content)
            for rsn_entry in rsn_entries:
                if remaining_quota <= 0:
                    #print "Out of Quota in off-path search for content: " + repr(content)
                    break
                next_hop = path[hop+1]
                rsn_hop = rsn_entry[0]
                position = rsn_entry[1]
                quota = rsn_entry[2]
                if rsn_hop == next_hop:
                    # we just found an "on-path" hint: continue with the FIB nexthop
                    continue
                """
                if success_rate is 0:
                    remaining_quota -= 1
                else:
                    remaining_quota -= remaining_quota*success_rate
                """
                remaining_quota -= quota
                off_path_serving_node = self.follow_offpath_trail(u, v, rsn_hop, on_path_trail, off_path_trails, source, position, quota)

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v
     
        # Return content: 
        # DFIB_OPH
        # Sort return paths by length, TODO replace this by: sort by path latency
        sorted_paths = sorted(off_path_trails, key=len)
        if on_path_serving_node is not None: 
            sorted_paths.append(on_path_trail)
        visited = {} # keep track of the visited nodes to eliminate duplicate data packets arriving at a hop (simulating PIT forwarding)
        first = False
        for path in sorted_paths:
            if not first: # only forward the request of the shortest path
                first = True
                for hop in range(1, len(path)):
                    u = path[hop - 1]
                    v = path[hop]
                    self.controller.forward_request_hop(u, v)
            path.reverse()

            if self.limit_replica:
                if path[0] == source:
                # Content coming from the server (i.e., source)
                # Insert/update rsn entry towards the direction of user
                    for hop in range(2, len(path)-1):
                        curr_hop = path[hop]
                        prev_hop = path[hop-1]
                        if prev_hop in visited.keys() and visited[prev_hop]:
                            break
                        visited[prev_hop] = True
                        key = self.form_key(content, curr_hop)
                        #print "Adding key: " + repr(key) + " @current node: " + repr(prev_hop)
                        self.controller.put_rsn(prev_hop, curr_hop, key)
                        # Insert content to cache
                        if self.view.has_cache(curr_hop):
                            if self.p == 1.0 or random.random() <= self.p:
                                self.controller.put_content(prev_hop)
                        # Forward the content
                        self.controller.forward_content_hop(prev_hop, curr_hop)
                else:
                # Content coming from a cache 
                # Insert/Update the rsn entry towards the direction of cache if such an entry existed (in the case of off-path hit)
                    for hop in range(1, len(path)-1):
                        curr_hop = path[hop]
                        prev_hop = path[hop-1]
                        if prev_hop in visited.keys() and visited[prev_hop]:
                            break
                        visited[prev_hop] = True
                        key = self.form_key(content, prev_hop)
                        #print "Adding key: " + repr(key) + " @current node: " + repr(curr_hop)
                        self.controller.put_rsn(curr_hop, prev_hop, key)
                        # Forward the content
                        self.controller.forward_content_hop(prev_hop, curr_hop)
            else: # not limiting replicas of content
                for hop in range(1, len(path)-1):
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if prev_hop in visited.keys() and visited[prev_hop]:
                        break
                    visited[prev_hop] = True
                    key = self.form_key(content, prev_hop)
                    #print "Adding key: " + repr(key) + " @current node: " + repr(curr_hop)
                    self.controller.put_rsn(curr_hop, prev_hop, key)
                    # Forward the content
                    self.controller.forward_content_hop(prev_hop, curr_hop)
        
        self.controller.end_session()

# LANMAN:
@register_strategy('LIRA_DFIB')
class LiraDfib(Strategy):
    """LIRA strategy with shortest path routing and RSN routing up to a
    certain number of detour trails.

    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, p=1.0, rsn_fresh=0.0, rsn_timeout=float('inf'), extra_quota=3, fan_out=1):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        max_detour : int, optional
            The max number of hop that can be performed following an RSN trail
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        rsn_on_evict : bool, optional
            If True content evicted from cache are inserted in the RSN
        """
        super(LiraDfib, self).__init__(view, controller)
        self.p = p
        self.rsn_fresh = rsn_fresh
        self.rsn_timeout = rsn_timeout
        self.extra_quota = extra_quota
        self.fan_out = fan_out

    def get_path_delay(path):
        path_delay = 0.0
        for hop in range(1, len(path)):
            u = path[hop-1]
            v = path[hop]
            path_delay += self.view.link_delay(u,v)
        return path_delay
    # LIRA_DFIB
    def lookup_rsn_at_node(self, v):
        rsn_entry = self.controller.get_rsn(v) if self.view.has_rsn_table(v) else None
        return rsn_entry
        
    def follow_offpath_trail(self, prev_hop, curr_hop, rsn_hop, on_path_trail, off_path_trails, source, time):
        off_path_serving_node = None
        trail = [curr_hop]
        # This loop is guaranteed to execute at least once, as rsn_hop is not None
        while rsn_hop is not None:
            prev_hop = curr_hop
            curr_hop = rsn_hop

            if curr_hop in trail:
            # loop in the explored off-path trail
                print "Loop in the explored off-path trail"
                self.controller.invalidate_trail(trail)
                break

            else:
                trail.append(curr_hop)
                if curr_hop == source or self.view.has_cache(curr_hop):
                    if self.controller.get_content(curr_hop):
                        trail = on_path_trail[:-1] + trail
                        off_path_trails.append(trail)
                        off_path_serving_node = curr_hop
                        break

                rsn_entry = self.lookup_rsn_at_node(curr_hop)
                if rsn_entry is not None:
                    rsn_nexthop_obj = rsn_entry.get_freshest_except_node(time, prev_hop)
                    rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None

                    if not len(rsn_entry.nexthops):
                    # if the rsn entry's nexthops are  expired, remove
                        self.controller.remove_rsn(curr_hop)
                                    
                else:
                    rsn_hop = None
        else: # else of while
        # Onur: if break is executed above, this else is skipped
        # This point is reached when I did explore an RSN
        # trail but failed. 
        # Invalidate the trail here and return to on-path node
            self.controller.invalidate_trail(trail)
            #TODO if, afer invalidation, there is no nexthop entries
            # then delete the rsn entry
            return None
        
        if off_path_serving_node is not None:
            success = True
            self.controller.follow_trail(1, success)
        else:
            success = False
            self.controller.follow_trail(1, success)

        return off_path_serving_node

    #LIRA_DFIB
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # Hop counter of RSN routing
        rsn_hop_count = 0
        # Quota used by the packet (flow)
        packet_quota = 0 
        # Are we following a fresh (off-path) trail?
        fresh_trail = False
        # List of trails followed by the successful (off-path) requests, (more than one trails in the case of request multicasting)
        off_path_trails = []
        # On-path trail followed my the main request
        on_path_trail = [curr_hop]

        path = self.view.shortest_path(curr_hop, source)
        # Quota Limit on the request
        quota_limit = len(path) - 1 + self.extra_quota
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            on_path_trail.append(v)
            # self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            packet_quota += 1
            if packet_quota >= quota_limit and v != source:
                # we spent the quota without either reaching the source or finding a cached copy
                break
            rsn_entry = self.lookup_rsn_at_node(v)
            if packet_quota <= quota_limit and rsn_entry is not None and v != source:
                off_path_serving_node = None
                next_hop = path[hop + 1]
                rsn_nexthop_objs = rsn_entry.get_topk_freshest_except_node(time, u, self.fan_out)
                # if the rsn entry's nexthops are  expired, remove
                if not len(rsn_entry.nexthops):
                    self.controller.remove_rsn(v)
                for rsn_nexthop_obj in rsn_nexthop_objs:
                    rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None
                    if rsn_hop is not None and rsn_hop == next_hop:
                        continue 
                    # TODO: Check if distance to off-path cache is closer than source
                
                    elif rsn_hop is not None and packet_quota < quota_limit: 
                    # If entry in RSN table, then start detouring to get cached
                    # content, if any
                        packet_quota += 1
                        prev_hop = u
                        curr_hop = v
                        
                        off_path_serving_node = self.follow_offpath_trail(prev_hop, curr_hop, rsn_hop, on_path_trail, off_path_trails, source, time)

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v
     
        # LIRA_DFIB
        # Return content: 
        # Sort return paths by length, TODO replace this by: sort by path latency
        sorted_paths = sorted(off_path_trails, key=len)
        if on_path_serving_node is not None: 
            sorted_paths.append(on_path_trail)
        visited = {} # keep track of the visited nodes to eliminate duplicate data packets arriving at a hop (simulating PIT forwarding)
        first = False
        for path in sorted_paths:
            if not first: # only forward the request of the shortest path
                first = True
                for hop in range(1, len(path)):
                    u = path[hop - 1]
                    v = path[hop]
                    self.controller.forward_request_hop(u, v)
            path.reverse()
            for hop in range(1, len(path)):
                curr_hop = path[hop]
                prev_hop = path[hop-1]
                if visited.get(prev_hop):
                    break
                visited[prev_hop] = True
                # Insert/update rsn entry towards the direction of user
                rsn_entry = self.controller.get_rsn(prev_hop) if self.view.has_rsn_table(prev_hop) else None
                rsn_entry = RsnEntry(self.rsn_fresh, self.rsn_timeout) if rsn_entry is None else rsn_entry
                rsn_entry.insert_nexthop(curr_hop, curr_hop, len(path) - hop, time) 
                self.controller.put_rsn(prev_hop, rsn_entry)
                # Update the rsn entry towards the direction of cache if such an entry existed (in the case of off-path hit)
                rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None
                if rsn_entry is not None and rsn_entry.get_nexthop(prev_hop) is not None:
                    rsn_entry.insert_nexthop(prev_hop, prev_hop, len(path) - hop, time)
                # Insert content to cache
                if self.view.has_cache(curr_hop):
                    if self.p == 1.0 or random.random() <= self.p:
                        self.controller.put_content(curr_hop)
                # Forward the content
                self.controller.forward_content_hop(prev_hop, curr_hop)
        """
        # Add on-path hint
        if on_path_serving_node is not None and self.onpath_hint:
            path = self.view.shortest_path(on_path_serving_node, receiver)
            freshness = float('inf')
            distance = 1
            for hop in range(1, len(path)):
                curr_hop = path[hop]
                prev_hop = path[hop-1]
                rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None
                if freshness < float('inf') and rsn_entry is not None:
                    rsn_entry.insert_nexthop(prev_hop, prev_hop, distance, time)
                elif freshness < float('inf') and rsn_entry is None:
                    rsn_entry = RsnEntry(self.rsn_fresh, self.rsn_timeout) if rsn_entry is None else rsn_entry
                    rsn_entry.insert_nexthop(prev_hop, prev_hop, distance, time)
                rsn_nexthop_obj = None
                if rsn_entry is not None and curr_hop is not receiver:
                    next_hop = path[hop+1]
                    rsn_nexthop_obj = rsn_entry.get_freshest_except_nodes(time, [prev_hop, next_hop]) 
                if rsn_nexthop_obj is not None and rsn_nexthop_obj.age(time) < freshness:
                    freshness = rsn_nexthop_obj.age(time)
                    distance = 1
                else:
                    distance += 1
        """
        self.controller.end_session()

@register_strategy('LIRA_BC') # Breadcrumb strategy
class LiraBC(Strategy):
    """LIRA strategy with shortest path routing and RSN routing up to a
    certain number of detour trails.

    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, p=1.0):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        """
        super(LiraBC, self).__init__(view, controller)
        self.p = p
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # off-path trail followed by the breadcrumb
        off_path_trail = None

        path = self.view.shortest_path(curr_hop, source)
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            rsn_entry = self.controller.get_rsn(v) if self.view.has_rsn_table(v) else None
            if rsn_entry is not None and v != source:
                next_hop = path[hop + 1]
                rsn_nexthop_obj = rsn_entry.get_freshest_except_nodes(time, [u, next_hop])
                rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None
                # TODO: Check if distance to off-path cache is closer than source
                
                if rsn_hop is not None:
                    # If entry in RSN table, then start detouring to get cached
                    # content, if any
                    prev_hop = u
                    curr_hop = v
                    trail = [curr_hop] # store the explored trail to detect looping and invalidate in case it leads to no where
                
                    while rsn_hop is not None:
                        self.controller.forward_request_hop(curr_hop, rsn_hop)
                        prev_hop = curr_hop
                        curr_hop = rsn_hop

                        if rsn_hop in trail:
                            # loop in the explored off-path trail
                            break

                        else:
                            trail.append(curr_hop)
                            if curr_hop == source or self.view.has_cache(curr_hop):
                                if self.controller.get_content(curr_hop):
                                    off_path_serving_node = curr_hop
                                    off_path_trail = trail
                                    break

                            rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None

                            if rsn_entry is not None:
                                rsn_nexthop_obj = rsn_entry.get_freshest_except_node(time, prev_hop)
                                rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None
                            else:
                                rsn_hop = None

                    else: # else of while
                        # Onur: if break is executed in the while loop, this else is skipped
                        # This point is reached when I did explore an RSN
                        # trail but failed. 
                        # Invalidate the trail here and return to on-path node
                        self.controller.invalidate_trail(trail)
                        # travel the reverse path of the trail
                        trail.reverse()
                        for hop in range(1, len(trail)):
                            self.controller.forward_request_hop(trail[hop-1], trail[hop])
                        #TODO if, afer invalidation, there is no nexthop entries
                        # then delete the rsn entry

                if off_path_serving_node is not None:
                    # If I hit a content via a fresh off-path trail, I need to break
                    # the for loop,
                    # the on_path_serving_node will be None 
                    break

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v
        
        if off_path_serving_node is None:
            success = False
            self.controller.follow_trail(0, success)
        else:
            success = True
            self.controller.follow_trail(0, success)

        # Return content:
        # if on_path_serving_node is not None, then follow the reverse of on-path
        if on_path_serving_node is not None:
            path = list(reversed(self.view.shortest_path(receiver, on_path_serving_node)))
            for hop in range(1, len(path)):
                curr_hop = path[hop]
                prev_hop = path[hop-1]
                # Insert/update rsn entry
                rsn_entry = self.controller.get_rsn(prev_hop) if self.view.has_rsn_table(prev_hop) else None
                rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                rsn_entry.insert_nexthop(curr_hop, curr_hop, len(path) - hop, time) 
                self.controller.put_rsn(prev_hop, rsn_entry)
                # TODO: Propagate freshest on-path hints towards receiver

                # Insert content to cache
                if self.view.has_cache(curr_hop):
                    if self.p == 1.0 or random.random() <= self.p:
                        self.controller.put_content(curr_hop)
                # Forward the content
                self.controller.forward_content_hop(prev_hop, curr_hop)

        elif off_path_trail is not None:
            distance = 0
            for hop in range(len(off_path_trail)-1, 0, -1):
                distance += 1
                curr_hop = trail[hop]
                prev_hop = trail[hop-1]
                # Insert/update rsn entry
                  # First "refresh" the DFIB entry which was used to forward the request to the off-path cache 
                rsn_entry = self.controller.get_rsn(prev_hop) if self.view.has_rsn_table(prev_hop) else None
                rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                rsn_entry.insert_nexthop(curr_hop, trail[len(trail)-1], distance, time) 
                self.controller.put_rsn(prev_hop, rsn_entry)
                  # insert or update the DFIB entry pointing towards where the data is being forwarded
                rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None
                rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                rsn_entry.insert_nexthop(prev_hop, trail[0], len(trail), time) 
                self.controller.put_rsn(curr_hop, rsn_entry)
                self.controller.forward_content_hop(curr_hop, prev_hop)
                # Insert content to cache
                if self.view.has_cache(prev_hop):
                    if self.p == 1.0 or random.random() <= self.p:
                        self.controller.put_content(prev_hop)
            
            on_path_serving_node = off_path_trail[0]
            path = list(reversed(self.view.shortest_path(receiver, on_path_serving_node)))
            for hop in range(1, len(path)):
                curr_hop = path[hop]
                prev_hop = path[hop-1]
                
                # Insert content to cache
                if self.view.has_cache(curr_hop):
                    if self.p == 1.0 or random.random() <= self.p:
                        self.controller.put_content(prev_hop)
                # Forward the content
                self.controller.forward_content_hop(prev_hop, curr_hop)


        self.controller.end_session()

@register_strategy('LIRA_LCE')
class LiraLce(Strategy):
    """LIRA strategy with shortest path routing and RSN routing up to a
    certain number of detoured hops.
    
    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, max_detour=3, p=1.0, rsn_on_evict=True):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        max_detour : int, optional
            The max number of hop that can be performed following an RSN trail
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        rsn_on_evict : bool, optional
            If True content evicted from cache are inserted in the RSN
        """
        super(LiraLce, self).__init__(view, controller)
        self.max_detour = max_detour
        self.p = p
        self.rsn_on_evict = rsn_on_evict
        if rsn_on_evict:
            self.next_hop = collections.defaultdict(dict)
        self.count = 0
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content
        serving_node = None
        # Flag indicating if RSN-based routing is allowed
        rsn_routing = True
        # Hop counter of RSN routing
        rsn_hop_count = 0

        # Handle request        
        # Route requests to original source and queries caches on the path
        while serving_node is None:
            path = self.view.shortest_path(curr_hop, source)
            for hop in range(1, len(path)):
                u = path[hop - 1]
                v = path[hop]
                self.controller.forward_request_hop(u, v)
                if self.view.has_cache(v):
                    if self.controller.get_content(v):
                        serving_node = v
                        break
                if rsn_routing and self.view.has_rsn_table(v):
                    rsn_hop = self.controller.get_rsn(v)
                    next_hop = path[hop + 1]
                    if rsn_hop is not None and rsn_hop != next_hop:
                        # If entry in RSN table, then start detouring to get cached
                        # content, if any
                        prev_hop = u
                        curr_hop = v
                        while rsn_hop is not None:
                            if  rsn_hop == prev_hop:
                                # If RSN is pointing to the direction I am coming
                                # I would be better off removing the entry because
                                # clearly is broken
                                self.controller.remove_rsn(rsn_hop)
                                rsn_hop = None
                                continue
                            if rsn_hop_count >= self.max_detour:
                                # This actions, instead of breaking, exits the
                                # while loop and enter the else block, which
                                # handles the situation
                                rsn_hop = None
                                continue
                            self.controller.forward_request_hop(curr_hop, rsn_hop)
                            rsn_hop_count += 1
                            prev_hop = curr_hop
                            curr_hop = rsn_hop
                            rsn_routing = False
                            if curr_hop == source or self.view.has_cache(curr_hop):
                                if self.controller.get_content(curr_hop):
                                    serving_node = curr_hop
                                    break
                            if self.view.has_rsn_table(curr_hop):
                                rsn_hop = self.controller.get_rsn(curr_hop)
                            else:
                                rsn_hop = None
                        else: 
                            # This point is reached when I did explore an RSN
                            # trail but failed. I now need to break the for and
                            # reroute to source from a different path
                            # However, this else is entered also when while is not
                            # executed at all, so I need another condition to
                            # separate the cases
                            if curr_hop != v:
                                break
                    if serving_node is not None:
                        # If I hit a content via RSN routing, I need to break
                        # the for loop, the outter while will also exit because
                        # serving_node is not None 
                        break
            else: # for concluded without break. Get content from source
                self.controller.get_content(v)
                serving_node = v
        else:
            # Should never get here unless there is a routing failure and 
            # you don't reach a serving node
            pass
     
        # Return content
        path = self.view.shortest_path(serving_node, receiver)
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            if u == serving_node and self.view.has_rsn_table(u) and self.rsn_on_evict:
                self.next_hop[u][content] = v
            self.controller.forward_content_hop(u, v)
            if v != receiver:
                next_hop = path[hop + 1]
                cache_inserted = False      # Flag marking if content is inserted
                cache_evicted = None        # Flag marking what content cache evicted, if any
                if self.view.has_cache(v):
                    if self.p == 1.0 or random.random() <= self.p:
                        cache_inserted = True
                        cache_evicted = self.controller.put_content(v)
                if self.view.has_rsn_table(v):
                    # if inserted and node also has RNS, signal where it went
                    if cache_inserted:
                        if self.controller.get_rsn(v) is not None:
                            self.controller.remove_rsn(v)
                        if self.rsn_on_evict:
                            self.next_hop[v][content] = next_hop
                    # If not inserted in the cache, then put it in the RSN instead
                    else:
                        self.controller.put_rsn(v, next_hop)
                    # Instead, if you put it in the cache and RSN on evict is enabled
                    # and you evicted a content, then put this evicted one in the RSN 
                    if self.rsn_on_evict and cache_evicted is not None:
                        self.controller.put_rsn(node=v, 
                                                next_hop=self.next_hop[v].pop(cache_evicted),
                                                content=cache_evicted)
        self.controller.end_session()


@register_strategy('LIRA_CHOICE')
class LiraChoice(Strategy):
    """COMIT strategy with shortest path routing and RSN routing up to a
    certain number of detoured hops.
    
    Contents are cached only in 1 randomly selected node on the delivery path.
    
    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, max_detour=3, rsn_on_evict=True):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        max_detour : int, optional
            The max number of hop that can be performed following an RSN trail
        rsn_on_evict : bool, optional
            If True content evicted from cache are inserted in the RSN
        """
        super(LiraChoice, self).__init__(view, controller)
        self.max_detour = max_detour
        self.rsn_on_evict = rsn_on_evict
        if rsn_on_evict:
            self.next_hop = collections.defaultdict(dict)
        self.count = 0
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content
        serving_node = None
        # Flag indicating if RSN-based routing is allowed
        rsn_routing = True
        # Hop counter of RSN routing
        rsn_hop_count = 0

        # Handle request        
        # Route requests to original source and queries caches on the path
        while serving_node is None:
            path = self.view.shortest_path(curr_hop, source)
            for hop in range(1, len(path)):
                u = path[hop - 1]
                v = path[hop]
                self.controller.forward_request_hop(u, v)
                if self.view.has_cache(v):
                    if self.controller.get_content(v):
                        serving_node = v
                        break
                if rsn_routing and self.view.has_rsn_table(v):
                    rsn_hop = self.controller.get_rsn(v)
                    next_hop = path[hop + 1]
                    if rsn_hop is not None and rsn_hop != next_hop:
                        # If entry in RSN table, then start detouring to get cached
                        # content, if any
                        prev_hop = u
                        curr_hop = v
                        while rsn_hop is not None:
                            if  rsn_hop == prev_hop:
                                # If RSN is pointing to the direction I am coming
                                # I would be better off removing the entry because
                                # clearly is broken
                                self.controller.remove_rsn(rsn_hop)
                                rsn_hop = None
                                continue
                            if rsn_hop_count >= self.max_detour:
                                # This actions, instead of breaking, exits the
                                # while loop and enter the else block, which
                                # handles the situation
                                rsn_hop = None
                                continue
                            self.controller.forward_request_hop(curr_hop, rsn_hop)
                            rsn_hop_count += 1
                            prev_hop = curr_hop
                            curr_hop = rsn_hop
                            rsn_routing = False
                            if curr_hop == source or self.view.has_cache(curr_hop):
                                if self.controller.get_content(curr_hop):
                                    serving_node = curr_hop
                                    break
                            if self.view.has_rsn_table(curr_hop):
                                rsn_hop = self.controller.get_rsn(curr_hop)
                            else:
                                rsn_hop = None
                        else: 
                            # This point is reached when I did explore an RSN
                            # trail but failed. I now need to break the for and
                            # reroute to source from a different path
                            # However, this else is entered also when while is not
                            # executed at all, so I need another condition to
                            # separate the cases
                            if curr_hop != v:
                                break
                    if serving_node is not None:
                        # If I hit a content via RSN routing, I need to break
                        # the for loop, the outter while will also exit because
                        # serving_node is not None 
                        break
            else: # for concluded without break. Get content from source
                self.controller.get_content(v)
                serving_node = v
        else:
            # Should never get here unless there is a routing failure and 
            # you don't reach a serving node
            pass
     
        # Return content
        path = self.view.shortest_path(serving_node, receiver)
        caches = [v for v in path[1:-1] if self.view.has_cache(v)]
        designated_cache = random.choice(caches) if len(caches) > 0 else None
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            if u == serving_node and self.view.has_rsn_table(u) and self.rsn_on_evict:
                self.next_hop[u][content] = v
            self.controller.forward_content_hop(u, v)
            if v != receiver:
                next_hop = path[hop + 1]
                cache_inserted = False      # Flag marking if content is inserted
                cache_evicted = None        # Flag marking what content cache evicted, if any
                if self.view.has_cache(v):
                    if v == designated_cache:
                        cache_inserted = True
                        cache_evicted = self.controller.put_content(v)
                if self.view.has_rsn_table(v):
                    # if inserted and node also has RNS, signal where it went
                    if cache_inserted:
                        if self.controller.get_rsn(v) is not None:
                            self.controller.remove_rsn(v)
                        if self.rsn_on_evict:
                            self.next_hop[v][content] = next_hop
                    # If not inserted in the cache, then put it in the RSN instead
                    else:
                        self.controller.put_rsn(v, next_hop)
                    # Instead, if you put it in the cache and RSN on evict is enabled
                    # and you evicted a content, then put this evicted one in the RSN 
                    if self.rsn_on_evict and cache_evicted is not None:
                        self.controller.put_rsn(node=v, 
                                                next_hop=self.next_hop[v].pop(cache_evicted),
                                                content=cache_evicted)
        self.controller.end_session()
        

@register_strategy('LIRA_PROB_CACHE')
class LiraProbCache(Strategy):
    """COMIT strategy with shortest path routing and RSN routing up to a
    certain number of detoured hops.
    
    This strategy stores contents randomly on the delivery path according to
    the ProbCache strategy. 
    
    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, max_detour=3, t_tw=10, rsn_on_evict=True):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        max_detour : int, optional
            The max number of hop that can be performed following an RSN trail
        t_tw : float, optional
            The ProbCache t_tw parameter
        rsn_on_evict : bool, optional
            If True content evicted from cache are inserted in the RSN
        """
        super(LiraProbCache, self).__init__(view, controller)
        self.max_detour = max_detour
        self.rsn_on_evict = rsn_on_evict
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
        if rsn_on_evict:
            self.next_hop = collections.defaultdict(dict)
        self.count = 0
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content
        serving_node = None
        # Flag indicating if RSN-based routing is allowed
        rsn_routing = True
        # Hop counter of RSN routing
        rsn_hop_count = 0

        # Handle request        
        # Route requests to original source and queries caches on the path
        while serving_node is None:
            path = self.view.shortest_path(curr_hop, source)
            for hop in range(1, len(path)):
                u = path[hop - 1]
                v = path[hop]
                self.controller.forward_request_hop(u, v)
                if self.view.has_cache(v):
                    if self.controller.get_content(v):
                        serving_node = v
                        break
                if rsn_routing and self.view.has_rsn_table(v):
                    rsn_hop = self.controller.get_rsn(v)
                    next_hop = path[hop + 1]
                    if rsn_hop is not None and rsn_hop != next_hop:
                        # If entry in RSN table, then start detouring to get cached
                        # content, if any
                        prev_hop = u
                        curr_hop = v
                        while rsn_hop is not None:
                            if  rsn_hop == prev_hop:
                                # If RSN is pointing to the direction I am coming
                                # I would be better off removing the entry because
                                # clearly is broken
                                self.controller.remove_rsn(rsn_hop)
                                rsn_hop = None
                                continue
                            if rsn_hop_count >= self.max_detour:
                                # This actions, instead of breaking, exits the
                                # while loop and enter the else block, which
                                # handles the situation
                                rsn_hop = None
                                continue
                            self.controller.forward_request_hop(curr_hop, rsn_hop)
                            rsn_hop_count += 1
                            prev_hop = curr_hop
                            curr_hop = rsn_hop
                            rsn_routing = False
                            if curr_hop == source or self.view.has_cache(curr_hop):
                                if self.controller.get_content(curr_hop):
                                    serving_node = curr_hop
                                    break
                            if self.view.has_rsn_table(curr_hop):
                                rsn_hop = self.controller.get_rsn(curr_hop)
                            else:
                                rsn_hop = None
                        else: 
                            # This point is reached when I did explore an RSN
                            # trail but failed. I now need to break the for and
                            # reroute to source from a different path
                            # However, this else is entered also when while is not
                            # executed at all, so I need another condition to
                            # separate the cases
                            if curr_hop != v:
                                break
                    if serving_node is not None:
                        # If I hit a content via RSN routing, I need to break
                        # the for loop, the outter while will also exit because
                        # serving_node is not None 
                        break
            else: # for concluded without break. Get content from source
                self.controller.get_content(v)
                serving_node = v
        else:
            # Should never get here unless there is a routing failure and 
            # you don't reach a serving node
            pass
     
        # Return content
        path = self.view.shortest_path(serving_node, receiver)
        c = len([v for v in path if self.view.has_cache(v)])
        x = 0.0
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            if u == serving_node and self.view.has_rsn_table(u) and self.rsn_on_evict:
                self.next_hop[u][content] = v
            self.controller.forward_content_hop(u, v)
            if v != receiver:
                next_hop = path[hop + 1]
                cache_inserted = False      # Flag marking if content is inserted
                cache_evicted = None        # Flag marking what content cache evicted, if any
                if self.view.has_cache(v):
                    N = sum([self.cache_size[n] for n in path[hop - 1:] if n in self.cache_size])
                    if v in self.cache_size:
                        x += 1
                    prob_cache = float(N)/(self.t_tw * self.cache_size[v])*(x/c)**c
                    if random.random() < prob_cache:
                        cache_inserted = True
                        cache_evicted = self.controller.put_content(v)
                if self.view.has_rsn_table(v):
                    # if inserted and node also has RNS, signal where it went
                    if cache_inserted:
                        if self.controller.get_rsn(v) is not None:
                            self.controller.remove_rsn(v)
                        if self.rsn_on_evict:
                            self.next_hop[v][content] = next_hop
                    # If not inserted in the cache, then put it in the RSN instead
                    else:
                        self.controller.put_rsn(v, next_hop)
                    # Instead, if you put it in the cache and RSN on evict is enabled
                    # and you evicted a content, then put this evicted one in the RSN 
                    if self.rsn_on_evict and cache_evicted is not None:
                        self.controller.put_rsn(node=v, 
                                                next_hop=self.next_hop[v].pop(cache_evicted),
                                                content=cache_evicted)
        self.controller.end_session()


@register_strategy('TFIB_SC')
class Tfib_sc(Strategy):
    """
    Strategy using forwarding budget but trails pointing to caches, not users.

    Content placement is done using a ProbCache-like approach with an upper-bound
    on how many times a content can be cached on the return path.
    """

    # T-FIB-SC
    def __init__(self, view, controller, extra_quota=3, fan_out=1, t_tw=10, quota_increment=1.0):
        """Constructor
        """
        super(Tfib_sc, self).__init__(view, controller)
        #ProbCache related:
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
        #Strategy related:
        self.fan_out = fan_out
        self.extra_quota = extra_quota
        self.quota_increment = quota_increment

    # T-FIB-SC
    def form_key(self, content, node):
        """ form key to lookup content from RSN table
        """
        key = repr(content) + "-" + repr(node)
        return key
    
    # T-FIB-SC
    def lookup_rsn_at_node(self, node, content=None, ignore=[], fan_out=1):
        """lookup the rsn table at node 

        Parameters
        ----------
        node : node id of the node with rsn table
        content : the content id to lookup
        ignore : list of nexthop nodes to ignore
        fan_out : max number of next-hops returned 

        Return
        ------
        A list of rsn entries each represented as a triple; first index is the 
        next-hop node id, second index id the success rate of the entry 
        in the RSN table, third index is the position (i.e., rank) of the entry
        in the RSN table. 
        """
        
        if content is None:
            content = self.controller.session['content']

        neighbors = self.view.get_neighbors(node)
        neighbors = [n for n in neighbors if n not in ignore]
        neighbors = [n for n in neighbors if n not in self.view.topology().sources()]
        neighbors = [n for n in neighbors if n not in self.view.topology().receivers()]
        
        rsn_entries = []
        for n in neighbors:
            key = self.form_key(content, n) #repr(content) + "/" + repr(n)
            nexthop = self.view.peek_rsn(node, key)
            if nexthop is not None:
                if nexthop != n:
                    #print "Current node: " + repr(node) + " neighbor: " + repr(n) + " and nexthop: " + repr(nexthop) + " key: " + repr(key)
                    #print "Neighbors: " + repr(neighbors)
                    raise RuntimeError('This should not happen in lookup_rsn_at_node')
                #position = self.view.get_rsn_position(node, key)
                position = 0
                rsn_table = self.view.get_rsn_table(node)
                #n_lookups = rsn_table.get_nlookups()
                #n_success = rsn_table.get_nsuccess()
                #n_quotas = rsn_table.get_quota()
                self.controller.get_rsn(node, key) #lookup to change the position now
                success = 0.0
                rsn_entries.append([nexthop, position, 1])
                """
                if n_lookups[position] < 3: # TODO create a parameter for a threshold
                    dfib_size = rsn_table.get_size()
                    success = 0.0 #(1.0 - ((1.0*position)/dfib_size))
                    rsn_entries.append([nexthop, success, position])
                else:
                    success = (1.0*n_success[position])/n_lookups[position]
                    rsn_entries.append([nexthop, success, position])
                    if not self.first:
                        print "Accumulated enough statistics!"
                        self.first = True
                    #print "Nexthop: " + repr(nexthop) + " pos: " + repr(position) + " succ: " + repr(success)
                """

        # sort the entries by success rate (increasing order -- head is 0 tail is size-1)
        rsn_entries.sort(key = lambda x : x[1])
        
        return rsn_entries[0:fan_out]

    # T-FIB-SC
    def invalidate_tr(self, trail, content=None):
        """invalidate trail of DFIB
        """
        #print "invalidating trail " + repr(trail) 
        content = self.controller.session['content'] if content is None else content
        for hop in range(0, len(trail)-1):
            curr_hop = trail[hop]
            next_hop = trail[hop+1]
            if not self.view.has_rsn_table(curr_hop):
                continue
            key = self.form_key(content, next_hop) 
            is_removed = self.controller.remove_rsn(curr_hop, key)
            #print "Removing trail: " + repr(curr_hop) + " -> " + repr(next_hop)
            if is_removed is None:
                print "Error: " + " Trail: " + repr(trail) + " key " + repr(key) + " at node " + repr(curr_hop) + " nexthop " + repr(next_hop)
                print "is_removed: " + repr(is_removed)
                raise RuntimeError('This should not happen in invalidate_tr')

    # T-FIB-SC
    def follow_offpath_trail(self, prev_hop, curr_hop, rsn_hop, on_path_trail, off_path_trails, source, position, quota):
        """ Follow an offpath trail all the way until either you find the content, or 
        arrive at a node with no SIT trail (i.e., dead-end)
        """
        off_path_serving_node = None
        trail = [curr_hop]
        positions = [position]
        # This loop is guaranteed to execute at least once, as rsn_hop is not None
        while rsn_hop is not None:
            prev_hop = curr_hop
            curr_hop = rsn_hop
            self.controller.forward_off_path_request_hop(prev_hop, curr_hop)
            if curr_hop in trail:
            # loop in the explored off-path trail
                #print "Loop in the trail, calling invalidate " + repr(trail) + " / " + repr(rsn_hop)
                self.invalidate_tr(trail)
                break
            else:
                trail.append(curr_hop)
                if curr_hop == source or self.view.has_cache(curr_hop):
                    if self.controller.get_content(curr_hop):
                        off_path_serving_node = curr_hop
                        #print "Off path search successful: Found content at node " + repr(off_path_serving_node)
                        break
                
                rsn_entries = self.lookup_rsn_at_node(curr_hop, None, [prev_hop], 1) # returns an array of [[nexthop, position, quota]...]
                if not len(rsn_entries):
                    rsn_hop = None
                else:
                    rsn_entry = rsn_entries[0]
                    positions.append(rsn_entry[1])
                    rsn_hop = rsn_entry[0]
        else: # else of while
        # Onur: if break is executed above, this else is skipped
        # This point is reached when I did explore an RSN
        # trail but failed. 
        # Invalidate the trail here and return to on-path node
            self.invalidate_tr(trail)

        """
        indx = 0
        for position in positions:
            rsn = self.view.get_rsn_table(trail[indx])
            n_quotas = rsn.get_quota()
            if off_path_serving_node is None:
                #n_quotas[position] /= 2
                n_quotas[position] = max(1, n_quotas[position]/2) #XXX Lower bound is 1
            else:
                n_quotas[position] += self.quota_increment
            indx += 1

        if off_path_serving_node is not None:
            trail = on_path_trail[:-1] + trail
            off_path_trails.append(trail)
            success = True
            self.controller.follow_trail(quota, success)
        else:
            success = False
            self.controller.follow_trail(quota, success)
        """
        if off_path_serving_node is not None:
            trail = on_path_trail[:-1] + trail
            off_path_trails.append(trail)
            success = True
            self.controller.follow_trail(1, success)
        else:
            success = False
            self.controller.follow_trail(1, success)

        return off_path_serving_node

    # T-FIB-SC
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        """
        Process the request
        """
        self.controller.start_session(time, receiver, content, log)
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # Hop counter of RSN routing
        rsn_hop_count = 0
        # Quota used by the packet (flow)
        packet_quota = 0 
        # List of trails followed by the successful (off-path) requests, (more than one trails in the case of request multicasting)
        off_path_trails = []
        # On-path trail followed my the main request
        on_path_trail = [curr_hop]

        path = self.view.shortest_path(curr_hop, source)
        # Quota Limit on the request
        remaining_quota = len(path) - 1 + self.extra_quota
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            on_path_trail.append(v)
            # self.controller.forward_request_hop(u, v)
            self.controller.forward_off_path_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            remaining_quota-=1.0
            if remaining_quota <= 0 and v != source:
                # we spent the quota without either reaching the source or finding a cached copy
                #print "Out of Quota for content: " + repr(content)
                break

            rsn_entries = self.lookup_rsn_at_node(v, None, [u], self.fan_out)
            #print "Lookup returned: " + repr(len(rsn_entries)) + " entries at node: " + repr(v) + " for content: " + repr(content)
            for rsn_entry in rsn_entries:
                if remaining_quota <= 0:
                    #print "Out of Quota in off-path search for content: " + repr(content)
                    break
                next_hop = path[hop+1]
                rsn_hop = rsn_entry[0]
                position = rsn_entry[1]
                quota = rsn_entry[2]
                if rsn_hop == next_hop:
                    # we just found an "on-path" hint: continue with the FIB nexthop
                    continue
                """
                if success_rate is 0:
                    remaining_quota -= 1
                else:
                    remaining_quota -= remaining_quota*success_rate
                """
                remaining_quota -= quota
                off_path_serving_node = self.follow_offpath_trail(u, v, rsn_hop, on_path_trail, off_path_trails, source, position, quota)

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v

        # Return content: 
        # T-FIB-SC 
        sorted_paths = sorted(off_path_trails, key=len)
        if on_path_serving_node is not None: 
            sorted_paths.append(on_path_trail)
        visited = {} # keep track of the visited nodes to eliminate duplicate data packets arriving at a hop (simulating PIT forwarding)
        first = False
        for path in sorted_paths:
            if not first: # only forward the request of the shortest path
                first = True
                for hop in range(1, len(path)):
                    u = path[hop - 1]
                    v = path[hop]
                    self.controller.forward_request_hop(u, v)
            path.reverse()

            if path[0] == source:
            # Content coming from the server (i.e., source)
            # Insert/update rsn entry towards the direction of user
                c = len([v for v in path if self.view.has_cache(v)])
                x = 0.0
                placement = False
                for hop in range(1, len(path)): #XXX correct DFIB_OPH as well!
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if prev_hop in visited.keys() and visited[prev_hop]:
                        break
                    visited[prev_hop] = True
                    #print "Adding key: " + repr(key) + " @current node: " + repr(prev_hop)
                    if not placement:
                        key = self.form_key(content, curr_hop)
                        self.controller.put_rsn(prev_hop, curr_hop, key)
                    else:
                        key = self.form_key(content, prev_hop)
                        self.controller.put_rsn(curr_hop, prev_hop, key)
                    # Insert content to cache
                    if not placement:
                        N = sum([self.cache_size[n] for n in path[hop - 1:] if n in self.cache_size])
                        if curr_hop in self.cache_size:
                            x += 1
                        #TODO check if we haven't cached anything and we are at the last hop! If that is the case, then force a put_content
                        if self.view.has_cache(curr_hop):
                            prob_cache = float(N)/(self.t_tw * self.cache_size[curr_hop])*(x/c)**c
                            if random.random() < prob_cache:
                                self.controller.put_content(curr_hop)
                                placement = True
                            elif hop == (len(path)-1):
                                self.controller.put_content(curr_hop)
                                placement = True
                    # Forward the content
                    self.controller.forward_content_hop(prev_hop, curr_hop)
            else:
            # Content coming from a cache 
            # Insert/Update the rsn entry towards the direction of cache if such an entry existed (in the case of off-path hit)
                for hop in range(1, len(path)-1):
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if prev_hop in visited.keys() and visited[prev_hop]:
                        break
                    visited[prev_hop] = True
                    key = self.form_key(content, prev_hop)
                    #print "Adding key: " + repr(key) + " @current node: " + repr(curr_hop)
                    self.controller.put_rsn(curr_hop, prev_hop, key)
        
        self.controller.end_session()

@register_strategy('LIRA_DFIB_SC')
class LiraDfibSc(Strategy):
    """DFIB strategy with static cost

    If a node has got both an RSN and a cache, if the content is caches, put it
    in the RSN only if evicted
    """

    def __init__(self, view, controller, p=1.0, extra_quota=3, fan_out=1, quota_increment=0.3, limit_replica=True):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        max_detour : int, optional
            The max number of hop that can be performed following an RSN trail
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        rsn_on_evict : bool, optional
            If True content evicted from cache are inserted in the RSN
        """
        super(LiraDfibSc, self).__init__(view, controller)
        self.p = p
        self.fan_out = fan_out
        self.extra_quota = extra_quota
        self.n_requests = 0
        self.first = False
        self.quota_increment = quota_increment
        self.limit_replica = limit_replica

    def get_path_delay(path):
        path_delay = 0.0
        for hop in range(1, len(path)):
            u = path[hop-1]
            v = path[hop]
            path_delay += self.view.link_delay(u,v)
        return path_delay

    def form_key(self, content, node):
        """ form key to lookup content from RSN table
        """
        key = repr(content) + "-" + repr(node)
        return key

    # LIRA_DFIB_SC
    def lookup_rsn_at_node(self, node, content=None, ignore=[], fan_out=1):
        """lookup the rsn table at node 

        Parameters
        ----------
        node : node id of the node with rsn table
        content : the content id to lookup
        ignore : list of nexthop nodes to ignore
        fan_out : max number of next-hops returned 

        Return
        ------
        A list of rsn entries each represented as a triple; first index is the 
        next-hop node id, second index id the success rate of the entry 
        in the RSN table, third index is the position (i.e., rank) of the entry
        in the RSN table. 
        """
        
        if content is None:
            content = self.controller.session['content']

        neighbors = self.view.get_neighbors(node)
        neighbors = [n for n in neighbors if n not in ignore]
        neighbors = [n for n in neighbors if n not in self.view.topology().sources()]
        neighbors = [n for n in neighbors if n not in self.view.topology().receivers()]
        
        rsn_entries = []
        for n in neighbors:
            key = self.form_key(content, n) #repr(content) + "/" + repr(n)
            nexthop = self.view.peek_rsn(node, key)
            if nexthop is not None:
                if nexthop != n:
                    #print "Current node: " + repr(node) + " neighbor: " + repr(n) + " and nexthop: " + repr(nexthop) + " key: " + repr(key)
                    #print "Neighbors: " + repr(neighbors)
                    raise RuntimeError('This should not happen in lookup_rsn_at_node')
                #position = self.view.get_rsn_position(node, key)
                position = 0
                rsn_table = self.view.get_rsn_table(node)
                #n_lookups = rsn_table.get_nlookups()
                #n_success = rsn_table.get_nsuccess()
                #n_quotas = rsn_table.get_quota()
                self.controller.get_rsn(node, key) #lookup to change the position now
                success = 0.0
                rsn_entries.append([nexthop, position, 1])
                """
                if n_lookups[position] < 3: # TODO create a parameter for a threshold
                    dfib_size = rsn_table.get_size()
                    success = 0.0 #(1.0 - ((1.0*position)/dfib_size))
                    rsn_entries.append([nexthop, success, position])
                else:
                    success = (1.0*n_success[position])/n_lookups[position]
                    rsn_entries.append([nexthop, success, position])
                    if not self.first:
                        print "Accumulated enough statistics!"
                        self.first = True
                    #print "Nexthop: " + repr(nexthop) + " pos: " + repr(position) + " succ: " + repr(success)
                """

        # sort the entries by success rate (increasing order -- head is 0 tail is size-1)
        rsn_entries.sort(key = lambda x : x[1])
        
        return rsn_entries[0:fan_out]
        
    # LIRA_DFIB_SC
    def invalidate_tr(self, trail, content=None):
        """invalidate trail of DFIB
        """
        #print "invalidating trail " + repr(trail) 
        content = self.controller.session['content'] if content is None else content
        for hop in range(0, len(trail)-1):
            curr_hop = trail[hop]
            next_hop = trail[hop+1]
            if not self.view.has_rsn_table(curr_hop):
                continue
            key = self.form_key(content, next_hop) 
            is_removed = self.controller.remove_rsn(curr_hop, key)
            #print "Removing trail: " + repr(curr_hop) + " -> " + repr(next_hop)
            if is_removed is None:
                print "Error: " + " Trail: " + repr(trail) + " key " + repr(key) + " at node " + repr(curr_hop) + " nexthop " + repr(next_hop)
                print "is_removed: " + repr(is_removed)
                raise RuntimeError('This should not happen in invalidate_tr')
            #else:
            #    print "Trail is removed at node: " + repr(curr_hop)

    # LIRA_DFIB_SC
    def follow_offpath_trail(self, prev_hop, curr_hop, rsn_hop, on_path_trail, off_path_trails, source, position, quota):
        """ Follow an offpath trail all the way until either you find the content, or 
        arrive at a node with no SIT trail (i.e., dead-end)
        """
        off_path_serving_node = None
        trail = [curr_hop]
        positions = [position]
        # This loop is guaranteed to execute at least once, as rsn_hop is not None
        while rsn_hop is not None:
            prev_hop = curr_hop
            curr_hop = rsn_hop
            if curr_hop in trail:
            # loop in the explored off-path trail
                #print "Loop in the trail, calling invalidate " + repr(trail) + " / " + repr(rsn_hop)
                self.invalidate_tr(trail)
                break
            else:
                trail.append(curr_hop)
                if curr_hop == source or self.view.has_cache(curr_hop):
                    if self.controller.get_content(curr_hop):
                        off_path_serving_node = curr_hop
                        #print "Off path search successful: Found content at node " + repr(off_path_serving_node)
                        break
                
                rsn_entries = self.lookup_rsn_at_node(curr_hop, None, [prev_hop], 1) # returns an array of [[nexthop, position, quota]...]
                if not len(rsn_entries):
                    rsn_hop = None
                else:
                    rsn_entry = rsn_entries[0]
                    positions.append(rsn_entry[1])
                    rsn_hop = rsn_entry[0]
        else: # else of while
        # Onur: if break is executed above, this else is skipped
        # This point is reached when I did explore an RSN
        # trail but failed. 
        # Invalidate the trail here and return to on-path node
            #print "Followed an RSN, but failed: " + repr(trail)
            #print "on-path trail " + repr(on_path_trail)
            self.invalidate_tr(trail)

        #print "Trail: " + repr(trail) 
        """
        indx = 0
        for position in positions:
            rsn = self.view.get_rsn_table(trail[indx])
            #if rsn is None:
                #print "Node: " + repr(trail[indx]) + " has no rsn table "
            n_success = rsn.get_nsuccess()
            n_lookups = rsn.get_nlookups()
            n_quotas = rsn.get_quota()
            if off_path_serving_node is None:
                #n_quotas[position] /= 2
                #n_quotas[position] = max(1, n_quotas[position]/2) #XXX Lower bound is 1
                n_lookups[position] += 1
            else:
                #n_quotas[position] += self.quota_increment
                n_success[position] += 1
                n_lookups[position] += 1
            indx += 1
        """
        if off_path_serving_node is not None:
            trail = on_path_trail[:-1] + trail
            off_path_trails.append(trail)
            success = True
            self.controller.follow_trail(1, success)
        else:
            success = False
            self.controller.follow_trail(1, success)

        return off_path_serving_node

    #LIRA_DFIB_SC
    def print_quotas(self, num):
        """
        Print the quotas for a router (for debugging purposes)
        """
        topo = self.view.topology()
        routers = [v for v in topo.nodes_iter()
                     if topo.node[v]['stack'][0] == 'router']
        
        fname = "./Data/quota_stats_" + repr(num)
        aFile = open(fname, 'w')
        for v in routers:
            rsn = self.view.get_rsn_table(v)
            n_quotas = rsn.get_quota()
            n_lookups = rsn.get_nlookups()
            n_success = rsn.get_nsuccess()
            size = self.view.model.rsn_size[v]
            num_neighbors = len(self.view.get_neighbors(v))
            s = "Printing rsn table Quotas for " + repr(v) + " with " + repr(num_neighbors) + " neighbors\n"
            aFile.write(s)
            for index in range(0, size):
                s =  "\t" + repr(index) + ": " + repr(n_quotas[index]) + " : " + repr(n_success[index]) + " : " + repr(n_lookups[index]) +  "\n"
                aFile.write(s)

        aFile.close()

    # LIRA_DFIB_SC
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        """
        Process the request
        """
        #    print "Done with: " + repr(self.n_requests)
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # Hop counter of RSN routing
        rsn_hop_count = 0
        # Quota used by the packet (flow)
        packet_quota = 0 
        # Are we following a fresh (off-path) trail?
        fresh_trail = False
        # List of trails followed by the successful (off-path) requests, (more than one trails in the case of request multicasting)
        off_path_trails = []
        # On-path trail followed my the main request
        on_path_trail = [curr_hop]

        path = self.view.shortest_path(curr_hop, source)
        # Quota Limit on the request
        remaining_quota = len(path) - 1 + self.extra_quota
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            on_path_trail.append(v)
            # self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            remaining_quota-=1.0
            if remaining_quota <= 0 and v != source:
                # we spent the quota without either reaching the source or finding a cached copy
                #print "Out of Quota for content: " + repr(content)
                break

            rsn_entries = self.lookup_rsn_at_node(v, None, [u], self.fan_out)
            #print "Lookup returned: " + repr(len(rsn_entries)) + " entries at node: " + repr(v) + " for content: " + repr(content)
            for rsn_entry in rsn_entries:
                if remaining_quota <= 0:
                    #print "Out of Quota in off-path search for content: " + repr(content)
                    break
                next_hop = path[hop+1]
                rsn_hop = rsn_entry[0]
                position = rsn_entry[1]
                quota = rsn_entry[2]
                if rsn_hop == next_hop:
                    # we just found an "on-path" hint: continue with the FIB nexthop
                    continue
                remaining_quota -= quota
                off_path_serving_node = self.follow_offpath_trail(u, v, rsn_hop, on_path_trail, off_path_trails, source, position, quota)

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v
     
        # Return content: 
        # DFIB_SC
        # Sort return paths by length, TODO replace this by: sort by path latency
        sorted_paths = sorted(off_path_trails, key=len)
        if on_path_serving_node is not None: 
            sorted_paths.append(on_path_trail)
        visited = {} # keep track of the visited nodes to eliminate duplicate data packets arriving at a hop (simulating PIT forwarding)
        first = False
        for path in sorted_paths:
            if not first: # only forward the request of the shortest path
                first = True
                for hop in range(1, len(path)):
                    u = path[hop - 1]
                    v = path[hop]
                    self.controller.forward_request_hop(u, v)
            path.reverse()
            if self.limit_replica:
                if path[0] == source:
                # Content coming from the server (i.e., source)
                # Insert/update rsn entry towards the direction of user
                    for hop in range(2, len(path)-1):
                        curr_hop = path[hop]
                        prev_hop = path[hop-1]
                        if prev_hop in visited.keys() and visited[prev_hop]:
                            break
                        visited[prev_hop] = True
                        key = self.form_key(content, curr_hop)
                        #print "Adding key: " + repr(key) + " @current node: " + repr(prev_hop)
                        self.controller.put_rsn(prev_hop, curr_hop, key)
                        # Insert content to cache
                        if self.view.has_cache(curr_hop):
                            if self.p == 1.0 or random.random() <= self.p:
                                self.controller.put_content(prev_hop)
                        # Forward the content
                        self.controller.forward_content_hop(prev_hop, curr_hop)
                else:
                # Content coming from a cache 
                # Insert/Update the rsn entry towards the direction of cache if such an entry existed (in the case of off-path hit)
                    for hop in range(1, len(path)-1):
                        curr_hop = path[hop]
                        prev_hop = path[hop-1]
                        if prev_hop in visited.keys() and visited[prev_hop]:
                            break
                        visited[prev_hop] = True
                        key = self.form_key(content, prev_hop)
                        #print "Adding key: " + repr(key) + " @current node: " + repr(curr_hop)
                        self.controller.put_rsn(curr_hop, prev_hop, key)
                        # Forward the content
                        self.controller.forward_content_hop(prev_hop, curr_hop)
            else:
                for hop in range(1, len(path)-1):
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if prev_hop in visited.keys() and visited[prev_hop]:
                        break
                    visited[prev_hop] = True
                    key = self.form_key(content, prev_hop)
                    #print "Adding key: " + repr(key) + " @current node: " + repr(curr_hop)
                    self.controller.put_rsn(curr_hop, prev_hop, key)
                    # Forward the content
                    self.controller.forward_content_hop(prev_hop, curr_hop)

        self.controller.end_session()


@register_strategy('TFIB_DC')
class Tfib_dc(Strategy):
    """
    Strategy using forwarding budget but trails pointing to caches, not users.

    Content placement is done using a ProbCache-like approach with an upper-bound
    on how many times a content can be cached on the return path.
    """

    # T-FIB-DC
    def __init__(self, view, controller, t_tw=10, extra_quota=3, fan_out=1, quota_increment=1.0):
        """Constructor
        """
        super(Tfib_dc, self).__init__(view, controller)
        #ProbCache related:
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
        #Strategy related:
        self.fan_out = fan_out
        self.extra_quota = extra_quota
        self.quota_increment = quota_increment
        self.n_requests = 0

    # T-FIB-DC
    def form_key(self, content, node):
        """ form key to lookup content from RSN table
        """
        key = repr(content) + "-" + repr(node)
        return key
    
    # T-FIB-DC
    def lookup_rsn_at_node(self, node, content=None, ignore=[], fan_out=1):
        """lookup the rsn table at node 

        
        ----------
        node : node id of the node with rsn table
        content : the content id to lookup
        ignore : list of nexthop nodes to ignore
        fan_out : max number of next-hops returned 

        Return
        ------
        A list of rsn entries each represented as a triple; first index is the 
        next-hop node id, second index id the success rate of the entry 
        in the RSN table, third index is the position (i.e., rank) of the entry
        in the RSN table. 
        """
        
        if content is None:
            content = self.controller.session['content']

        neighbors = self.view.get_neighbors(node)
        neighbors = [n for n in neighbors if n not in ignore]
        neighbors = [n for n in neighbors if n not in self.view.topology().sources()]
        neighbors = [n for n in neighbors if n not in self.view.topology().receivers()]
        
        rsn_entries = []
        for n in neighbors:
            key = self.form_key(content, n) #repr(content) + "/" + repr(n)
            nexthop = self.view.peek_rsn(node, key)
            if nexthop is not None:
                if nexthop != n:
                    #print "Current node: " + repr(node) + " neighbor: " + repr(n) + " and nexthop: " + repr(nexthop) + " key: " + repr(key)
                    #print "Neighbors: " + repr(neighbors)
                    raise RuntimeError('This should not happen in lookup_rsn_at_node')
                position = self.view.get_rsn_position(node, key)
                rsn_table = self.view.get_rsn_table(node)
                #n_lookups = rsn_table.get_nlookups()
                #n_success = rsn_table.get_nsuccess()
                n_quotas = rsn_table.get_quota()
                self.controller.get_rsn(node, key) #lookup to change the position now
                success = 0.0
                quota = n_quotas[position]
                rsn_entries.append([nexthop, position, quota])


        # sort the entries by rank (increasing order -- head is 0 and tail is size-1)
        rsn_entries.sort(key = lambda x : x[1])
        
        return rsn_entries[0:fan_out]
    
    # T-FIB-DC
    def invalidate_tr(self, trail, content=None):
        """invalidate trail of DFIB
        """
        #print "invalidating trail " + repr(trail) 
        content = self.controller.session['content'] if content is None else content
        for hop in range(0, len(trail)-1):
            curr_hop = trail[hop]
            next_hop = trail[hop+1]
            if not self.view.has_rsn_table(curr_hop):
                continue
            key = self.form_key(content, next_hop) 
            is_removed = self.controller.remove_rsn(curr_hop, key)
            #print "Removing trail: " + repr(curr_hop) + " -> " + repr(next_hop)
            if is_removed is None:
                print "Error: " + " Trail: " + repr(trail) + " key " + repr(key) + " at node " + repr(curr_hop) + " nexthop " + repr(next_hop)
                print "is_removed: " + repr(is_removed)
                raise RuntimeError('This should not happen in invalidate_tr')

    # T-FIB-DC
    def follow_offpath_trail(self, prev_hop, curr_hop, rsn_hop, on_path_trail, off_path_trails, source, position, quota):
        """ Follow an offpath trail all the way until either you find the content, or 
        arrive at a node with no SIT trail (i.e., dead-end)
        """
        off_path_serving_node = None
        trail = [curr_hop]
        positions = [position]
        # This loop is guaranteed to execute at least once, as rsn_hop is not None
        while rsn_hop is not None:
            prev_hop = curr_hop
            curr_hop = rsn_hop
            self.controller.forward_off_path_request_hop(prev_hop, curr_hop)
            if curr_hop in trail:
            # loop in the explored off-path trail
                #print "Loop in the trail, calling invalidate " + repr(trail) + " / " + repr(rsn_hop)
                self.invalidate_tr(trail)
                break
            else:
                trail.append(curr_hop)
                if curr_hop == source or self.view.has_cache(curr_hop):
                    if self.controller.get_content(curr_hop):
                        off_path_serving_node = curr_hop
                        #print "Off path search successful: Found content at node " + repr(off_path_serving_node)
                        break
                
                rsn_entries = self.lookup_rsn_at_node(curr_hop, None, [prev_hop], 1) # returns an array of [[nexthop, position, quota]...]
                if not len(rsn_entries):
                    rsn_hop = None
                else:
                    rsn_entry = rsn_entries[0]
                    positions.append(rsn_entry[1])
                    rsn_hop = rsn_entry[0]
        else: # else of while
        # Onur: if break is executed above, this else is skipped
        # This point is reached when I did explore an RSN
        # trail but failed. 
        # Invalidate the trail here and return to on-path node
            self.invalidate_tr(trail)

        indx = 0
        for position in positions:
            rsn = self.view.get_rsn_table(trail[indx])
            n_quotas = rsn.get_quota()
            if off_path_serving_node is None:
                #n_quotas[position] /= 2
                n_quotas[position] = max(1, n_quotas[position]/2) #XXX Lower bound is 1
            else:
                n_quotas[position] += self.quota_increment
            indx += 1

        if off_path_serving_node is not None:
            trail = on_path_trail[:-1] + trail
            off_path_trails.append(trail)
            success = True
            self.controller.follow_trail(quota, success)
        else:
            success = False
            self.controller.follow_trail(quota, success)

        return off_path_serving_node
    
    # T-FIB-DC
    def print_quotas(self):
        """
        Print the quotas for a router (for debugging purposes)
        """
        topo = self.view.topology()
        routers = [v for v in topo.nodes_iter()
                     if topo.node[v]['stack'][0] == 'router']
        
        fname = "./Data/quota_stats" 
        aFile = open(fname, 'w')
        for v in routers:
            rsn = self.view.get_rsn_table(v)
            n_quotas = rsn.get_quota()
            n_lookups = rsn.get_nlookups()
            n_success = rsn.get_nsuccess()
            size = self.view.model.rsn_size[v]
            num_neighbors = len(self.view.get_neighbors(v))
            s = "Printing rsn table Quotas for " + repr(v) + " with " + repr(num_neighbors) + " neighbors\n"
            aFile.write(s)
            for index in range(0, size):
                s =  "\t" + repr(index) + ": " + repr(n_quotas[index]) + " : " + repr(n_success[index]) + " : " + repr(n_lookups[index]) +  "\n"
                aFile.write(s)

        aFile.close()

    # T-FIB-DC
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        """
        Process the request
        """
        if self.n_requests == 1079998: #Print the quota statistics at the end
            self.print_quotas()
        self.n_requests += 1
        self.controller.start_session(time, receiver, content, log)
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # Hop counter of RSN routing
        rsn_hop_count = 0
        # Quota used by the packet (flow)
        packet_quota = 0 
        # List of trails followed by the successful (off-path) requests, (more than one trails in the case of request multicasting)
        off_path_trails = []
        # On-path trail followed my the main request
        on_path_trail = [curr_hop]

        path = self.view.shortest_path(curr_hop, source)
        # Quota Limit on the request
        remaining_quota = len(path) - 1 + self.extra_quota
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            self.controller.forward_off_path_request_hop(u, v)
            on_path_trail.append(v)
            # self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            remaining_quota-=1.0
            if remaining_quota <= 0 and v != source:
                # we spent the quota without either reaching the source or finding a cached copy
                #print "Out of Quota for content: " + repr(content)
                break

            rsn_entries = self.lookup_rsn_at_node(v, None, [u], self.fan_out)
            #print "Lookup returned: " + repr(len(rsn_entries)) + " entries at node: " + repr(v) + " for content: " + repr(content)
            for rsn_entry in rsn_entries:
                if remaining_quota <= 0:
                    #print "Out of Quota in off-path search for content: " + repr(content)
                    break
                next_hop = path[hop+1]
                rsn_hop = rsn_entry[0]
                position = rsn_entry[1]
                quota = rsn_entry[2]
                if rsn_hop == next_hop:
                    # we just found an "on-path" hint: continue with the FIB nexthop
                    continue
                """
                if success_rate is 0:
                    remaining_quota -= 1
                else:
                    remaining_quota -= remaining_quota*success_rate
                """
                remaining_quota -= quota
                off_path_serving_node = self.follow_offpath_trail(u, v, rsn_hop, on_path_trail, off_path_trails, source, position, quota)

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v

        # Return content: 
        # T-FIB-DC 
        sorted_paths = sorted(off_path_trails, key=len)
        if on_path_serving_node is not None: 
            sorted_paths.append(on_path_trail)
        visited = {} # keep track of the visited nodes to eliminate duplicate data packets arriving at a hop (simulating PIT forwarding)
        first = False
        for path in sorted_paths:
            if not first: # only forward the request of the shortest path
                first = True
                for hop in range(1, len(path)):
                    u = path[hop - 1]
                    v = path[hop]
                    self.controller.forward_request_hop(u, v)
            path.reverse()

            if path[0] == source:
            # Content coming from the server (i.e., source)
            # Insert/update rsn entry towards the direction of user
                c = len([v for v in path if self.view.has_cache(v)])
                x = 0.0
                placement = False
                for hop in range(1, len(path)): #XXX correct DFIB_OPH as well!
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if prev_hop in visited.keys() and visited[prev_hop]:
                        break
                    visited[prev_hop] = True
                    #print "Adding key: " + repr(key) + " @current node: " + repr(prev_hop)
                    if not placement:
                        key = self.form_key(content, curr_hop)
                        self.controller.put_rsn(prev_hop, curr_hop, key)
                    else:
                        key = self.form_key(content, prev_hop)
                        self.controller.put_rsn(curr_hop, prev_hop, key)
                    # Insert content to cache
                    if not placement:
                        N = sum([self.cache_size[n] for n in path[hop - 1:] if n in self.cache_size])
                        if curr_hop in self.cache_size:
                            x += 1
                        if self.view.has_cache(curr_hop):
                            prob_cache = float(N)/(self.t_tw * self.cache_size[curr_hop])*(x/c)**c
                            if random.random() < prob_cache:
                                self.controller.put_content(curr_hop)
                                placement = True
                            elif hop == (len(path)-1): # force put if it is last hop
                                self.controller.put_content(curr_hop)
                                placement = True
                    # Forward the content
                    self.controller.forward_content_hop(prev_hop, curr_hop)
            else:
            # Content coming from a cache 
            # Insert/Update the rsn entry towards the direction of cache if such an entry existed (in the case of off-path hit)
                for hop in range(1, len(path)-1):
                    curr_hop = path[hop]
                    prev_hop = path[hop-1]
                    if prev_hop in visited.keys() and visited[prev_hop]:
                        break
                    visited[prev_hop] = True
                    key = self.form_key(content, prev_hop)
                    #print "Adding key: " + repr(key) + " @current node: " + repr(curr_hop)
                    self.controller.put_rsn(curr_hop, prev_hop, key)
        
        self.controller.end_session()

@register_strategy('TFIB_BC') # Breadcrumb strategy
class TfibBC(Strategy):
    """TFIB strategy with shortest path routing and Breadcrumb routing. Content placement is done using ProbCache and performed at most once for each data
    """

    def __init__(self, view, controller, t_tw=10):
        """Constructor
        
        Parameters
        ----------
        view : NetworkView
            An instance of the network view
        controller : NetworkController
            An instance of the network controller
        p : float, optional
            The probability to insert a content in a cache. If 1, the strategy
            always insert content, like a normal LCE, if less it behaves like
            a Bernoulli random caching strategy
        """
        super(TfibBC, self).__init__(view, controller)
        #ProbCache related:
        self.t_tw = t_tw
        self.cache_size = view.cache_nodes(size=True)
    
    @inheritdoc(Strategy)
    def process_event(self, time, receiver, content, log):
        self.controller.start_session(time, receiver, content, log)
        # Start point of the request path
        curr_hop = receiver
        # Source of content
        source = self.view.content_source(content)
        # Node serving the content on-path
        on_path_serving_node = None
        # Node serving the content off-path
        off_path_serving_node = None
        # off-path trail followed by the breadcrumb
        off_path_trail = None

        path = self.view.shortest_path(curr_hop, source)
        # Handle request        
        # Route requests to original source and queries caches on the path
        for hop in range(1, len(path)):
            u = path[hop - 1]
            v = path[hop]
            self.controller.forward_request_hop(u, v)
            # Return if there is cache hit at v
            if self.view.has_cache(v):
                if self.controller.get_content(v):
                    on_path_serving_node = v
                    break
            rsn_entry = self.controller.get_rsn(v) if self.view.has_rsn_table(v) else None
            if rsn_entry is not None and v != source:
                next_hop = path[hop + 1]
                rsn_nexthop_obj = rsn_entry.get_freshest_except_nodes(time, [u, next_hop])
                rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None
                # TODO: Check if distance to off-path cache is closer than source
                
                if rsn_hop is not None:
                    # If entry in RSN table, then start detouring to get cached
                    # content, if any
                    prev_hop = u
                    curr_hop = v
                    trail = [curr_hop] # store the explored trail to detect looping and invalidate in case it leads to no where
                
                    while rsn_hop is not None:
                        self.controller.forward_request_hop(curr_hop, rsn_hop)
                        prev_hop = curr_hop
                        curr_hop = rsn_hop

                        if rsn_hop in trail:
                            # loop in the explored off-path trail
                            break

                        else:
                            trail.append(curr_hop)
                            if curr_hop == source or self.view.has_cache(curr_hop):
                                if self.controller.get_content(curr_hop):
                                    off_path_serving_node = curr_hop
                                    off_path_trail = trail
                                    break

                            rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None

                            if rsn_entry is not None:
                                rsn_nexthop_obj = rsn_entry.get_freshest_except_node(time, prev_hop)
                                rsn_hop = rsn_nexthop_obj.nexthop if rsn_nexthop_obj is not None else None
                            else:
                                rsn_hop = None

                    else: # else of while
                        # Onur: if break is executed in the while loop, this else is skipped
                        # This point is reached when I did explore an RSN
                        # trail but failed. 
                        # Invalidate the trail here and return to on-path node
                        self.controller.invalidate_trail(trail)
                        success = False 
                        self.controller.follow_trail(0, success)
                        # travel the reverse path of the trail
                        trail.reverse()
                        for hop in range(1, len(trail)):
                            self.controller.forward_request_hop(trail[hop-1], trail[hop])

                if off_path_serving_node is not None:
                    # If I hit a content via a fresh off-path trail, I need to break
                    # the for loop,
                    # the on_path_serving_node will be None 
                    break

        else: # for concluded without break. Get content from source
            self.controller.get_content(v)
            on_path_serving_node = v
        
        if off_path_serving_node is not None:
            success = True
            self.controller.follow_trail(0, success) # Failure case is handled above

        # Return content:
        # TFIB_BC (TFIB with Breadcrumb)
        # if on_path_serving_node is not None, then follow the reverse of on-path
        if on_path_serving_node is not None:
            path = list(reversed(self.view.shortest_path(receiver, on_path_serving_node)))
            c = len([v for v in path if self.view.has_cache(v)])
            x = 0.0
            placement = False
            for hop in range(1, len(path)):
                curr_hop = path[hop]
                prev_hop = path[hop-1]
                # Insert/update rsn entry
                if not placement:
                    rsn_entry = self.controller.get_rsn(prev_hop) if self.view.has_rsn_table(prev_hop) else None
                    rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                    rsn_entry.insert_nexthop(curr_hop, curr_hop, len(path) - hop, time) 
                    self.controller.put_rsn(prev_hop, rsn_entry)
                else:
                    rsn_entry = self.controller.get_rsn(curr_hop) if self.view.has_rsn_table(curr_hop) else None
                    rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                    rsn_entry.insert_nexthop(prev_hop, prev_hop, len(path) - hop, time) 
                    self.controller.put_rsn(curr_hop, rsn_entry)

                # Insert content to cache
                if not placement:
                    N = sum([self.cache_size[n] for n in path[hop - 1:] if n in self.cache_size])
                    if curr_hop in self.cache_size:
                        x += 1
                    if self.view.has_cache(curr_hop):
                        prob_cache = float(N)/(self.t_tw * self.cache_size[curr_hop])*(x/c)**c
                        if random.random() < prob_cache:
                            self.controller.put_content(curr_hop)
                            placement = True
                        elif hop == (len(path)-1):
                            self.controller.put_content(curr_hop)
                            placement = True
                # Forward the content
                self.controller.forward_content_hop(prev_hop, curr_hop)

        elif off_path_trail is not None:
            distance = 0
            for hop in range(len(off_path_trail)-1, 0, -1):
                distance += 1
                curr_hop = trail[hop]
                prev_hop = trail[hop-1]
                # "Refresh" the DFIB entry which was used to forward the request to the off-path cache 
                rsn_entry = self.controller.get_rsn(prev_hop) if self.view.has_rsn_table(prev_hop) else None
                rsn_entry = RsnEntry() if rsn_entry is None else rsn_entry
                rsn_entry.insert_nexthop(curr_hop, trail[len(trail)-1], distance, time) 
                self.controller.put_rsn(prev_hop, rsn_entry)
            
            on_path_serving_node = off_path_trail[0]
            path = list(reversed(self.view.shortest_path(receiver, on_path_serving_node)))
            for hop in range(1, len(path)):
                curr_hop = path[hop]
                prev_hop = path[hop-1]
                
                # Forward the content
                self.controller.forward_content_hop(prev_hop, curr_hop)

        self.controller.end_session()
