#!/bin/bash

declare -A modules=(
  ["app.py"]=8501
  ["ambulance.py"]=8502
  ["hospitalapp.py"]=8503
  ["police.py"]=8504
)


for module in "${!modules[@]}"; do
  port=${modules[$module]}
  echo "Starting $module on port $port..."
  streamlit run "$module" --server.port="$port" &
  sleep 1
done

echo "Press Ctrl+C to stop the servers."
