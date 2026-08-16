#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <task-count|all> <concurrency> [sample-seed]" >&2
  exit 2
fi

task_count=$1
concurrency=$2
sample_seed=${3:-}
deep_swe_dir=${DEEPSWE_DIR:-"$HOME/work/deep-swe"}

if [[ $task_count != all && ! $task_count =~ ^[1-9][0-9]*$ ]]; then
  echo "Task count must be a positive integer or 'all'." >&2
  exit 2
fi
if [[ ! $concurrency =~ ^[1-9][0-9]*$ ]]; then
  echo "Concurrency must be a positive integer." >&2
  exit 2
fi
if [[ -n $sample_seed && ! $sample_seed =~ ^[0-9]+$ ]]; then
  echo "Sample seed must be a non-negative integer." >&2
  exit 2
fi

if [[ ! -d $deep_swe_dir/.git ]]; then
  mkdir -p "$(dirname "$deep_swe_dir")"
  git clone https://github.com/datacurve-ai/deep-swe.git "$deep_swe_dir"
fi

if ! command -v pier >/dev/null 2>&1; then
  uv tool install 'datacurve-pier>=0.3.1'
fi

if [[ ! -f $HOME/.modal.toml && -z ${MODAL_TOKEN_ID:-} ]]; then
  echo "Modal is not authenticated. Run: uvx modal token new" >&2
  exit 1
fi

if [[ -f $HOME/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.env"
  set +a
fi
if [[ -z ${BASETEN_API_KEY:-} ]]; then
  echo "BASETEN_API_KEY is not set in the environment or ~/.env." >&2
  exit 1
fi

probe_file=$(mktemp)
trap 'rm -f "$probe_file"' EXIT
probe_status=$(curl -sS -o "$probe_file" -w '%{http_code}' \
  -X POST 'https://inference.baseten.co/v1/responses' \
  -H "Authorization: Bearer $BASETEN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"moonshotai/Kimi-K3","input":"Reply OK","max_output_tokens":1}')
if [[ $probe_status != 200 ]]; then
  echo "Baseten K3 authentication probe failed with HTTP $probe_status." >&2
  exit 1
fi

export OPENAI_API_KEY=$BASETEN_API_KEY
export OPENAI_BASE_URL=https://inference.baseten.co/v1

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
job_name="kimi-k3-deepswe-${task_count}-c${concurrency}-${timestamp}"
args=(
  --path tasks
  --agent mini-swe-agent
  --model openai/moonshotai/Kimi-K3
  --env modal
  --n-concurrent "$concurrency"
  --max-retries 2
  --job-name "$job_name"
  --jobs-dir jobs
  --yes
)
if [[ $task_count != all ]]; then
  args+=(--n-tasks "$task_count")
fi
if [[ -n $sample_seed ]]; then
  args+=(--sample-seed "$sample_seed")
fi

echo "Starting $job_name in $deep_swe_dir"
cd "$deep_swe_dir"
time pier run "${args[@]}"
echo "Results: $deep_swe_dir/jobs/$job_name/result.json"
