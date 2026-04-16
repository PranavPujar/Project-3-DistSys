# Project 3: Distributed Systems (2PC & Raft)

## Overview
This project extends an existing distributed fishing game system by implementing two consensus protocols: Two-Phase Commit (2PC) and Raft. The goal is to ensure consistency, fault tolerance, and reliable coordination across multiple distributed nodes.

The system runs using Docker containers and communicates using gRPC (RPC-based communication).

GitHub Repository:
https://github.com/PranavPujar/Project-3-DistSys

## System Architecture
- Distributed system with multiple nodes (containers)
- Each node runs a service using gRPC
- Two main components:
  - 2PC Module → Handles distributed transactions
  - Raft Module → Handles leader election and log replication

## Features
- Leader election using Raft
- Log replication across nodes
- Fault tolerance (node crashes, partitions)
- Transaction coordination using 2PC
- Automatic request forwarding to leader
- Dockerized multi-node setup

## Technologies Used
- Python
- gRPC
- Docker & Docker Compose
- Distributed Systems Concepts (2PC, Raft)

## How to Run the Project

### 1. Start the Raft Cluster
cd raft
docker-compose up --build -d

### 2. View Logs
docker-compose logs -f

### 3. Send Client Requests
python3 raft_client.py 50051 "SET USER=Alice"

Try different nodes:
python3 raft_client.py 50052 "SET USER=Bob"
python3 raft_client.py 50053 "SET USER=Charlie"

## 2PC Execution (Optional)

cd two_pc
python coordinator.py
python participant.py

Workflow:
1. Coordinator sends Prepare RPC
2. Participants respond YES/NO
3. Coordinator sends Commit (if all YES) or Abort

## Testing Scenarios
1. Leader Crash & Re-election
2. Node Rejoining (Log Catch-up)
3. Follower Crash (Majority Maintained)
4. Network Partition (Minority Isolation)
5. Split Vote Resolution

## Expected Behavior
- Leader is elected automatically
- Logs replicate across nodes
- Majority required for commits
- Followers forward client requests
- System recovers from failures

## Contributors
- Pranav Pujar → Raft Implementation
- Hanumath Ponnaluri → 2PC Implementation

## Conclusion
This project demonstrates how distributed systems achieve consistency and fault tolerance using 2PC and Raft.

