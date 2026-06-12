ifneq ($(wildcard .venv/bin/python),)
PYTHON ?= .venv/bin/python
else
PYTHON ?= python3
endif
ifneq ($(wildcard .venv/bin/uv),)
UV ?= .venv/bin/uv
else
UV ?= uv
endif
OPA ?= opa
# Runner for validation scripts. Defaults to plain Python; the coverage
# target overrides it with an instrumented runner so validation targets are
# defined exactly once and stay in sync between `verify` and `coverage`.
PY_RUN ?= $(PYTHON)
PACKAGES := manifest events permissions traces playbooks demo replay oep_verify
POLICY_TEST_FILES := $(wildcard permissions/policy/*.rego)
COUNTERFACTUAL_POLICY_FILES := $(filter-out %_test.rego,$(wildcard permissions/policy/counterfactual/*.rego))
DEMO_STATE := demo/state/code_review_agent.sqlite
COVERAGE_DEMO_STATE ?= demo/state/code_review_agent.coverage.sqlite
COVERAGE_FAIL_UNDER ?= 95
COVERAGE_SOURCE := demo,events,integrations,manifest,permissions,playbooks,oep_verify,replay,traces,translations
DTR_INTEGRATION_DIR := integrations/decision-trace-reconstructor
DTR_SCENARIO ?= code_review_agent
DTR_SCENARIOS ?= $(shell $(PYTHON) -c "from oep_verify.scenarios import scenario_names; print(' '.join(scenario_names()))")

.PHONY: verify check-opa-dependency check-lock compile validate-manifest validate-events validate-human-review validate-permissions validate-demo validate-eval validate-traces validate-playbooks validate-bedrock validate-mcp validate-langgraph validate-replay-cli validate-counterfactual-replay check-replay-determinism validate-counterfactual-schema validate-v03-features validate-5surface-diff validate-cost-counterfactual validate-reserve-commit-release validate-cross-provider-drift validate-cache-substitution validate-identity-binding validate-composite validate-backward-compat check-docs check-permission-digests test test-policy coverage lint typecheck build-check sync-resources update-digests check-digests clean-state regen-dtr-jsonl check-dtr-jsonl validate-dtr

verify: check-opa-dependency check-lock compile validate-manifest validate-events validate-human-review test-policy validate-permissions validate-counterfactual-schema validate-v03-features check-permission-digests validate-demo validate-eval validate-traces validate-playbooks validate-bedrock validate-mcp validate-langgraph validate-replay-cli validate-counterfactual-replay check-replay-determinism check-dtr-jsonl check-docs build-check

check-opa-dependency:
	@command -v $(OPA) > /dev/null 2>&1 || (echo "Error: '$(OPA)' CLI is not installed or not on PATH. Install OPA CLI 1.x or set OPA=/path/to/opa." >&2; exit 1)

# Soft gate locally: warn-and-skip when uv is absent so dependency-light
# environments can still run `verify`; CI enforces lockfile freshness hard
# via `uv sync --locked`.
check-lock:
	@if command -v $(UV) > /dev/null 2>&1; then \
		$(UV) lock --check; \
	else \
		echo "Warning: 'uv' not found; skipping lockfile freshness check (CI enforces it via 'uv sync --locked')." >&2; \
	fi

compile:
	$(PYTHON) -m compileall -q $(PACKAGES)

validate-manifest:
	$(PY_RUN) manifest/scripts/check_release_manifest.py

validate-events:
	$(PY_RUN) events/scripts/check_agent_step_event.py

# Regenerates the committed human-review examples deterministically and
# verifies the reconstruct + tamper-evidence claims behind the schema.
validate-human-review:
	$(PY_RUN) events/scripts/demo_human_review_reconstruct.py

validate-permissions:
	$(PY_RUN) permissions/scripts/check_tool_permission_packet.py

check-permission-digests:
	$(PY_RUN) permissions/scripts/update_permission_digests.py --check

validate-demo:
	$(PY_RUN) demo/scripts/run_code_review_demo.py
	$(PY_RUN) demo/scripts/check_replay_state.py

validate-eval:
	$(PY_RUN) traces/scripts/check_eval_result.py

validate-traces:
	$(PY_RUN) traces/scripts/check_operational_trace.py

validate-playbooks:
	$(PY_RUN) playbooks/scripts/check_reconstruction_packet.py

validate-bedrock:
	$(PY_RUN) translations/bedrock/scripts/check_bedrock_translation.py

validate-mcp:
	$(PY_RUN) integrations/mcp/scripts/to_oep_permission.py

validate-langgraph:
	$(PY_RUN) integrations/langgraph/scripts/to_oep_permission.py

validate-replay-cli:
	OEP_REPLAY_MODE=read-only $(PY_RUN) -m oep_verify.cli replay pder_code_review_read_diff_0001 --field decision_id > /dev/null
	OEP_REPLAY_MODE=read-only $(PY_RUN) -m oep_verify.cli replay pder_code_review_read_diff_0001 --field policy_bundle_version > /dev/null
	OEP_REPLAY_MODE=counterfactual $(PY_RUN) -m oep_verify.cli replay pder_code_review_read_diff_0001 --counterfactual --policy-bundle permissions/policy/tool_permissions.rego --output-format json --replay-timestamp-utc 2026-05-23T00:00:00Z > /dev/null

validate-counterfactual-replay:
	$(PY_RUN) replay/scripts/check_counterfactual_replay.py --runs 2

check-replay-determinism:
	$(PY_RUN) replay/scripts/check_counterfactual_replay.py --runs 3 --temp-only --include-dtr

validate-counterfactual-schema:
	$(PY_RUN) replay/scripts/check_counterfactual_replay_schema.py

# Composite v0.3 gate: one process runs every check in check_v03_features.py.
# `verify` uses this target; the narrow validate-* targets below stay as
# focused aliases for local debugging and run the same script per check.
validate-v03-features:
	$(PY_RUN) replay/scripts/check_v03_features.py

validate-5surface-diff:
	$(PY_RUN) replay/scripts/check_v03_features.py --check 5surface

validate-cost-counterfactual:
	$(PY_RUN) replay/scripts/check_v03_features.py --check cost

validate-reserve-commit-release:
	$(PY_RUN) replay/scripts/check_v03_features.py --check reserve

validate-cross-provider-drift:
	$(PY_RUN) replay/scripts/check_v03_features.py --check cross-provider

validate-cache-substitution:
	$(PY_RUN) replay/scripts/check_v03_features.py --check cache

validate-identity-binding:
	$(PY_RUN) replay/scripts/check_v03_features.py --check identity

validate-composite:
	$(PY_RUN) replay/scripts/check_v03_features.py --check composite

validate-backward-compat:
	$(PY_RUN) replay/scripts/check_v03_features.py --check backward-compat

check-docs:
	$(PYTHON) scripts/check_public_docs.py

test:
	$(PYTHON) -m pytest -q

test-policy: check-opa-dependency
	$(OPA) test $(POLICY_TEST_FILES)
	@test -n "$(COUNTERFACTUAL_POLICY_FILES)" || (echo "No counterfactual policy files found."; exit 1)
	@set -e; \
	for policy_file in $(COUNTERFACTUAL_POLICY_FILES); do \
		test_file="$${policy_file%.rego}_test.rego"; \
		if [ ! -f "$$test_file" ]; then \
			echo "Missing counterfactual policy test file: $$test_file"; \
			exit 1; \
		fi; \
		$(OPA) test "$$policy_file" "$$test_file"; \
	done

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy manifest events permissions traces playbooks demo oep_verify replay tests translations integrations scripts

build-check:
	$(PYTHON) scripts/check_package_build.py

sync-resources:
	$(PYTHON) scripts/sync_packaged_resources.py

update-digests:
	$(PYTHON) manifest/scripts/update_manifest_digests.py
	$(PYTHON) permissions/scripts/update_permission_digests.py

check-digests:
	$(PY_RUN) manifest/scripts/update_manifest_digests.py --check
	$(PY_RUN) permissions/scripts/update_permission_digests.py --check

# Coverage re-runs the same validation targets as `verify` with PY_RUN
# overridden to an instrumented runner, so new validation targets only need
# to be added to the target lists below (no duplicated command lines).
# Targets whose scripts read OEP_DEMO_STATE_PATH run with the coverage demo
# state injected; everything else runs exactly as in `verify`.
COVERAGE_PY_RUN := $(PYTHON) -m coverage run -a --source=$(COVERAGE_SOURCE)
COVERAGE_TARGETS := check-digests validate-manifest validate-events validate-human-review validate-permissions validate-bedrock validate-mcp validate-langgraph validate-counterfactual-schema validate-v03-features validate-counterfactual-replay check-replay-determinism check-dtr-jsonl
COVERAGE_STATE_TARGETS := validate-demo validate-eval validate-traces validate-playbooks validate-replay-cli

coverage:
	rm -f $(COVERAGE_DEMO_STATE)
	$(PYTHON) -m coverage erase
	$(MAKE) test-policy OPA=$(OPA)
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(MAKE) $(COVERAGE_STATE_TARGETS) PY_RUN='$(COVERAGE_PY_RUN)'
	$(MAKE) $(COVERAGE_TARGETS) PY_RUN='$(COVERAGE_PY_RUN)'
	$(PYTHON) scripts/check_public_docs.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" -m pytest -q
	$(PYTHON) scripts/check_package_build.py
	$(PYTHON) -m coverage report --skip-empty --fail-under=$(COVERAGE_FAIL_UNDER)

clean-state:
	rm -f demo/state/*.sqlite demo/state/*.sqlite-wal demo/state/*.sqlite-shm demo/state/*.sqlite3 demo/state/*.sqlite3-wal demo/state/*.sqlite3-shm demo/state/*.db demo/state/*.db-wal demo/state/*.db-shm
	@if [ -d demo/counterfactual ]; then \
		find demo/counterfactual -type f \( \
			-name '*.sqlite' -o -name '*.sqlite-wal' -o -name '*.sqlite-shm' -o \
			-name '*.sqlite3' -o -name '*.sqlite3-wal' -o -name '*.sqlite3-shm' -o \
			-name '*.db' -o -name '*.db-wal' -o -name '*.db-shm' -o \
			-name '*.json' -o -name '*.jsonl' \
		\) -delete; \
		find demo/counterfactual -type d -empty -not -path demo/counterfactual -delete; \
	fi

# Regenerate the canonical DTR JSONL from the OEP example artefacts.
regen-dtr-jsonl:
	$(PYTHON) $(DTR_INTEGRATION_DIR)/scripts/to_dtr_jsonl.py \
		--scenario $(DTR_SCENARIO) \
		--out $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).jsonl

check-dtr-jsonl:
	@set -e; \
	tmp_dir=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	for scenario in $(DTR_SCENARIOS); do \
		out="$$tmp_dir/$$scenario.jsonl"; \
		$(PY_RUN) $(DTR_INTEGRATION_DIR)/scripts/to_dtr_jsonl.py \
			--scenario "$$scenario" \
			--out "$$out"; \
		diff -u "$(DTR_INTEGRATION_DIR)/$$scenario.jsonl" "$$out"; \
	done

# Validate the DTR integration end-to-end. Requires `decision-trace` v0.1.0+
# installed and on PATH (or override DTR=... explicitly).
DTR ?= decision-trace
validate-dtr: regen-dtr-jsonl
	$(DTR) validate generic-jsonl \
		--mapping $(DTR_INTEGRATION_DIR)/mapping.v0.yaml \
		--sample-from $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).jsonl
	$(DTR) ingest generic-jsonl \
		--from-file $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).jsonl \
		--mapping $(DTR_INTEGRATION_DIR)/mapping.v0.yaml \
		--scenario-id oep_$(DTR_SCENARIO) \
		--out $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).fragments.json
	$(DTR) reconstruct $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).fragments.json \
		--out $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).report \
		--jsonld
	@diff -q $(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).report/feasibility.json \
		$(DTR_INTEGRATION_DIR)/$(DTR_SCENARIO).expected_feasibility.json \
		&& echo "OK: $(DTR_SCENARIO) feasibility matches expected" \
		|| (echo "FAIL: $(DTR_SCENARIO) feasibility differs from expected"; exit 1)
