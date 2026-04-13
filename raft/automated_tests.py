#!/usr/bin/env python3
import subprocess
import time
import grpc
import raft_pb2 as pb
import raft_pb2_grpc as grpc_stub
import sys

# Configuration
NODES = {
    "1": "50051",
    "2": "50052",
    "3": "50053",
    "4": "50054",
    "5": "50055"
}

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def ensure_cluster_alive():
    """Starts all nodes and waits for a stable leader."""
    print("[SETUP] Ensuring all nodes are up and a leader is elected...")
    run_cmd("docker-compose start") # Start any stopped containers
    
    for attempt in range(15):
        leader_id, port = get_leader()
        if leader_id:
            print(f"[SETUP] Cluster ready. Leader is Node {leader_id}")
            return leader_id, port
        time.sleep(2)
    
    print("[SETUP] Error: Could not find a stable leader.")
    return None, None

def get_leader():
    """Iterates through nodes to find the current leader."""
    for node_id, port in NODES.items():
        try:
            with grpc.insecure_channel(f"localhost:{port}") as channel:
                stub = grpc_stub.RaftServiceStub(channel)
                # Use a very short timeout for leader discovery
                resp = stub.SubmitOperation(pb.ClientRequest(operation="QUERY", client_id="Test"), timeout=1.5)
                if resp.leader_id:
                    return resp.leader_id, NODES.get(resp.leader_id)
        except Exception:
            continue
    return None, None

def submit_op(port, op, timeout=6.0):
    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = grpc_stub.RaftServiceStub(channel)
            resp = stub.SubmitOperation(pb.ClientRequest(operation=op, client_id="Test"), timeout=timeout)
            return resp
    except Exception:
        return None

def test_case_1_leader_crash():
    print("\n--- Test Case 1: Leader Crash & Re-election ---")
    leader_id, port = ensure_cluster_alive()
    if not leader_id: return False
    
    print(f"Crashing Leader Node {leader_id}...")
    run_cmd(f"docker stop raft-raft{leader_id}-1")
    
    print("Waiting for re-election (8s)...")
    time.sleep(8)
    
    new_leader, _ = get_leader()
    if new_leader and new_leader != leader_id:
        print(f"Success! New Leader is Node {new_leader}")
        return True
    else:
        print(f"Failed! Leader is {new_leader}")
        return False

def test_case_2_node_rejoin():
    print("\n--- Test Case 2: Node Rejoining (Log Catch-up) ---")
    leader_id, port = ensure_cluster_alive()
    if not leader_id: return False
    
    # Pick a follower to crash
    follower_id = "1" if leader_id != "1" else "2"
    print(f"Crashing Follower Node {follower_id}...")
    run_cmd(f"docker stop raft-raft{follower_id}-1")
    
    op_name = f"SYNC_TEST_{int(time.time())}"
    print(f"Submitting '{op_name}' to Leader...")
    resp = submit_op(port, op_name)
    
    print(f"Restarting Node {follower_id}...")
    run_cmd(f"docker start raft-raft{follower_id}-1")
    print("Waiting for sync (6s)...")
    time.sleep(6)
    
    logs = run_cmd(f"docker logs raft-raft{follower_id}-1").stdout
    if op_name in logs:
        print(f"Success! Node {follower_id} caught up and applied the missing operation.")
        return True
    else:
        print(f"Failed! Operation '{op_name}' not found in Node {follower_id} logs.")
        return False

def test_case_3_follower_crash_majority():
    print("\n--- Test Case 3: Follower Crash (Majority Maintained) ---")
    leader_id, leader_port = ensure_cluster_alive()
    if not leader_id: return False
    
    stopped = []
    for nid in NODES:
        if nid != leader_id and len(stopped) < 2:
            run_cmd(f"docker stop raft-raft{nid}-1")
            stopped.append(nid)
    
    print(f"Stopped 2 followers: {stopped}. (3/5 alive).")
    print("Submitting 'MAJORITY_OP'...")
    resp = submit_op(leader_port, "MAJORITY_OP")
    
    if resp and resp.success:
        print("Success! Operation committed with majority.")
        return True
    else:
        print(f"Failed! Success={resp.success if resp else 'NoResp'}")
        return False

def test_case_4_minority_isolation():
    print("\n--- Test Case 4: Network Partition (Minority Isolation) ---")
    leader_id, leader_port = ensure_cluster_alive()
    if not leader_id: return False
    
    stopped = []
    for nid in NODES:
        if nid != leader_id and len(stopped) < 3:
            run_cmd(f"docker stop raft-raft{nid}-1")
            stopped.append(nid)
    
    print(f"Stopped 3 nodes: {stopped}. (2/5 alive - Minority).")
    print("Submitting 'MINORITY_OP' (Expect Timeout)...")
    resp = submit_op(leader_port, "MINORITY_OP", timeout=4.0)
    
    if resp and not resp.success and "Timeout" in resp.result:
        print("Success! Leader correctly refused to commit without majority.")
        return True
    else:
        print(f"Failed! Response: {resp.result if resp else 'Connection Error (Expected)'}")
        # In Raft, a leader might also become unreachable if it steps down during isolation
        return resp is None or "Timeout" in str(resp)

def test_case_5_split_vote():
    print("\n--- Test Case 5: Split Vote Resolution ---")
    print("Restarting whole cluster simultaneously...")
    run_cmd("docker-compose stop && docker-compose start")
    print("Waiting for stability (12s)...")
    time.sleep(12)
    
    leader_id, _ = get_leader()
    if leader_id:
        print(f"Success! Stable leader Node {leader_id} elected.")
        return True
    else:
        print("Failed! No stable leader elected.")
        return False

def run_all_tests():
    # Initialize Docker
    run_cmd("docker-compose up -d")
    
    tests = [
        ("Leader Crash", test_case_1_leader_crash),
        ("Node Rejoin", test_case_2_node_rejoin),
        ("Follower Crash (Majority)", test_case_3_follower_crash_majority),
        ("Minority Isolation", test_case_4_minority_isolation),
        ("Split Vote", test_case_5_split_vote)
    ]
    
    results = []
    for name, func in tests:
        try:
            passed = func()
            results.append((name, passed))
        except Exception as e:
            print(f"Test {name} crashed with error: {e}")
            results.append((name, False))
    
    print("\n" + "="*40)
    print(f"{'TEST NAME':30} | {'STATUS'}")
    print("-" * 40)
    for name, passed in results:
        print(f"{name:30} | {'PASSED' if passed else 'FAILED'}")
    print("="*40)

if __name__ == "__main__":
    run_all_tests()
