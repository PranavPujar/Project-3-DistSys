#!/usr/bin/env python3
# client.py

import sys
import time
import threading
from collections import deque

import grpc
import fishing_pb2 as pb
import fishing_pb2_grpc as grpc_stub

# ----------------------------------------------------------------------
# Helper: keep a stream open and allow us to send data later
# ----------------------------------------------------------------------
class UpdateLocationStream:
    def __init__(self, stub):
        self.stub = stub
        self._lock = threading.Lock()
        self._closed = False
        # A queue of (x, y) tuples to send
        self._queue = deque()
        # Start the streaming thread
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.response = None
        self.thread.start()

    def _run(self):
        # Build a generator that yields requests from the queue
        def request_gen():
            while not self._closed:
                if self._queue:
                    x, y = self._queue.popleft()
                    yield pb.UpdateLocationRequest(jwt=self.jwt, x=x, y=y)
                else:
                    time.sleep(0.1)

        # The first message must contain the JWT – we send it immediately
        request_iter = request_gen()
        try:
            self.response = next(self.stub.UpdateLocation(request_iter))
        except Exception as e:
            print(f"[UPDATE] Stream error: {e}")

    def send(self, x, y):
        with self._lock:
            if not self._closed:
                self._queue.append((x, y))
            else:
                print("[UPDATE] Stream already closed.")

    def close(self):
        with self._lock:
            self._closed = True

# ----------------------------------------------------------------------
# Main interactive client
# ----------------------------------------------------------------------
class FishingClient:
    def __init__(self, address="localhost:50051"):
        self.channel = grpc.insecure_channel(address)
        self.stub = grpc_stub.FishingServiceStub(self.channel)
        self.jwt = None
        self.update_stream = None
        self.current_users_thread = None

    # ---------- Commands ----------
    def cmd_login(self, args):
        if len(args) != 2:
            print("Usage: login <username> <password>")
            return
        username, password = args
        resp = self.stub.Login(pb.LoginRequest(username=username, password=password))
        self.jwt = resp.token
        print(f"[CLIENT] Logged in. JWT={self.jwt}")

    def cmd_update_location(self, args):
        if not self.jwt:
            print("[CLIENT] You must login first.")
            return
        if len(args) != 2:
            print("Usage: update_location <x> <y>")
            return
        x, y = map(float, args)
        if not self.update_stream:
            # First time: create stream
            self.update_stream = UpdateLocationStream(self.stub)
            self.update_stream.jwt = self.jwt
        self.update_stream.send(x, y)
        print(f"[CLIENT] Sent location ({x}, {y})")

    def cmd_start_fishing(self, args):
        if not self.jwt:
            print("[CLIENT] You must login first.")
            return
        def run():
            stream = self.stub.StartFishing(pb.StartFishingRequest(jwt=self.jwt))
            try:
                for fish in stream:
                    print(f"[CLIENT] Caught fish! id={fish.fish_id} dna={fish.fish_dna} level={fish.fish_level}")
            except grpc.RpcError as e:
                print(f"[CLIENT] Fishing stream error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def cmd_list_users(self, args):
        stream = self.stub.ListUsers(pb.EmptyRequest())
        for user in stream:
            print(f"[CLIENT] User {user.id} at ({user.x:.2f},{user.y:.2f}) is_fishing={user.is_fishing}")

    def cmd_current_users(self, args):
        if self.current_users_thread and self.current_users_thread.is_alive():
            print("[CLIENT] CurrentUsers stream already running.")
            return
        def run():
            stream = self.stub.CurrentUsers(pb.EmptyRequest())
            try:
                for resp in stream:
                    print(f"[CLIENT] Current users: {resp.count}")
            except grpc.RpcError as e:
                print(f"[CLIENT] CurrentUsers stream error: {e}")
        self.current_users_thread = threading.Thread(target=run, daemon=True)
        self.current_users_thread.start()

    def cmd_inventory(self, args):
        resp = self.stub.Inventory(pb.InventoryRequest())
        for fish in resp.fish:
            print(f"[CLIENT] Fish {fish.fish_id} dna={fish.fish_dna} level={fish.fish_level}")

    def cmd_get_image(self, args):
        resp = self.stub.GetImage(pb.ImageRequest())
        filename = "retrieved_image.jpg"
        with open(filename, "wb") as f:
            f.write(resp.image_data)
        print(f"[CLIENT] Saved image of {len(resp.image_data)} bytes to '{filename}'")

    def cmd_help(self, args):
        cmds = [
            "login <username> <password>",
            "update_location <x> <y>",
            "start_fishing",
            "list_users",
            "current_users",
            "inventory",
            "get_image",
            "help",
            "quit"
        ]
        print("Available commands:")
        for c in cmds:
            print(f"  {c}")

    # ---------- Main loop ----------
    def run(self):
        print("Fishing client – type 'help' for commands.")
        while True:
            try:
                line = input(">> ").strip()
            except EOFError:
                break
            if not line:
                continue
            parts = line.split()
            cmd, args = parts[0], parts[1:]
            if cmd == "quit":
                print("Exiting…")
                break
            elif cmd == "login":
                self.cmd_login(args)
            elif cmd == "update_location":
                self.cmd_update_location(args)
            elif cmd == "start_fishing":
                self.cmd_start_fishing(args)
            elif cmd == "list_users":
                self.cmd_list_users(args)
            elif cmd == "current_users":
                self.cmd_current_users(args)
            elif cmd == "inventory":
                self.cmd_inventory(args)
            elif cmd == "get_image":
                self.cmd_get_image(args)
            elif cmd == "help":
                self.cmd_help(args)
            else:
                print(f"Unknown command: {cmd}. Type 'help' for a list.")

        # Clean up streams
        if self.update_stream:
            self.update_stream.close()
        self.channel.close()


if __name__ == "__main__":
    client = FishingClient()
    client.run()
