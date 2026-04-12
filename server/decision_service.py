#!/usr/bin/env python3
import os
import sys
import time
import grpc
from concurrent import futures

import fishing_pb2 as pb
import fishing_pb2_grpc as grpc_stub

NODE_ID = os.getenv("NODE_ID", "1")
NODE_IPS = os.getenv("NODE_IPS", "localhost").split(",")
DECISION_PORT = os.getenv("DECISION_PORT", "60051")

class DecisionService(grpc_stub.DecisionServiceServicer):
    def InternalPrepare(self, request, context):
        print(f"Node {NODE_ID} runs RPC InternalPrepare called by Node {NODE_ID}")
        # Logic to decide if we can commit. For demo, we always commit.
        # You could add logic here to abort if certain conditions aren't met.
        return pb.InternalPrepareResponse(vote=pb.VOTE_COMMIT)

    def InternalDecision(self, request, context):
        print(f"Node {NODE_ID} runs RPC InternalDecision called by Node {NODE_ID}")
        
        # As Node 1 Decision Phase, we multicast the decision to all participants' Decision Phases
        for i, ip in enumerate(NODE_IPS):
            target_node_id = str(i + 1)
            # In Docker, each container listens on its own IP:50051
            target_address = f"{ip}:50051"
            
            try:
                with grpc.insecure_channel(target_address) as channel:
                    stub = grpc_stub.DecisionServiceStub(channel)
                    
                    print(f"Node {NODE_ID} sends RPC GlobalDecision to Node {target_node_id}")
                    stub.GlobalDecision(pb.GlobalDecisionRequest(
                        transaction_id=request.transaction_id,
                        decision=request.decision,
                        node_id=NODE_ID
                    ))
            except Exception as e:
                print(f"[DECISION] Error contacting Node {target_node_id}: {e}")
        
        return pb.google_dot_protobuf_dot_empty__pb2.Empty()

    def GlobalDecision(self, request, context):
        print(f"Node {NODE_ID} runs RPC GlobalDecision called by Node {request.node_id}")
        decision_str = "COMMIT" if request.decision == pb.DECISION_COMMIT else "ABORT"
        print(f"[NODE {NODE_ID}] Local Transaction {request.transaction_id}: {decision_str}")
        return pb.GlobalDecisionResponse(ack=True, node_id=NODE_ID)
