#!/bin/bash

# Check if GEMINI_API_KEY is set or .env file exists
if [ -z "$GEMINI_API_KEY" ] && [ ! -f .env ]; then
    echo "Error: GEMINI_API_KEY is not set and .env file not found."
    echo "Please set it in .env or export it: export GEMINI_API_KEY='your-api-key'"
    exit 1
fi

python benchmark.py
