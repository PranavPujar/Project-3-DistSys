# Raft Implementation Testing Guide (Q5)

This document outlines 5 test cases related to failures to demonstrate the robustness of the Raft implementation. Follow these steps to execute each scenario and capture screenshots for your final report.

## Prerequisites
Open a terminal and start the 5-node Raft cluster in the background:
```bash
cd raft
docker-compose up --build -d
```
*Wait ~5 seconds for the initial leader election to complete.*

To monitor the logs of the entire cluster in real-time, open a separate terminal window:
```bash
cd raft
docker-compose logs -f
```

---

## Test Case 1: Leader Crash & Re-election
**Objective:** Demonstrate that when the current leader fails, the followers detect the missing heartbeats and elect a new leader.

**Steps:**
1. **Identify the Leader:** Look at the `docker-compose logs -f` output and find the node that prints `[NODE X] Became LEADER`. Note its ID (e.g., `raftX`).
2. **Crash the Leader:** Stop the leader container. For example, if Node 3 is the leader:
   ```bash
   docker stop raft-raft3-1
   ```
3. **Observe the Logs:** Watch the logs. Within 1.5–3 seconds, you will see other nodes timeout, transition to Candidate, and start an election (`Starting election for term...`).
4. **Capture Screenshot:** Take a screenshot showing the leader being stopped and a new node printing `Became LEADER`.

---

## Test Case 2: Node Rejoining the Cluster (Log Catch-up)
**Objective:** Show that a node re-entering the system syncs its log with the current leader.

**Steps:**
1. **Submit Operations:** While the node from Test Case 1 is still stopped, submit a few operations using the client (use any running port, e.g., 50051):
   ```bash
   python3 raft_client.py 50051 "SET A=10"
   python3 raft_client.py 50051 "SET B=20"
   ```
2. **Restart the Node:** Bring the crashed node back online:
   ```bash
   docker start raft-raft3-1
   ```
3. **Observe the Logs:** The restarted node will receive `AppendEntries` from the current leader. It will see that its log is outdated, delete conflicting entries (if any), append the missing entries (`SET A=10`, `SET B=20`), and apply them.
4. **Capture Screenshot:** Take a screenshot showing the restarted node applying the operations that were committed while it was offline.

---

## Test Case 3: Follower Crash (Majority Still Maintained)
**Objective:** Demonstrate that the cluster continues to function and commit operations as long as a majority of nodes are alive.

**Steps:**
1. **Crash Two Followers:** Identify two follower nodes and stop them:
   ```bash
   docker stop raft-raft4-1 raft-raft5-1
   ```
2. **Submit Operation:** Send an operation using the client:
   ```bash
   python3 raft_client.py 50051 "SET C=30"
   ```
3. **Observe the Logs:** The leader will send `AppendEntries` to the remaining 2 nodes. Because 3 nodes (Leader + 2 Followers) form a majority (3 out of 5), the operation will be successfully committed and applied.
4. **Capture Screenshot:** Take a screenshot of the client receiving a "Success" response and the 3 running nodes applying the operation, despite the 2 missing nodes.

---

## Test Case 4: Network Partition (Minority Isolation)
**Objective:** Show that a leader isolated in a minority partition cannot commit new operations.

**Steps:**
1. **Isolate the Leader:** Assume Node 1 is the leader. Stop 3 *other* nodes to simulate the leader being cut off with only one other follower (a minority of 2 out of 5):
   ```bash
   docker stop raft-raft2-1 raft-raft3-1 raft-raft4-1
   ```
2. **Submit Operation:** Attempt to submit an operation to the isolated leader:
   ```bash
   python3 raft_client.py 50051 "SET D=40"
   ```
3. **Observe the Client:** The client command will hang or timeout after 5 seconds because the leader cannot gather a majority of ACKs (it only has 1 follower left).
4. **Capture Screenshot:** Take a screenshot of the client returning a "Timeout waiting for commit" failure message.

---

## Test Case 5: Split Vote Resolution
**Objective:** Prove that the randomized election timeouts successfully resolve split votes.

**Steps:**
1. **Stop the Cluster:**
   ```bash
   docker-compose stop
   ```
2. **Start Cluster Simultaneously:** Start all nodes at the exact same time.
   ```bash
   docker-compose start
   ```
3. **Observe the Logs:** Because all nodes start simultaneously, multiple nodes might time out at the same time and become Candidates. You will see multiple nodes logging `Starting election`. Some may log `Error contacting Node X` or vote for themselves. Due to the randomized timer (1.5s - 3.0s), one node will eventually time out slightly faster on the *next* term, secure a majority, and become the leader.
4. **Capture Screenshot:** Take a screenshot showing multiple candidates requesting votes, followed by a single node ultimately declaring itself the leader for a new term.
