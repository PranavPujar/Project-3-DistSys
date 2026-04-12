#!/usr/bin/env python3
import sys
import grpc
import raft_pb2 as pb
import raft_pb2_grpc as grpc_stub

def main():
    if len(sys.argv) < 3:
        print("Usage: python raft_client.py <node_port> <operation>")
        print("Example: python raft_client.py 50051 'SET x=5'")
        sys.exit(1)

    port = sys.argv[1]
    operation = " ".join(sys.argv[2:])
    
    target = f"localhost:{port}"
    print(f"Connecting to {target}...")
    
    try:
        with grpc.insecure_channel(target) as channel:
            stub = grpc_stub.RaftServiceStub(channel)
            
            req = pb.ClientRequest(operation=operation, client_id="Client1")
            # Client logging format required by the assignment
            print(f"Node Client sends RPC SubmitOperation to Node (Port {port})")
            
            resp = stub.SubmitOperation(req)
            
            if resp.success:
                print(f"Success! Operation '{operation}' committed by Leader Node {resp.leader_id}")
            else:
                print(f"Failed. Reason: {resp.result}. Current Leader: {resp.leader_id if resp.leader_id else 'Unknown'}")
                
    except grpc.RpcError as e:
        print(f"RPC failed: {e}")

if __name__ == "__main__":
    main()
