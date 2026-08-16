---
name: DeepSWE Kimi K3 on Baseten
description: Run DeepSWE (DxB) evaluations against Baseten Kimi K3 on Modal, inspect Pier results, and measure org TPM correctly in VictoriaMetrics. Use for DeepSWE subsets, full runs, or K3 eval monitoring.
---

# DeepSWE Kimi K3 on Baseten

Use the public DeepSWE protocol: Pier `>=0.3.1`, Modal, and
`mini-swe-agent` against `openai/moonshotai/Kimi-K3`. This is not an exact
reproduction of a score produced with the unavailable `kimi-code` adapter.

## Run

1. Use `~/work/deep-swe`; clone `datacurve-ai/deep-swe` there if needed.
2. Ensure Modal is authenticated with `uvx modal profile list`. If needed, run
   `uvx modal token new`. When a remote tool buffers the URL until expiry, run
   it unbuffered in the background, redirect output to a file, and read the
   live URL from that file immediately.
3. Run `scripts/run.sh <task-count|all> <concurrency> [sample-seed]` from this
   skill directory. Start with one task, then a deterministic subset such as
   `scripts/run.sh 16 16 0`, before running all 113 tasks.
4. Keep each attempt under a new job name. Do not resume or score a run that
   failed authentication before inference.

The launcher installs Pier if absent, sources `~/.env`, explicitly maps
`BASETEN_API_KEY` to `OPENAI_API_KEY`, makes a real authenticated Responses API
probe, and creates a timestamped Pier job. Never select `KIMI_API_KEY`: it may
be present but returned 403 against Baseten in the observed setup. An empty
JSON probe is insufficient because request validation can return 400 before
authentication is checked.

Results are valid only when all trials complete and infrastructure errors are
zero. Read `<job>/result.json`; binary score is the count under reward `1`
divided by total trials. Modal warnings about `cidr_allowlist` and `Sandbox.ls`
deprecations are non-fatal.

## Monitor TPM

Identify the exact per-cluster VictoriaMetrics datasource each time. The
observed UIDs were:

- `VM-gcp-ue4-prod-2`: `P72446EC762F11D49`
- `VM-ali-apse8-prod-1`: `PECC799887E396D28`

For org `org-eb7383528d6c45fc9241602302a2835e`, use
`exported_namespace`, not `namespace`. Org-labeled K3 series used internal
model names, not the API model name:

- Ali: `kimi-k3-trtllm-disagg-dspark-0806`
- GCP: `k3-trtllm-disagg-dspark-0807-gcp`

Deduplicate repeated scrapes by pod. A plain `sum(rate(...))` overcounted the
same counters by up to 5x across three scrape jobs.

```promql
sum(
  max by (pod) (
    rate(llm_input_tokens_total{
      exported_namespace="org-eb7383528d6c45fc9241602302a2835e",
      model_name="kimi-k3-trtllm-disagg-dspark-0806"
    }[2m])
  )
) * 60
```

Replace `llm_input_tokens_total` with `llm_output_tokens_total` for output TPM.
Use `sum(max by (pod) (increase(...[window])))` for token totals. Verify the
deduplicated total against Pier's independent input/output token accounting.
Query both workload-plane clusters before concluding where traffic landed.

## Sanity Baseline

The validated 16-task run completed in 51m24s with no retries or infrastructure
errors: 12/16 reward, 169,568,025 input tokens, and 1,388,568 output tokens.
Treat this only as an operational baseline; use all 113 tasks for a comparable
benchmark score.
