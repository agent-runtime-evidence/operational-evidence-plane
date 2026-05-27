ifneq ($(wildcard .venv/bin/python),)
PYTHON ?= .venv/bin/python
else
PYTHON ?= python3
endif
OPA ?= opa
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

.PHONY: verify check-opa-dependency compile validate-manifest validate-events validate-permissions validate-demo validate-eval validate-traces validate-playbooks validate-bedrock validate-mcp validate-langgraph validate-replay-cli validate-counterfactual-replay check-replay-determinism validate-counterfactual-schema validate-5surface-diff validate-cost-counterfactual validate-reserve-commit-release validate-cross-provider-drift validate-cache-substitution validate-identity-binding validate-composite validate-backward-compat check-docs check-permission-digests test test-policy coverage lint typecheck build-check sync-resources update-digests check-digests clean-state regen-dtr-jsonl check-dtr-jsonl validate-dtr

verify: check-opa-dependency compile validate-manifest validate-events test-policy validate-permissions validate-counterfactual-schema validate-backward-compat validate-5surface-diff validate-cost-counterfactual validate-reserve-commit-release validate-cross-provider-drift validate-cache-substitution validate-identity-binding validate-composite check-permission-digests validate-demo validate-eval validate-traces validate-playbooks validate-bedrock validate-mcp validate-langgraph validate-replay-cli validate-counterfactual-replay check-replay-determinism check-dtr-jsonl check-docs build-check

check-opa-dependency:
	@command -v $(OPA) > /dev/null 2>&1 || (echo "Error: '$(OPA)' CLI is not installed or not on PATH. Install OPA CLI 1.x or set OPA=/path/to/opa." >&2; exit 1)

compile:
	$(PYTHON) -m compileall -q $(PACKAGES)

validate-manifest:
	$(PYTHON) manifest/scripts/check_release_manifest.py

validate-events:
	$(PYTHON) events/scripts/check_agent_step_event.py

validate-permissions:
	$(PYTHON) permissions/scripts/check_tool_permission_packet.py

check-permission-digests:
	$(PYTHON) permissions/scripts/update_permission_digests.py --check

validate-demo:
	$(PYTHON) demo/scripts/run_code_review_demo.py
	$(PYTHON) demo/scripts/check_replay_state.py

validate-eval:
	$(PYTHON) traces/scripts/check_eval_result.py

validate-traces:
	$(PYTHON) traces/scripts/check_operational_trace.py

validate-playbooks:
	$(PYTHON) playbooks/scripts/check_reconstruction_packet.py

validate-bedrock:
	$(PYTHON) translations/bedrock/scripts/check_bedrock_translation.py

validate-mcp:
	$(PYTHON) integrations/mcp/scripts/to_oep_permission.py

validate-langgraph:
	$(PYTHON) integrations/langgraph/scripts/to_oep_permission.py

validate-replay-cli:
	OEP_REPLAY_MODE=read-only $(PYTHON) -m oep_verify.cli replay pder_code_review_read_diff_0001 --field decision_id > /dev/null
	OEP_REPLAY_MODE=read-only $(PYTHON) -m oep_verify.cli replay pder_code_review_read_diff_0001 --field policy_bundle_version > /dev/null
	OEP_REPLAY_MODE=counterfactual $(PYTHON) -m oep_verify.cli replay pder_code_review_read_diff_0001 --counterfactual --policy-bundle permissions/policy/tool_permissions.rego --output-format json --replay-timestamp-utc 2026-05-23T00:00:00Z > /dev/null

validate-counterfactual-replay:
	$(PYTHON) replay/scripts/check_counterfactual_replay.py --runs 2

check-replay-determinism:
	$(PYTHON) replay/scripts/check_counterfactual_replay.py --runs 3 --temp-only --include-dtr

validate-counterfactual-schema:
	$(PYTHON) replay/scripts/check_counterfactual_replay_schema.py

validate-5surface-diff:
	$(PYTHON) replay/scripts/check_v03_features.py --check 5surface

validate-cost-counterfactual:
	$(PYTHON) replay/scripts/check_v03_features.py --check cost

validate-reserve-commit-release:
	$(PYTHON) replay/scripts/check_v03_features.py --check reserve

validate-cross-provider-drift:
	$(PYTHON) replay/scripts/check_v03_features.py --check cross-provider

validate-cache-substitution:
	$(PYTHON) replay/scripts/check_v03_features.py --check cache

validate-identity-binding:
	$(PYTHON) replay/scripts/check_v03_features.py --check identity

validate-composite:
	$(PYTHON) replay/scripts/check_v03_features.py --check composite

validate-backward-compat:
	$(PYTHON) replay/scripts/check_v03_features.py --check backward-compat

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
	$(PYTHON) manifest/scripts/update_manifest_digests.py --check
	$(PYTHON) permissions/scripts/update_permission_digests.py --check

coverage:
	rm -f $(COVERAGE_DEMO_STATE)
	$(PYTHON) -m coverage erase
	$(MAKE) test-policy OPA=$(OPA)
	$(PYTHON) -m coverage run --source="$(COVERAGE_SOURCE)" manifest/scripts/update_manifest_digests.py --check
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" permissions/scripts/update_permission_digests.py --check
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" manifest/scripts/check_release_manifest.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" events/scripts/check_agent_step_event.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" permissions/scripts/check_tool_permission_packet.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" demo/scripts/run_code_review_demo.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" demo/scripts/check_replay_state.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" traces/scripts/check_eval_result.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" traces/scripts/check_operational_trace.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" playbooks/scripts/check_reconstruction_packet.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" translations/bedrock/scripts/check_bedrock_translation.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" integrations/mcp/scripts/to_oep_permission.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" integrations/langgraph/scripts/to_oep_permission.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" OEP_REPLAY_MODE=read-only $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" -m oep_verify.cli replay pder_code_review_read_diff_0001 --field decision_id > /dev/null
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" replay/scripts/check_counterfactual_replay_schema.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" replay/scripts/check_v03_features.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" replay/scripts/check_counterfactual_replay.py --runs 2
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" replay/scripts/check_counterfactual_replay.py --runs 3 --temp-only --include-dtr
	$(PYTHON) scripts/check_public_docs.py
	@set -e; \
	tmp_dir=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	for scenario in $(DTR_SCENARIOS); do \
		out="$$tmp_dir/$$scenario.jsonl"; \
		$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" $(DTR_INTEGRATION_DIR)/scripts/to_dtr_jsonl.py \
			--scenario "$$scenario" \
			--out "$$out"; \
		diff -u "$(DTR_INTEGRATION_DIR)/$$scenario.jsonl" "$$out"; \
	done
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
		$(PYTHON) $(DTR_INTEGRATION_DIR)/scripts/to_dtr_jsonl.py \
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
