#!/bin/bash

# Start the combined gRPC server (Fishing + Voting + Decision)
python -u server.py $FISHING_PORT $IMAGE_FILE
