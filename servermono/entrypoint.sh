#!/bin/bash

# Start each server in the background
python server.py 50051 1.JPG &
python server.py 50052 2.JPG &
python server.py 50053 3.JPG &
python server.py 50054 4.JPG &
python server.py 50055 5.JPG &
python server.py 50056 6.JPG &

# Wait for all background processes to finish
wait
