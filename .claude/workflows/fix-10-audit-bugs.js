export const meta = {
  name: 'fix-10-audit-bugs',
  description: 'Fix 10 hidden bugs from code audit across 5 files',
  phases: [
    { title: 'Fix-llm_client', detail: 'Bug A,B,G,I in utils/llm_client.py' },
    { title: 'Fix-base_agent', detail: 'Bug D,E in agents/base_agent.py' },
    { title: 'Fix-pipeline', detail: 'Bug F in orchestrator/pipeline.py' },
    { title: 'Fix-timeout_test', detail: 'Bug C,H in tests/test_timeout_boundary.py' },
    { title: 'Fix-logger', detail: 'Bug J in utils/logger.py' },
    { title: 'Test', detail: 'Run full test suite' },
    { title: 'Review', detail: 'Adversarial review of all changes' },
  ],
}

const fileTasks = [
  {
    file: 'utils/llm_client.py',
    phase: 'Fix-llm_client',
    label: 'fix-llm-client',
    prompt: 'Fix 4 bugs in talent-compass/utils/llm_client.py. Read the file first.\n\n' +
      'Bug A (line ~166-171): call_llm_json schema validation failure returns both error AND content. ' +
      'The return has error non-null but content also has parsed data. This breaks format contract. ' +
      'Fix: set "content": null in the schema validation failure return path.\n\n' +
      'Bug B (line ~144-150): call_llm_json JSON parse failure adds extra "raw_content" key not in other paths. ' +
      'Three return paths must have identical top-level keys. Fix: add "raw_content": null to the success path ' +
      'and schema-fail path so all three paths have identical keys: content, error, usage, model, raw_content.\n\n' +
      'Bug G (line ~104): call_llm() returns content="" on valid empty LLM response, but callers check truthiness. ' +
      'Fix: add a doc comment noting callers must check error field, not content truthiness.\n\n' +
      'Bug I (line ~57-58): _client = None before _client = OpenAI(...) is dead code. Remove the redundant line.',
  },
  {
    file: 'agents/base_agent.py',
    phase: 'Fix-base_agent',
    label: 'fix-base-agent',
    prompt: 'Fix 2 bugs in talent-compass/agents/base_agent.py. Read the file first.\n\n' +
      'Bug D (lines ~100-110, ~126-136): run() has three return paths. F-104 added data_lineage to success path only. ' +
      'The VALIDATION FAILURE path and EXCEPTION path both lack data_lineage injection. Violates CLAUDE.md D4. ' +
      'Fix: add data_lineage to metadata in BOTH error paths: ' +
      '{"model": "", "timestamp": datetime.now(timezone.utc).isoformat(), "audit_status": "pending"}\n\n' +
      'Bug E (line ~141): run() does "if \"metadata\" not in result: result[\"metadata\"] = {}". ' +
      'If execute() returns non-dict, this throws TypeError. If dict but no "status" key, pipeline crashes. ' +
      'Fix: after execute(), add guard: if not isinstance(result, dict), wrap as error dict. ' +
      'If dict but no "status" key, inject "status": "success".',
  },
  {
    file: 'orchestrator/pipeline.py',
    phase: 'Fix-pipeline',
    label: 'fix-pipeline',
    prompt: 'Fix 1 bug in talent-compass/orchestrator/pipeline.py. Read the file first.\n\n' +
      'Bug F: _execute_with_timeout constructs return dicts manually in timeout path (line ~152-161) ' +
      'and exception path (line ~170-179). These bypass BaseAgent.run() which normally injects data_lineage. ' +
      'Fix: add data_lineage to metadata in BOTH paths: ' +
      '{"model": "", "timestamp": datetime.now().isoformat(), "audit_status": "pending"}\n' +
      'datetime is already imported at file top. Use datetime.now().isoformat().',
  },
  {
    file: 'tests/test_timeout_boundary.py',
    phase: 'Fix-timeout_test',
    label: 'fix-timeout-test',
    prompt: 'Fix 2 bugs in talent-compass/tests/test_timeout_boundary.py. Read the file first.\n\n' +
      'Bug C: _HangingAgent.execute() uses time.sleep() for timeout testing, violating CLAUDE.md D5: ' +
      '"test timeout with blocking I/O, not time.sleep(). sleep is cooperative; real LLM deadlocks never check cancel flag."\n' +
      'Fix steps:\n' +
      '1. Add "import socket" at top of file.\n' +
      '2. Replace time.sleep(0.1) loop with socket-based blocking: try connecting to unroutable IP 10.255.255.1:1 with 0.1s socket timeout per attempt. Still check cancel_event between attempts.\n' +
      '3. Add new test "test_hard_timeout_with_real_blocking" that creates an agent doing PURE blocking I/O ' +
      'WITHOUT checking cancel_event (single long socket.connect with no timeout loop). This verifies the hard timeout truly works. ' +
      'Expected: degraded status from hard timeout, not cancelled=true.\n\n' +
      'Bug H (lines 59,83,121): Uses hardcoded output_dir="data/intermediate" instead of tmp_path. ' +
      'Fix: use str(tmp_path) for output_dir in all three PipelineRunner calls. ' +
      'Add tmp_path parameter to test_cancel_event_propagates_to_agent which lacks it.',
  },
  {
    file: 'utils/logger.py',
    phase: 'Fix-logger',
    label: 'fix-logger',
    prompt: 'Fix 1 bug in talent-compass/utils/logger.py. Read the file first.\n\n' +
      'Bug J: setup_logger() default log_dir="logs" is CWD-relative. config.py already has LOG_DIR as absolute path. ' +
      'Fix: use a late import inside the function body to get config.LOG_DIR, then use str(config.LOG_DIR) ' +
      'as the default value for log_dir parameter. This avoids circular import issues.',
  },
]

// Phase 1-5: Fix bugs per-file via pipeline
const fixResults = await pipeline(
  fileTasks,
  function(task) { return agent(task.prompt, { label: task.label, phase: task.phase }) }
)

// Phase 6: Run tests
phase('Test')
const testResult = await agent(
  'Run the full test suite for talent-compass:\n' +
  '1. cd D:/workplace/talent-compass && python -m pytest tests/ -v\n' +
  '2. If any tests fail, read the failing test and modified source to diagnose.\n' +
  '3. Fix test issues if needed to match new behavior.\n' +
  '4. Re-run until all tests pass.\n' +
  '5. Report final pass/fail counts.',
  { label: 'run-all-tests' }
)

// Phase 7: Adversarial review
phase('Review')
const reviewResult = await agent(
  'Adversarial review of ALL changes to fix 10 bugs across 5 files in talent-compass:\n' +
  '- utils/llm_client.py (Bug A: schema fail content=null; Bug B: raw_content key consistency; Bug G: doc comment; Bug I: dead code removal)\n' +
  '- agents/base_agent.py (Bug D: data_lineage in error paths; Bug E: result type guard)\n' +
  '- orchestrator/pipeline.py (Bug F: data_lineage in timeout/exception paths)\n' +
  '- tests/test_timeout_boundary.py (Bug C: socket blocking; Bug H: tmp_path)\n' +
  '- utils/logger.py (Bug J: config.LOG_DIR default)\n\n' +
  'For EACH change: (1) Read the modified file, find the exact diff. ' +
  '(2) Construct a scenario where the fix fails or introduces a new bug. ' +
  '(3) Verify edge cases: null, empty, unexpected types. ' +
  '(4) For Bug C especially: verify socket-based test ACTUALLY tests real blocking behavior.\n' +
  'Report which fixes are solid and which need adjustment.',
  { label: 'adversarial-review' }
)

return { fixCount: fixResults.length, testResult: testResult, reviewResult: reviewResult }
