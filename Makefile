PYTHON ?= python3
OPA ?= opa
PACKAGES := manifest events permissions traces playbooks demo oep_verify
POLICY_TEST_FILES := $(wildcard permissions/policy/*.rego)
DEMO_STATE := demo/state/code_review_agent.sqlite
COVERAGE_DEMO_STATE ?= demo/state/code_review_agent.coverage.sqlite
COVERAGE_FAIL_UNDER ?= 95
COVERAGE_SOURCE := demo,events,integrations,manifest,permissions,playbooks,oep_verify,traces,translations
DTR_INTEGRATION_DIR := integrations/decision-trace-reconstructor
DTR_SCENARIO ?= code_review_agent
DTR_SCENARIOS ?= $(shell $(PYTHON) -c "from oep_verify.scenarios import scenario_names; print(' '.join(scenario_names()))")

.PHONY: verify compile validate-manifest validate-events validate-permissions validate-demo validate-eval validate-traces validate-playbooks validate-bedrock check-docs test test-policy coverage lint typecheck build-check update-digests check-digests clean-state regen-dtr-jsonl check-dtr-jsonl validate-dtr

verify: compile validate-manifest validate-events test-policy validate-permissions validate-demo validate-eval validate-traces validate-playbooks validate-bedrock check-dtr-jsonl check-docs build-check

compile:
	$(PYTHON) -m compileall -q $(PACKAGES)

validate-manifest:
	$(PYTHON) manifest/scripts/check_release_manifest.py

validate-events:
	$(PYTHON) events/scripts/check_agent_step_event.py

validate-permissions:
	$(PYTHON) permissions/scripts/check_tool_permission_packet.py

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

check-docs:
	$(PYTHON) scripts/check_public_docs.py

test:
	$(PYTHON) -m pytest -q

test-policy:
	$(OPA) test $(POLICY_TEST_FILES)

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy manifest events permissions traces playbooks demo oep_verify tests translations integrations scripts

build-check:
	$(PYTHON) scripts/check_package_build.py

update-digests:
	$(PYTHON) manifest/scripts/update_manifest_digests.py

check-digests:
	$(PYTHON) manifest/scripts/update_manifest_digests.py --check

coverage:
	rm -f $(COVERAGE_DEMO_STATE)
	$(PYTHON) -m coverage erase
	$(OPA) test $(POLICY_TEST_FILES)
	$(PYTHON) -m coverage run --source="$(COVERAGE_SOURCE)" manifest/scripts/update_manifest_digests.py --check
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" manifest/scripts/check_release_manifest.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" events/scripts/check_agent_step_event.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" permissions/scripts/check_tool_permission_packet.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" demo/scripts/run_code_review_demo.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" demo/scripts/check_replay_state.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" traces/scripts/check_eval_result.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" traces/scripts/check_operational_trace.py
	OEP_DEMO_STATE_PATH="$(COVERAGE_DEMO_STATE)" $(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" playbooks/scripts/check_reconstruction_packet.py
	$(PYTHON) -m coverage run -a --source="$(COVERAGE_SOURCE)" translations/bedrock/scripts/check_bedrock_translation.py
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
	rm -f $(DEMO_STATE)

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
