# MMO Fishing Game – Prototype Architecture

This repository contains a prototype for a massively‑multiplayer online (MMO) fishing game that can scale horizontally.  
Each server instance is responsible for a *tile* of the world and acts as the single source of truth for that tile.  

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
  - [`client/`](#client)
  - [`server/`](#server)
  - [`servermono/`](#servermono)
- [Running the Code](#running-the-code)
  - [Client](#client-1)
  - [6‑Node Server Cluster](#6-node-server-cluster)
  - [Single‑Node (Mono) Server](#single-node-mono-server)
- [Performance Benchmarks](#performance-benchmarks)
  - [6‑Node System](#6-node-system)
  - [1‑Node System](#1-node-system)
- [gRPC Service Definition](#grpc-service-definition)
- [Future Work](#future-work)
- [License](#license)

---

## Overview

* **Goal** – Show nearby players on a live map with minimal latency.  
* **Approach** – Horizontal scaling via tile‑based servers, gRPC for low‑latency communication.  
* **Testing** – k6 load tests (`fishing_test.js`) to simulate concurrent users.

---

## Project Structure

```
.
├── client/          # Simple test client (Python)
├── server/          # 6‑node cluster implementation
│   └── docker-compose.yml
├── servermono/      # Single‑node (monolithic) implementation
│   └── docker-compose.yml
├── fishing_test.js  # k6 load‑testing script
└── fishing.proto    # gRPC service definitions
```

### `client/`

A minimal Python client that can:
* Log in
* Update location
* Start a fishing stream
* Receive live updates

**Run**

```bash
cd client
python3 client.py
```

### `server/`

A 6‑node Docker Compose setup. Each node runs the same service and shares a simple in‑memory store.

**Run**

```bash
cd server
docker compose up
```

### `servermono/`

A single‑node Docker Compose setup for quick debugging and baseline performance.

**Run**

```bash
cd servermono
docker compose up
```

---

## Running the Code

1. **Prerequisites**

   * Docker & Docker Compose
   * Python 3 (for the client)
   * Go (to build the server binaries, if compiling locally)

2. **Start the Servers**

   ```bash
   # 6‑node cluster
   cd server && docker compose up

   # or single node
   cd servermono && docker compose up
   ```

3. **Run the Client**

   ```bash
   cd client && python3 client.py
   ```

4. **Load‑Test with k6**

   ```bash
   brew install k6          # macOS; adjust for your OS
   k6 run fishing_test.js
   ```

---

## Performance Benchmarks

### 6‑Node System

```
iteration_duration...........: avg=1.01s  min=1s       med=1.01s  max=1.05s   p(90)=1.02s   p(95)=1.03s  
iterations...................: 1000   98.283894/s
vus..........................: 100    min=100      max=100
grpc_req_duration............: avg=7.73ms  min=806.29µs med=6.65ms max=31.33ms p(90)=14.17ms p(95)=17.01ms
grpc_streams.................: 1000   98.283894/s
grpc_streams_msgs_received...: 1000   98.283894/s
grpc_streams_msgs_sent.......: 5000   491.419472/s
```

### 1‑Node System

```
iteration_duration...........: avg=1.02s  min=1s       med=1s     max=1.2s     p(90)=1.08s   p(95)=1.1s  
iterations...................: 1000   96.866251/s
vus..........................: 100    min=100      max=100
grpc_req_duration............: avg=13.4ms  min=596.66µs med=3.61ms max=176.58ms p(90)=59.39ms p(95)=79.6ms
grpc_streams.................: 1000   96.866251/s
grpc_streams_msgs_received...: 1000   96.866251/s
grpc_streams_msgs_sent.......: 5000   484.331254/s
```

> **Takeaway** – Horizontal scaling reduces request latency by ~40 % and increases throughput.

---

## gRPC Service Definition

```proto
syntax = "proto3";

package fishing;

service FishingService {
  rpc ListUser (ListUserRequest) returns (stream User);
  rpc Login (LoginRequest) returns (LoginResponse);
  rpc UpdateLocation (UpdateLocationRequest) returns (google.protobuf.Empty);
  rpc StartFishing (StartFishingRequest) returns (stream FishingEvent);
  rpc CurrentUsers (CurrentUsersRequest) returns (CurrentUsersResponse);
  rpc Inventory (InventoryRequest) returns (InventoryResponse);
  rpc GetImage (GetImageRequest) returns (GetImageResponse);
}
```

* **Login** – Authenticate a player.  
* **UpdateLocation** – Send new GPS coordinates.  
* **StartFishing** – Opens a server‑side stream of fishing events.  
* **CurrentUsers** – Returns the current player count and streams updates when players join/leave.  
* **Inventory** – Lists a player’s caught fish on that node.  
* **GetImage** – Returns an image of the tile (e.g., a map snapshot).

---

## Future Work

1. **Persistence Layer** – Integrate PocketBase (or another database) for durable storage and centralized data.  
2. **Dynamic Server Discovery** – Given an (x, y) coordinate, route the client to the responsible tile server.  
3. **Multi‑Server Client** – Build a client that can subscribe to multiple servers simultaneously, enabling seamless map rendering across tiles.  
4. **Load Balancing & Auto‑Scaling** – Use a service mesh or Kubernetes to automatically scale nodes based on player density.  
5. **Security Enhancements** – Token‑based auth, rate limiting, and data validation.
