#!/usr/bin/env bash
# R97: start llama-server with each setting below in turn and time it with `imageskin time-llm`,
# which adds a row for each to one table (llm-settings.md in the results folder).
#
# On the hosted machine, from the deploy folder (the app keeps running; its own llama-server is
# stopped meanwhile, so chat replies wait until the end):
#   bash ../experiments/speed/llama_settings.sh docker
# In a cloud session or on a laptop, with a llama-server built or installed and the models in
# MODELS (the .gguf files named below):
#   LLAMA_SERVER=~/llama.cpp/build/bin/llama-server MODELS=~/models \
#     bash experiments/speed/llama_settings.sh local
# A second argument runs only the settings whose name contains it, such as "threads".
set -euo pipefail

MODE=${1:?say docker or local}
ONLY=${2:-}
HERE=$(cd "$(dirname "$0")" && pwd)
PORT=8081
BENCH=imageskin-llama-bench

# name|model|llama-server options. Each changes one thing from the first, which is what the app
# ran with before R97; the last is what deploy/compose.yaml runs with since.
SETTINGS=(
  "before: 4B Q4_K_M, 2 threads|4b-q4|--ctx-size 4096 --threads 2"
  "one slot|4b-q4|--ctx-size 4096 --threads 2 --parallel 1"
  "full SWA cache|4b-q4|--ctx-size 4096 --threads 2 --swa-full"
  "3 threads|4b-q4|--ctx-size 4096 --threads 3"
  "4 threads|4b-q4|--ctx-size 4096 --threads 4"
  "2 threads, 4 reading|4b-q4|--ctx-size 4096 --threads 2 --threads-batch 4"
  "flash attention on|4b-q4|--ctx-size 4096 --threads 2 --flash-attn on"
  "flash attention off|4b-q4|--ctx-size 4096 --threads 2 --flash-attn off"
  "batch 128|4b-q4|--ctx-size 4096 --threads 2 --ubatch-size 128"
  "batch 1024|4b-q4|--ctx-size 4096 --threads 2 --batch-size 1024 --ubatch-size 1024"
  "context 8192|4b-q4|--ctx-size 8192 --threads 2"
  "4B Q4_0|4b-q4_0|--ctx-size 4096 --threads 2"
  "4B Q8_0|4b-q8|--ctx-size 4096 --threads 2"
  "1B Q4_K_M|1b-q4|--ctx-size 4096 --threads 2"
  "chosen: 2 threads, 4 reading, full SWA cache|4b-q4|--ctx-size 4096 --threads 2 --threads-batch 4 --swa-full"
)

hf() { # the model, as llama-server's -hf downloads it (into the llama container's volume)
  case $1 in
    4b-q4) echo ggml-org/gemma-3-4b-it-GGUF ;;
    4b-q4_0) echo unsloth/gemma-3-4b-it-GGUF:Q4_0 ;;
    4b-q8) echo ggml-org/gemma-3-4b-it-GGUF:Q8_0 ;;
    1b-q4) echo ggml-org/gemma-3-1b-it-GGUF ;;
  esac
}

file() { # the model's file in MODELS, for a local llama-server
  case $1 in
    4b-q4) echo gemma-3-4b-it-Q4_K_M.gguf ;;
    4b-q4_0) echo gemma-3-4b-it-Q4_0.gguf ;;
    4b-q8) echo gemma-3-4b-it-Q8_0.gguf ;;
    1b-q4) echo gemma-3-1b-it-Q4_K_M.gguf ;;
  esac
}

cores() { # as many cores for the container as the setting's threads, so each is measured alone
  local options=$1 n
  n=$(sed -nE 's/.*--threads-batch ([0-9]+).*/\1/p' <<<"$options")
  [[ -z $n ]] && n=$(sed -nE 's/.*--threads ([0-9]+).*/\1/p' <<<"$options")
  echo "${n:-2}"
}

if [[ $MODE == docker ]]; then
  docker compose cp "$HERE/sample.pdf" app:/tmp/sample.pdf
  docker compose stop llama
  trap 'docker rm -f $BENCH >/dev/null 2>&1; docker compose start llama' EXIT
fi

for setting in "${SETTINGS[@]}"; do
  IFS='|' read -r name model options <<<"$setting"
  [[ -n $ONLY && $name != *"$ONLY"* ]] && continue
  echo "=== $name: $options"
  if [[ $MODE == docker ]]; then
    # shellcheck disable=SC2086 # the options are separate words
    docker run -d --name $BENCH --network imageskin_default --cpus "$(cores "$options")" \
      --memory 6g -e LLAMA_CACHE=/models -v imageskin_llama-models:/models \
      ghcr.io/ggml-org/llama.cpp:server \
      -hf "$(hf "$model")" --no-mmproj --host 0.0.0.0 --port 8080 $options >/dev/null
    docker compose exec -T app imageskin time-llm "$name" \
      --llm-url http://$BENCH:8080 --pdf /tmp/sample.pdf || echo "FAILED: $name"
    docker rm -f $BENCH >/dev/null
  else
    # shellcheck disable=SC2086
    "${LLAMA_SERVER:?set LLAMA_SERVER}" -m "${MODELS:?set MODELS}/$(file "$model")" \
      --host 127.0.0.1 --port $PORT $options >"/tmp/$BENCH.log" 2>&1 &
    server=$!
    imageskin time-llm "$name" --llm-url http://127.0.0.1:$PORT --pdf "$HERE/sample.pdf" \
      || echo "FAILED: $name"
    kill $server
    wait $server 2>/dev/null || true
  fi
done
