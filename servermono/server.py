#!/usr/bin/env python3
# server.py

import time
import random
import threading
from concurrent import futures

import grpc
import fishing_pb2 as pb
import fishing_pb2_grpc as grpc_stub

# ----------------------------------------------------------------------
# In‑memory state (protected by a lock)
# ----------------------------------------------------------------------
class ServerState:
    def __init__(self):
        self.users = {}          # jwt -> pb.User
        self.inventory = {}      # jwt -> list[Fish]
        self.user_id_seq = 1
        self.lock = threading.Lock()

    def add_user(self, jwt):
        with self.lock:
            if jwt not in self.users:
                uid = self.user_id_seq
                self.user_id_seq += 1
                user = pb.User(id=uid, x=0.0, y=0.0, is_fishing=False)
                self.users[jwt] = user
                self.inventory.setdefault(jwt, [])
                return True
            return False

    def update_user(self, jwt, x, y):
        with self.lock:
            if jwt in self.users:
                u = self.users[jwt]
                u.x = x
                u.y = y

    def remove_user(self, jwt):
        with self.lock:
            self.users.pop(jwt, None)
            self.inventory.pop(jwt, None)

    def get_user_snapshot(self):
        with self.lock:
            return list(self.users.values())

    def current_user_count(self):
        with self.lock:
            return len(self.users)

    def add_fish_to_user(self, jwt, fish):
        with self.lock:
            if jwt in self.inventory:
                self.inventory[jwt].append(fish)

    def get_all_fishes(self):
        with self.lock:
            all_fishes = []
            for fishes in self.inventory.values():
                all_fishes.extend(fishes)
            return all_fishes

state = ServerState()

# ----------------------------------------------------------------------
# Service implementation
# ----------------------------------------------------------------------
class FishingService(grpc_stub.FishingServiceServicer):
    # ---------- Login ----------
    def Login(self, request, context):
        # Dummy auth – always accept
        token = f"{request.username}:{request.password}"
        print(f"[LOGIN] User '{token}' logged in.")
        return pb.LoginResponse(token=token)

    # ---------- UpdateLocation (client‑stream) ----------
    def UpdateLocation(self, request_iterator, context):
        jwt = None

        # This function will be executed when the RPC ends
        def cleanup():
            if jwt:
                state.remove_user(jwt)
                print(f"[UPDATE] User stream closed: {jwt}")

        # Register the cleanup callback
        context.add_callback(cleanup)

        for req in request_iterator:
            if not jwt:          # first message establishes the user
                jwt = req.jwt
                added = state.add_user(jwt)
                if added:
                    print(f"[UPDATE] New user stream opened: {jwt}")

            # Keep the user's location up to date
            state.update_user(jwt, req.x, req.y)

        # No explicit call to cleanup() is needed – it will run automatically.
        return pb.UpdateLocationResponse(success=True)


    # ---------- ListUsers (server‑stream) ----------
    def ListUsers(self, request, context):
        for user in state.get_user_snapshot():
            yield user


    # ---------- StartFishing (server‑stream) ----------
    def StartFishing(self, request, context):
        jwt = request.jwt
        # Random chance increases with number of users
        base_chance = 0.1
        extra_per_user = 0.05
        chance = base_chance + state.current_user_count() * extra_per_user

        print(f"[FISH] User {jwt} started fishing. Chance={chance:.2f}")
        while context.is_active():
            # Simulate a short delay
            time.sleep(random.uniform(1, 3))
            if random.random() < chance:
                fish = pb.Fish(
                    fish_id=random.randint(1000, 9999),
                    fish_dna=f"DNA{random.randint(100000,999999)}",
                    fish_level=random.randint(1, 10)
                )
                state.add_fish_to_user(jwt, fish)
                print(f"[FISH] User {jwt} caught fish {fish.fish_id}")
                yield fish
                break
            else:
                print(f"[FISH] User {jwt} did not catch a fish.")
                # We continue loop until a fish is caught or client disconnects

    # ---------- CurrentUsers (server‑stream) ----------
    def CurrentUsers(self, request, context):
        previouscount = state.current_user_count()
        yield pb.CurrentUsersResponse(count=previouscount)
        while context.is_active():
            count = state.current_user_count()
            if previouscount != count:
                previouscount = count
                yield pb.CurrentUsersResponse(count=count)
            time.sleep(1.0)  # update every second

    # ---------- Inventory ----------
    def Inventory(self, request, context):
        fishes = state.get_all_fishes()
        return pb.InventoryResponse(fish=fishes)

    def GetImage(self, request, context):
        # Read the image file from the path stored in IMAGE_PATH
        try:
            with open(IMAGE_PATH, "rb") as f:
                image_bytes = f.read()
            return pb.ImageResponse(image_data=image_bytes)
        except FileNotFoundError:
            context.abort(grpc.StatusCode.NOT_FOUND, f"Image file {IMAGE_PATH} not found")

# ----------------------------------------------------------------------
# Server bootstrap
# ----------------------------------------------------------------------
def serve(port=50051, image_path="image.jpg"):          # <- accept an image path
    global IMAGE_PATH
    IMAGE_PATH = image_path  # set the global to the provided argument

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    grpc_stub.add_FishingServiceServicer_to_server(FishingService(), server)
    # Use the supplied port instead of hard‑coding it
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"FishingService gRPC server listening on port {port}…")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("Shutting down server…")
        server.stop(0)

if __name__ == "__main__":
    import sys
    # Read optional port and image path from command‑line; default to 50051 and "image.jpg" if omitted
    try:
        cmd_port = int(sys.argv[1])
    except (IndexError, ValueError):
        cmd_port = 50051
    try:
        cmd_image_path = sys.argv[2]
    except IndexError:
        cmd_image_path = "image.jpg"
    serve(cmd_port, cmd_image_path)
