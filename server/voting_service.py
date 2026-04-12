#!/usr/bin/env python3
import os
import sys
import time
import grpc
import uuid
from concurrent import futures

import fishing_pb2 as pb
import fishing_pb2_grpc as grpc_stub

NODE_ID = os.getenv("NODE_ID", "1")
NODE_IPS = os.getenv("NODE_IPS", "localhost").split(",")
VOTING_PORT = os.getenv("VOTING_PORT", "50051")
DECISION_PORT = os.getenv("DECISION_PORT", "60051")

class VotingService(grpc_stub.VotingServiceServicer):
    def __init__(self):
        pass

    def Prepare(self, request, context):
        print(f"Node {NODE_ID} runs RPC Prepare called by Node {request.node_id}")
        target_port = os.getenv("FISHING_PORT", "50051")
        print(f"Node {NODE_ID} sends RPC InternalPrepare to Node {NODE_ID}")
        
        with grpc.insecure_channel(f"localhost:{target_port}") as channel:
            stub = grpc_stub.DecisionServiceStub(channel)
            resp = stub.InternalPrepare(pb.InternalPrepareRequest(
                transaction_id=request.transaction_id,
                node_id=NODE_ID
            ))
        
        return pb.VoteResponse(vote=resp.vote, node_id=NODE_ID)

    def CommitTransaction(self, request, context):
        if NODE_ID != "1":
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Only Node 1 can coordinate transactions")

        tx_id = str(uuid.uuid4())
        print(f"\n[COORDINATOR] Starting 2PC for transaction {tx_id}")

        # Phase 1: Voting
        votes = []
        for i, ip in enumerate(NODE_IPS):
            target_node_id = str(i + 1)
            target_address = f"{ip}:50051"
            
            # Simple retry logic for distributed nodes
            success = False
            for attempt in range(5):
                try:
                    with grpc.insecure_channel(target_address) as channel:
                        stub = grpc_stub.VotingServiceStub(channel)
                        print(f"Node {NODE_ID} sends RPC Prepare to Node {target_node_id}")
                        resp = stub.Prepare(pb.VoteRequest(transaction_id=tx_id, node_id=NODE_ID), timeout=5)
                        votes.append(resp.vote)
                        success = True
                        break
                except Exception as e:
                    print(f"[COORDINATOR] Attempt {attempt+1}: Error contacting Node {target_node_id}")
                    time.sleep(2)
            
            if not success:
                print(f"[COORDINATOR] Failed to contact Node {target_node_id} after retries")
                votes.append(pb.VOTE_ABORT)

        # Decision
        global_decision = pb.DECISION_COMMIT if all(v == pb.VOTE_COMMIT for v in votes) else pb.DECISION_ABORT
        decision_str = "COMMIT" if global_decision == pb.DECISION_COMMIT else "ABORT"
        print(f"[COORDINATOR] Global Decision: {decision_str}")

        # Phase 2: Decision
        target_port = os.getenv("FISHING_PORT", "50051")
        print(f"Node {NODE_ID} sends RPC InternalDecision to Node {NODE_ID}")
        with grpc.insecure_channel(f"localhost:{target_port}") as channel:
            stub = grpc_stub.DecisionServiceStub(channel)
            stub.InternalDecision(pb.InternalDecisionRequest(
                transaction_id=tx_id,
                decision=global_decision,
                node_id=NODE_ID
            ))

        return pb.google_dot_protobuf_dot_empty__pb2.Empty()
