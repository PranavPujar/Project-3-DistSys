#!/usr/bin/env python3
import os
import sys
import time
import random
import threading
from concurrent import futures

import grpc
import raft_pb2 as pb
import raft_pb2_grpc as grpc_stub

NODE_ID = os.getenv("NODE_ID", "1")
NODE_IPS = os.getenv("NODE_IPS", "localhost").split(",")
PORT = "50051"

class State:
    FOLLOWER = "Follower"
    CANDIDATE = "Candidate"
    LEADER = "Leader"

class RaftServer(grpc_stub.RaftServiceServicer):
    def __init__(self):
        self.lock = threading.RLock()
        
        # Persistent state
        self.current_term = 0
        self.voted_for = None
        self.log = [] # List of LogEntry messages
        
        # Volatile state
        self.commit_index = -1
        self.last_applied = -1
        self.state = State.FOLLOWER
        self.leader_id = None
        
        # Volatile state on leaders
        self.next_index = {ip: 0 for ip in NODE_IPS}
        self.match_index = {ip: -1 for ip in NODE_IPS}
        
        # Timers
        self.election_timer = None
        self.heartbeat_timer = None
        self.reset_election_timer()

    def reset_election_timer(self):
        if self.election_timer:
            self.election_timer.cancel()
        timeout = random.uniform(1.5, 3.0)
        self.election_timer = threading.Timer(timeout, self.start_election)
        self.election_timer.start()

    def reset_heartbeat_timer(self):
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
        self.heartbeat_timer = threading.Timer(1.0, self.send_heartbeats)
        self.heartbeat_timer.start()

    def start_election(self):
        with self.lock:
            if self.state == State.LEADER:
                return
            
            self.state = State.CANDIDATE
            self.current_term += 1
            self.voted_for = NODE_ID
            self.leader_id = None
            print(f"[NODE {NODE_ID}] Starting election for term {self.current_term}")
            
            term = self.current_term
            last_log_index = len(self.log) - 1
            last_log_term = self.log[-1].term if self.log else 0
            
        self.reset_election_timer() # Reset timeout for next potential election
        
        votes = 1 # Voted for self
        
        def request_vote(target_ip, target_id):
            nonlocal votes
            if target_id == NODE_ID:
                return
            try:
                print(f"Node {NODE_ID} sends RPC RequestVote to Node {target_id}")
                channel = grpc.insecure_channel(f"{target_ip}:{PORT}")
                stub = grpc_stub.RaftServiceStub(channel)
                req = pb.RequestVoteRequest(
                    term=term,
                    candidate_id=NODE_ID,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term
                )
                resp = stub.RequestVote(req, timeout=0.5)
                
                with self.lock:
                    if self.state != State.CANDIDATE or self.current_term != term:
                        return
                    if resp.term > self.current_term:
                        self.current_term = resp.term
                        self.state = State.FOLLOWER
                        self.voted_for = None
                        self.reset_election_timer()
                        return
                    if resp.vote_granted:
                        votes += 1
                        if votes > len(NODE_IPS) // 2 and self.state == State.CANDIDATE:
                            self.become_leader()
            except Exception as e:
                pass

        for i, ip in enumerate(NODE_IPS):
            t = threading.Thread(target=request_vote, args=(ip, str(i+1)))
            t.start()

    def become_leader(self):
        self.state = State.LEADER
        self.leader_id = NODE_ID
        print(f"[NODE {NODE_ID}] Became LEADER for term {self.current_term}")
        
        for ip in NODE_IPS:
            self.next_index[ip] = len(self.log)
            self.match_index[ip] = -1
            
        if self.election_timer:
            self.election_timer.cancel()
            self.election_timer = None
        
        self.send_heartbeats()

    def send_heartbeats(self):
        try:
            with self.lock:
                if self.state != State.LEADER:
                    return
                term = self.current_term
                commit_index = self.commit_index
                log_copy = list(self.log)

            def send_append_entries(target_ip, target_id):
                if target_id == NODE_ID:
                    return
                try:
                    with self.lock:
                        ni = self.next_index[target_ip]
                        prev_log_index = ni - 1
                        prev_log_term = log_copy[prev_log_index].term if prev_log_index >= 0 else 0
                        entries_to_send = log_copy[ni:]
                    
                    print(f"Node {NODE_ID} sends RPC AppendEntries to Node {target_id}")
                    channel = grpc.insecure_channel(f"{target_ip}:{PORT}")
                    stub = grpc_stub.RaftServiceStub(channel)
                    req = pb.AppendEntriesRequest(
                        term=term,
                        leader_id=NODE_ID,
                        prev_log_index=prev_log_index,
                        prev_log_term=prev_log_term,
                        entries=entries_to_send,
                        leader_commit=commit_index
                    )
                    resp = stub.AppendEntries(req, timeout=0.5)
                    
                    with self.lock:
                        if self.state != State.LEADER or self.current_term != term:
                            return
                        if resp.term > self.current_term:
                            self.current_term = resp.term
                            self.state = State.FOLLOWER
                            self.voted_for = None
                            self.reset_election_timer()
                            return
                        
                        if resp.success:
                            if entries_to_send:
                                self.match_index[target_ip] = prev_log_index + len(entries_to_send)
                                self.next_index[target_ip] = self.match_index[target_ip] + 1
                                self.update_commit_index()
                        else:
                            self.next_index[target_ip] = max(0, self.next_index[target_ip] - 1)
                            
                except Exception as e:
                    pass

            for i, ip in enumerate(NODE_IPS):
                t = threading.Thread(target=send_append_entries, args=(ip, str(i+1)))
                t.start()
                
            self.reset_heartbeat_timer()
        except Exception as e:
            print(f"[LEADER ERROR] Failed to send heartbeats: {e}")

    def update_commit_index(self):
        # find N such that N > commit_index, a majority of match_index[i] >= N, and log[N].term == current_term
        for n in range(len(self.log) - 1, self.commit_index, -1):
            if self.log[n].term != self.current_term:
                continue
            matches = 1 # self
            for ip in NODE_IPS:
                if str(NODE_IPS.index(ip) + 1) == NODE_ID:
                    continue
                if self.match_index[ip] >= n:
                    matches += 1
            if matches > len(NODE_IPS) // 2:
                self.commit_index = n
                print(f"[NODE {NODE_ID}] Commit index updated to {n}")
                self.apply_logs()
                break

    def apply_logs(self):
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            print(f"[NODE {NODE_ID}] Applied operation: {entry.operation} at index {self.last_applied}")

    # RPC Handlers
    def RequestVote(self, request, context):
        print(f"Node {NODE_ID} runs RPC RequestVote called by Node {request.candidate_id}")
        with self.lock:
            if request.term > self.current_term:
                self.current_term = request.term
                self.state = State.FOLLOWER
                self.voted_for = None
                self.leader_id = None
                self.reset_election_timer()
            
            vote_granted = False
            last_log_index = len(self.log) - 1
            last_log_term = self.log[-1].term if self.log else 0
            
            log_is_up_to_date = False
            if request.last_log_term > last_log_term:
                log_is_up_to_date = True
            elif request.last_log_term == last_log_term and request.last_log_index >= last_log_index:
                log_is_up_to_date = True
                
            if request.term == self.current_term:
                if (self.voted_for is None or self.voted_for == request.candidate_id) and log_is_up_to_date:
                    vote_granted = True
                    self.voted_for = request.candidate_id
                    self.reset_election_timer()
            
            return pb.RequestVoteResponse(term=self.current_term, vote_granted=vote_granted, node_id=NODE_ID)

    def AppendEntries(self, request, context):
        print(f"Node {NODE_ID} runs RPC AppendEntries called by Node {request.leader_id}")
        with self.lock:
            if request.term > self.current_term:
                self.current_term = request.term
                self.state = State.FOLLOWER
                self.voted_for = None
                self.leader_id = request.leader_id
                
            if request.term < self.current_term:
                return pb.AppendEntriesResponse(term=self.current_term, success=False, node_id=NODE_ID)
            
            self.reset_election_timer()
            self.state = State.FOLLOWER
            self.leader_id = request.leader_id
            
            if request.prev_log_index >= len(self.log):
                return pb.AppendEntriesResponse(term=self.current_term, success=False, node_id=NODE_ID)
            if request.prev_log_index >= 0 and self.log[request.prev_log_index].term != request.prev_log_term:
                return pb.AppendEntriesResponse(term=self.current_term, success=False, node_id=NODE_ID)
            
            # Delete conflicting entries and append new ones
            for i, entry in enumerate(request.entries):
                idx = request.prev_log_index + 1 + i
                if idx < len(self.log):
                    if self.log[idx].term != entry.term:
                        self.log = self.log[:idx]
                        self.log.append(entry)
                else:
                    self.log.append(entry)
                    
            if request.leader_commit > self.commit_index:
                self.commit_index = min(request.leader_commit, len(self.log) - 1)
                self.apply_logs()
                
            return pb.AppendEntriesResponse(term=self.current_term, success=True, node_id=NODE_ID)

    def SubmitOperation(self, request, context):
        client_node_id = context.peer().split(":")[0] # Simplified logic to just show received
        print(f"Node {NODE_ID} runs RPC SubmitOperation called by Client {request.client_id}")
        
        with self.lock:
            if self.state == State.LEADER:
                # Append to log
                new_index = len(self.log)
                entry = pb.LogEntry(operation=request.operation, term=self.current_term, index=new_index)
                self.log.append(entry)
                print(f"[NODE {NODE_ID}] Leader appended operation {request.operation} at index {new_index}")
            else:
                if self.leader_id:
                    print(f"[NODE {NODE_ID}] Forwarding operation to leader {self.leader_id}")
                    try:
                        leader_ip = NODE_IPS[int(self.leader_id)-1]
                        channel = grpc.insecure_channel(f"{leader_ip}:{PORT}")
                        stub = grpc_stub.RaftServiceStub(channel)
                        print(f"Node {NODE_ID} sends RPC SubmitOperation to Node {self.leader_id}")
                        resp = stub.SubmitOperation(request)
                        return resp
                    except Exception as e:
                        return pb.ClientResponse(success=False, leader_id=self.leader_id, result="Failed to forward")
                else:
                    return pb.ClientResponse(success=False, leader_id="", result="No known leader")
                    
        # Wait for commit if we are the leader
        target_index = len(self.log) - 1
        start_time = time.time()
        while time.time() - start_time < 5.0:
            with self.lock:
                if self.commit_index >= target_index:
                    return pb.ClientResponse(success=True, leader_id=NODE_ID, result="Committed")
            time.sleep(0.1)
            
        return pb.ClientResponse(success=False, leader_id=NODE_ID, result="Timeout waiting for commit")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    grpc_stub.add_RaftServiceServicer_to_server(RaftServer(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"Raft Node {NODE_ID} listening on port {PORT}")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
