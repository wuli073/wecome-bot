# Broadcast Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Broadcast Phase 3 real import, rematch, draft-generation, review, and persistence behavior exactly as specified in `C:/Users/33031/Desktop/bot/docs/superpowers/specs/2026-07-03-broadcast-phase3-design.md`, without touching Runtime execution surfaces or Phase 4 scope.

**Architecture:** Extend the existing `src/langbot/pkg/broadcast/` domain with focused parser, processor, matcher, generator, repository, service, and router responsibilities instead of creating a parallel subsystem. Persist import batches, import rows, and drafts in the existing SQLAlchemy/Alembic stack, keep file parsing outside DB write transactions, and convert the Broadcast frontend import/review tabs from seeded mock state to scoped backend APIs while preserving localized error handling inside the broadcast-specific client/data-source layer.

**Tech Stack:** Python 3.11+, Quart, SQLAlchemy, Alembic, pytest, aiosqlite, asyncpg, React, TypeScript, Vite, Playwright, Sonner, Python `csv` standard library, one minimal XLSX parser dependency if the lockfile review confirms no existing reusable reader

---

## Fixed scope anchors

- Spec authority: `C:/Users/33031/Desktop/bot/docs/superpowers/specs/2026-07-03-broadcast-phase3-design.md`
- Baseline commit: `67ea3b479`
- Existing Alembic head: `0013_broadcast_rules`
- New migration must keep `down_revision = '0013_broadcast_rules'`
- New migration revision id must be `0014_broadcast_phase3` or another final id of length `<= 32`, with no branch split
- Do not modify: `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/0013_broadcast_rules.py`
- Do not modify or stage these existing untracked docs:
  - `C:/Users/33031/Desktop/bot/docs/superpowers/plans/2026-07-02-broadcast-phase2-persistence.md`
  - `C:/Users/33031/Desktop/bot/docs/superpowers/plans/2026-07-02-broadcast-usability-fixes.md`
  - `C:/Users/33031/Desktop/bot/docs/superpowers/plans/2026-07-02-broadcast-workspace-phase1.md`
  - `C:/Users/33031/Desktop/bot/docs/superpowers/specs/2026-07-02-broadcast-workspace-design.md`
- Do not introduce Phase 4 behavior, Runtime calls, `paste-draft`, or `send-draft`
- Do not save original upload binaries, full raw customer files, or log raw upload contents
- Do not change global `BaseHttpClient` behavior; keep broadcast error extraction local to `BackendClient.requestBroadcast()` and the broadcast data source

## Dependency conclusion to carry into implementation

- CSV parsing must use the Python standard library `csv` module.
- `pyproject.toml` and `uv.lock` currently include `pandas`, but no directly reusable XLSX reader such as `openpyxl` was found in the locked dependencies or current source usage.
- The implementation should not default to `pandas` for Phase 3 file parsing.
- The implementation should prefer a minimal dedicated XLSX reader dependency, with `openpyxl` as the planned candidate because it reads `.xlsx` without requiring `pandas`, supports plain cell-value access, and can be used in read-only/data-only mode without executing formulas, macros, or scripts.
- `.xls` remains unsupported.

## API inventory required by the spec

### Imports APIs

- `POST /api/v1/broadcast/imports`
  - Content type: `multipart/form-data`
  - Fields: `bot_uuid`, `connector_id`, `file`
  - Response: import batch summary + statistics + first-page preview rows
  - Frontend call site: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx` via `BroadcastDataSource` -> `BackendClient`
- `GET /api/v1/broadcast/imports`
  - Query: `bot_uuid`, `connector_id`
  - Response: import batch list
  - Frontend call site: import page batch selector/list
- `GET /api/v1/broadcast/imports/{import_id}`
  - Query: required `bot_uuid`, `connector_id`; extra filters `match_status`, `keyword`, `page`, `page_size`
  - Response: import batch detail + preview rows + stats
  - Frontend call site: import page detail pane/table
- `DELETE /api/v1/broadcast/imports/{import_id}`
  - Query: `bot_uuid`, `connector_id`
  - Response: `{ deleted: true }`
  - Frontend call site: import page batch actions
- `POST /api/v1/broadcast/imports/{import_id}/rematch`
  - JSON: `bot_uuid`, `connector_id`
  - Response: updated batch stats + `drafts_stale` + preview summary
  - Frontend call site: import page rematch action
- `POST /api/v1/broadcast/imports/{import_id}/generate-drafts`
  - JSON: `bot_uuid`, `connector_id`, `template_id`
  - Response: `total_group_count`, `pending_review_count`, `invalid_count`, `unmatched_group_count`
  - Frontend call site: import page template/generate action

### Drafts APIs

- `GET /api/v1/broadcast/drafts`
  - Query: required `bot_uuid`, `connector_id`; extra filters `import_batch_id`, `status`, `keyword`
  - Response: grouped or flat draft list with stale/invalid metadata required by review UI
  - Frontend call site: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- `GET /api/v1/broadcast/drafts/{draft_id}`
  - Query: `bot_uuid`, `connector_id`
  - Response: body, render variables, template snapshot, target conversation, error reason
  - Frontend call site: `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- `PUT /api/v1/broadcast/drafts/{draft_id}`
  - JSON: `bot_uuid`, `connector_id`, `draft_text`
  - Response: updated draft + localized message when ready edits fall back to `pending_review`
  - Frontend call site: `DraftDetail.tsx` save action
- `POST /api/v1/broadcast/drafts/batch-status`
  - JSON: `bot_uuid`, `connector_id`, `draft_ids`, `status`
  - Response: updated draft summary / updated rows
  - Frontend call site: `DraftQueue.tsx` confirm / revoke actions

---

### Task 1: Baseline audit and dependency confirmation

**目标**
- Freeze all implementation assumptions against the confirmed Phase 3 spec, existing broadcast architecture, migration chain, and dependency reality before any code change begins.

**前置依赖**
- None.

**修改文件**
- `C:/Users/33031/Desktop/bot/docs/superpowers/plans/2026-07-03-broadcast-phase3-implementation.md`

**新增文件**
- 无

**先编写的失败测试**
- 无；本任务只做审查与记录，不修改生产代码或测试代码。

**实现步骤**
- [ ] Record the current Alembic head, confirm that `0013_broadcast_rules` is the actual `down_revision` anchor, and lock the new revision id target to `0014_broadcast_phase3` unless a later conflict requires another `<=32` character id.
- [ ] Review `pyproject.toml`, `uv.lock`, and current source usage to confirm CSV will use the standard library, `.xls` stays unsupported, `pandas` will not be the default parser, and a minimal `.xlsx` dependency is needed only if no existing safe reader is available.
- [ ] List the exact backend files, test files, frontend files, and E2E fixtures that the implementation tasks are allowed to touch.
- [ ] Record the non-goals again inside this plan: no Runtime, no `paste-draft`, no `send-draft`, no global HTTP client changes, no raw upload persistence.

**验收标准**
- The plan names the actual current Alembic head and the actual `down_revision` source.
- The plan states one dependency conclusion for `.xlsx` parsing with no ambiguous branch.
- The plan’s allowed file paths match the existing repository layout.

**精确验证命令**
- `git rev-parse --short HEAD`
- `Get-Content -Raw C:/Users/33031/Desktop/bot/pyproject.toml`
- `Get-ChildItem C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions | Sort-Object Name`

**禁止改动**
- No production code.
- No test code.
- No dependency installation in this task.

**预期 git diff 范围**
- Plan document only.

---

### Task 2: ORM entity and migration failure tests

**目标**
- Add failing persistence tests that express the new Phase 3 schema, metadata registration, revision constraints, upgrade/downgrade behavior, and four FK deletion rules before any ORM or migration implementation starts.

**前置依赖**
- Task 1.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations.py`
- `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations_postgres.py`

**新增文件**
- 无

**先编写的失败测试**
- SQLite: assert `broadcast_import_batches`, `broadcast_import_rows`, and `broadcast_drafts` appear after `upgrade(head)`.
- SQLite: assert the new migration revision id length is `<= 32` and `down_revision == '0013_broadcast_rules'`.
- SQLite: assert new tables are present in `Base.metadata` and participate in `create_all()`.
- SQLite: assert `matched_rule_id` becomes `NULL` after deleting a `broadcast_group_rules` row.
- SQLite: assert `template_id` becomes `NULL` after deleting a `broadcast_templates` row.
- SQLite: assert deleting an import batch cascades to import rows.
- SQLite: assert deleting an import batch cascades to drafts.
- SQLite: assert downgrade removes the three new tables and returns the revision to `0013_broadcast_rules`.
- PostgreSQL: mirror the upgrade table-presence and downgrade-current-revision assertions.

**实现步骤**
- [ ] Extend `test_migrations.py` with failing tests for the three new tables, new indexes, new unique constraints, metadata registration, revision-id length, and the four FK behaviors.
- [ ] Extend `test_migrations_postgres.py` with failing tests for upgrade/downgrade round trips and table/FK presence on PostgreSQL.
- [ ] Keep the tests explicit about using the real Alembic script directory and the actual head instead of placeholder revisions.
- [ ] Run the focused SQLite migration tests and confirm they fail because Phase 3 schema objects do not exist yet.

**验收标准**
- All schema expectations are encoded in failing migration tests before ORM/migration implementation.
- The migration tests explicitly cover SQLite and PostgreSQL.
- The four FK deletion cases are each asserted separately.

**精确验证命令**
- `uv run pytest tests/integration/persistence/test_migrations.py -q`
- `uv run pytest tests/integration/persistence/test_migrations_postgres.py -q`

**禁止改动**
- No ORM implementation yet.
- No Alembic migration file yet.
- Do not modify `0013_broadcast_rules.py`.

**预期 git diff 范围**
- Migration integration tests only.

---

### Task 3: ORM entities and Phase 3 migration implementation

**目标**
- Implement the new SQLAlchemy models and Alembic migration that satisfy the failing persistence tests for import batches, import rows, and drafts.

**前置依赖**
- Task 2.

**修改文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/entity/persistence/broadcast.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/entity/persistence/__init__.py` if model registration requires explicit imports
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/__init__.py` only if import wiring is already expected there

**新增文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/persistence/alembic/versions/0014_broadcast_phase3.py`

**先编写的失败测试**
- Use the failing tests from Task 2; do not add implementation first.

**实现步骤**
- [ ] Add `BroadcastImportBatch`, `BroadcastImportRow`, and `BroadcastDraft` to `broadcast.py` with the exact fields, indexes, unique constraints, nullable rules, and FK delete actions from the spec.
- [ ] Keep `BroadcastDraft.draft_text` non-nullable while allowing empty-string values for system-generated invalid drafts.
- [ ] Ensure the new ORM classes are imported so `Base.metadata` includes them during tests, runtime startup, and Alembic autoload.
- [ ] Create `0014_broadcast_phase3.py` with `revision = '0014_broadcast_phase3'`, `down_revision = '0013_broadcast_rules'`, guarded `upgrade()` and `downgrade()`, SQLite/PostgreSQL-safe operations, and explicit index/constraint creation.
- [ ] Re-run migration tests until SQLite and PostgreSQL schema tests pass.

**验收标准**
- New tables exist with the exact spec fields and constraints.
- Migration upgrade/downgrade passes on SQLite and PostgreSQL.
- `draft_text` remains non-null at the schema level.
- `0013_broadcast_rules.py` remains unchanged.

**精确验证命令**
- `uv run pytest tests/integration/persistence/test_migrations.py -q`
- `uv run pytest tests/integration/persistence/test_migrations_postgres.py -q`

**禁止改动**
- No API or service logic yet.
- No parser logic yet.

**预期 git diff 范围**
- Broadcast ORM file and one new Alembic migration file.

---

### Task 4: CSV/XLSX parser failure tests

**目标**
- Capture the full parser contract in failing unit tests before implementing file parsing.

**前置依赖**
- Task 3.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_file_parser.py`

**新增文件**
- 无

**先编写的失败测试**
- CSV normal case with UTF-8 and UTF-8 BOM.
- XLSX normal case on first worksheet with recorded `worksheet_name`.
- Empty file, unreadable XLSX, unsupported extension, over-10MB file, over-10000 data rows.
- Empty header, duplicate header, duplicate-after-trim header.
- Header trim behavior, cell stringification, blank-row skipping, source row number preservation.
- No formula/macro/script execution assumptions in parsed output.
- `.xls` rejection.

**实现步骤**
- [ ] Create `test_file_parser.py` with focused fixtures that build CSV bytes and `.xlsx` bytes in memory.
- [ ] Add assertions for the normalized parser output shape: `file_type`, `worksheet_name`, `headers`, `rows[{source_row_number, raw_data}]`.
- [ ] Add negative-case assertions for every required Chinese parser error branch.
- [ ] Run the parser test file and confirm failure because the parser module does not exist yet.

**验收标准**
- Every file-format and header rule from the spec exists as a failing test.
- The test file proves `.xls` is unsupported.
- The test file encodes the no-formula/no-macro/no-script rule as plain-value reading expectations.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_file_parser.py -q`

**禁止改动**
- No parser implementation yet.
- No service implementation yet.

**预期 git diff 范围**
- New parser unit test file only.

---

### Task 5: CSV/XLSX parser implementation

**目标**
- Implement safe `.csv` / `.xlsx` parsing that passes the parser failure tests and stays outside DB transactions.

**前置依赖**
- Task 4.

**修改文件**
- `C:/Users/33031/Desktop/bot/pyproject.toml` only if the Task 1 dependency audit concluded a minimal `.xlsx` dependency must be added
- `C:/Users/33031/Desktop/bot/uv.lock` only if Task 1 concluded a new dependency must be locked

**新增文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/file_parser.py`

**先编写的失败测试**
- Use the failing tests from Task 4.

**实现步骤**
- [ ] Implement CSV parsing with the Python `csv` standard library, UTF-8 and UTF-8 BOM handling, header trimming, blank-row skipping, and source row numbering.
- [ ] Implement `.xlsx` parsing using the minimal approved dependency from Task 1, reading only the first worksheet, recording `worksheet_name`, and extracting plain cell values without executing formulas, macros, or scripts.
- [ ] Enforce file-size and row-count limits before returning parsed structures.
- [ ] Convert parser errors into broadcast-domain exceptions/messages suitable for the service/router layer.
- [ ] Re-run parser tests until green.

**验收标准**
- `file_parser.py` returns the exact normalized output shape from the spec.
- `.xlsx` support works without `pandas` as the default parser.
- `.xls` remains rejected.
- No DB writes happen in the parser.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_file_parser.py -q`

**禁止改动**
- No import persistence or service orchestration yet.
- Do not add `pandas`-based parsing paths as the default implementation.

**预期 git diff 范围**
- One new parser module, and dependency files only if the audit required them.

---

### Task 6: Import processor failure tests

**目标**
- Encode row classification, required-field validation, statistics formulas, and rematch prerequisite behavior in failing tests before implementing import processing logic.

**前置依赖**
- Task 5.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_import_processor.py`

**新增文件**
- 无

**先编写的失败测试**
- Upload-time missing `group_field` or missing mapped source fields.
- Rematch-time revalidation against the latest variable profile.
- Group-value extraction with trim and empty-to-invalid.
- `valid_rows + invalid_rows = total_rows`.
- `matched_rows + unmatched_rows + invalid_rows = total_rows`.
- Rows never counted twice.
- Whole-batch rematch rejection when current required fields are missing from imported raw data.

**实现步骤**
- [ ] Add focused unit tests for upload validation, rematch validation, row classification, and batch-stat math.
- [ ] Include explicit tests proving that rematch uses the latest `group_field` and latest mapping rules instead of historical config snapshots.
- [ ] Confirm test failure because `import_processor.py` does not exist yet.

**验收标准**
- The tests express every statistics and field-validation rule from Spec sections 8 and 9.
- Rematch rejection is encoded as whole-batch rejection, not silent row downgrading.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_import_processor.py -q`

**禁止改动**
- No processor implementation yet.

**预期 git diff 范围**
- New import-processor unit test file only.

---

### Task 7: Import processor implementation

**目标**
- Implement upload/rematch field validation, row classification, and batch statistics with no DB access hidden inside the processing logic.

**前置依赖**
- Task 6.

**修改文件**
- 无

**新增文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/import_processor.py`

**先编写的失败测试**
- Use the failing tests from Task 6.

**实现步骤**
- [ ] Implement config-aware validators for upload and rematch required fields.
- [ ] Implement `group_value` extraction from `raw_data[group_field]` with string conversion, trim, and empty-to-invalid handling.
- [ ] Implement row classification outputs that the repository/service can persist directly: `invalid`, `unmatched`, `matched`, plus `error_message` and per-row match fields.
- [ ] Implement deterministic batch-stat calculation from the classified rows.
- [ ] Re-run import-processor tests until green.

**验收标准**
- Processing logic exactly matches the spec formulas and rematch behavior.
- Missing-field rematch rejects the entire batch.
- No persistence or transaction code leaks into the processor.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_import_processor.py -q`

**禁止改动**
- No repository or API work yet.

**预期 git diff 范围**
- One new import-processor module.

---

### Task 8: Group matcher failure tests

**目标**
- Lock the matching priority, regex validation/cache behavior, enabled-rule filtering, and same-name fallback in failing tests.

**前置依赖**
- Task 7.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_group_matcher.py`

**新增文件**
- 无

**先编写的失败测试**
- `exact`, `contains`, `regex` matching.
- `priority desc`, tie-break `id asc`.
- skip disabled rules.
- regex compilation caching inside one matching run.
- fallback to stored group names when no rule matches.
- unmatched result when neither rules nor names match.

**实现步骤**
- [ ] Add focused matching tests with minimal fixtures representing rules and group-name lists.
- [ ] Add assertions that invalid regexes are rejected earlier and cached regex behavior does not change match results.
- [ ] Run the group matcher tests and confirm failure because the module does not exist yet.

**验收标准**
- The test file fully describes the priority and fallback contract.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_group_matcher.py -q`

**禁止改动**
- No matcher implementation yet.

**预期 git diff 范围**
- New group-matcher unit test file only.

---

### Task 9: Group matcher implementation

**目标**
- Implement deterministic group matching for import/rematch/draft generation.

**前置依赖**
- Task 8.

**修改文件**
- 无

**新增文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/group_matcher.py`

**先编写的失败测试**
- Use the failing tests from Task 8.

**实现步骤**
- [ ] Implement a matcher that accepts enabled rules already scoped to the current bot/connector and evaluates them in `priority desc, id asc` order.
- [ ] Compile regex expressions once per matching run and cache them locally.
- [ ] Fall back to exact same-name conversation matching when no rule hits.
- [ ] Return enough metadata for persistence: `match_status`, `matched_rule_id`, `matched_conversation_name`.
- [ ] Re-run the matcher tests until green.

**验收标准**
- Matching order and fallback exactly follow the spec.
- Regex caching is local and deterministic.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_group_matcher.py -q`

**禁止改动**
- No draft generation yet.

**预期 git diff 范围**
- One new group-matcher module.

---

### Task 10: Draft generator failure tests

**目标**
- Encode grouping, five merge modes, render-variable keys, invalid-body preservation rules, and duplicate-prevention behavior in failing tests.

**前置依赖**
- Task 9.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_draft_generator.py`

**新增文件**
- 无

**先编写的失败测试**
- grouping by latest `group_field` within one import batch.
- five merge modes: `first`, `lines`, `unique_lines`, `commas`, `unique_commas`.
- preserve first-seen order in unique modes.
- `render_variables` keys must be `variable_key` values, not `source_field`.
- unmatched group -> invalid draft with rendered body if renderable.
- missing variables -> invalid draft with preview body.
- residual placeholders -> invalid draft with preview body.
- full render failure -> invalid draft with `draft_text == ''` and populated `error_message`.
- `target_conversation_name = NULL` when unmatched.
- ready draft blocks regeneration.
- `(import_batch_id, group_value)` uniqueness expectation.

**实现步骤**
- [ ] Write the generator tests using minimal row/profile/template fixtures and explicit expected merged values.
- [ ] Include tests for the ready-edit rule’s downstream effect: regenerated drafts must not bypass prior `ready` drafts.
- [ ] Run the draft-generator tests and confirm failure because the generator module does not exist yet.

**验收标准**
- Every invalid-draft body rule appears as a failing test.
- All five merge modes are covered.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_draft_generator.py -q`

**禁止改动**
- No generator implementation yet.

**预期 git diff 范围**
- New draft-generator unit test file only.

---

### Task 11: Draft generator implementation

**目标**
- Implement grouping, variable merging, template rendering, invalid-draft body preservation, and generation summary counting.

**前置依赖**
- Task 10.

**修改文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/template_engine.py` if the existing helper needs a narrow extension for preview/failure reporting

**新增文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/draft_generator.py`

**先编写的失败测试**
- Use the failing tests from Task 10.

**实现步骤**
- [ ] Implement group aggregation that preserves source row order and source row numbers inside each import batch group.
- [ ] Implement the five merge modes and first-seen dedup rules.
- [ ] Build `render_variables` with `variable_key` keys only.
- [ ] Generate `pending_review` drafts for fully valid groups and `invalid` drafts for unmatched/missing-variable/residual-placeholder/full-render-failure groups.
- [ ] Apply the exact invalid-body rules from the spec: rendered body when renderable, preview body for missing/residual placeholders, empty string only on full render failure.
- [ ] Return generation summary counts: `total_group_count`, `pending_review_count`, `invalid_count`, `unmatched_group_count`.
- [ ] Re-run the generator tests until green.

**验收标准**
- Draft-generation logic exactly matches the final Spec wording for `invalid.draft_text` handling.
- Preview text is preserved when possible.
- Empty `draft_text` is limited to system-generated full render failure cases.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_draft_generator.py -q`

**禁止改动**
- No repository or API work in this task.

**预期 git diff 范围**
- One new draft-generator module and a small template-engine adjustment if strictly necessary.

---

### Task 12: Repository persistence failure tests

**目标**
- Add repository tests for import-batch, import-row, and draft CRUD/query/purge behavior before extending repository code.

**前置依赖**
- Task 11.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_repository.py`

**新增文件**
- 无

**先编写的失败测试**
- create/list/get/delete import batches scoped by `bot_uuid + connector_id`.
- create/list/update import rows with one explicit transaction connection.
- create/list/get/delete drafts with one explicit transaction connection.
- delete-and-rebuild drafts inside one transaction.
- batch status update rejects cross-scope IDs.
- queries for import detail pagination and draft filters.

**实现步骤**
- [ ] Extend `test_repository.py` with failing tests for the new persistence methods and connection-sharing expectations.
- [ ] Add assertions that write batches use the provided connection object rather than silently opening independent commits.
- [ ] Run the repository tests and confirm failure on missing methods.

**验收标准**
- Repository contract for Phase 3 persistence is fully expressed before implementation.
- Transaction connection reuse is explicitly tested.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_repository.py -q`

**禁止改动**
- No repository implementation yet.

**预期 git diff 范围**
- Repository unit tests only.

---

### Task 13: Repository persistence implementation

**目标**
- Extend `BroadcastRepository` to persist imports, rows, drafts, rematch updates, and batch status changes while preserving scoped queries and shared-connection writes.

**前置依赖**
- Task 12.

**修改文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/repository.py`

**新增文件**
- 无

**先编写的失败测试**
- Use the failing tests from Task 12.

**实现步骤**
- [ ] Add import-batch create/list/get/delete methods.
- [ ] Add import-row bulk insert, rematch update, and filtered detail query methods.
- [ ] Add draft bulk replace/list/get/update/batch-status methods.
- [ ] Make every write-path accept and use the caller-provided connection object so upload/rematch/generation/status-update transactions stay on one connection.
- [ ] Re-run repository tests until green.

**验收标准**
- Repository writes stay on the same passed connection.
- Queries enforce bot/connector scoping at the repository boundary.
- Draft replacement supports single-transaction delete-and-rebuild.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_repository.py -q`

**禁止改动**
- No router/frontend changes yet.

**预期 git diff 范围**
- Broadcast repository only.

---

### Task 14: Imports service and API failure tests

**目标**
- Add failing unit/integration tests for upload, list/detail/delete, rematch, generate-drafts, Chinese errors, and same-connection transaction orchestration.

**前置依赖**
- Task 13.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_routes.py`
- `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`

**新增文件**
- 无

**????????**
- multipart upload success/failure for CSV and XLSX.
- upload rejects unsupported file, empty file, over-size file, over-row-count file, missing variable profile, missing group field, missing required fields.
- upload immediately performs first-match classification with the latest variable profile, `group_field`, enabled group rules, and group-name list in the current scope.
- upload immediately extracts/cleans `group_value`, marks `invalid`, runs `exact / contains / regex`, applies same-name fallback, and persists `matched / unmatched / invalid` plus `matched_conversation_name` and `matched_rule_id`.
- upload first-match ignores disabled rules.
- first-match statistics satisfy `matched_rows + unmatched_rows + invalid_rows = total_rows`.
- first-match results persist and remain visible after refresh/list/detail reload, without requiring rematch first.
- rematch recomputes `group_value` from latest config and sets `drafts_stale` only when old drafts exist.
- rematch rejects whole batch when current config fields are missing from imported raw data.
- rematch blocked by any `ready` draft.
- generate-drafts blocked by any `ready` draft.
- generate-drafts summary count fields exactly match the spec.
- import delete cascades through DB behavior.
- integration tests for import list/detail pagination and filters.

**????**
- [ ] Extend unit service tests with failing upload/rematch/generation orchestration assertions, including rollback expectations.
- [ ] Extend route tests for multipart request parsing, Chinese error mapping, and status codes.
- [ ] Extend integration API tests for the new imports endpoints, upload-time first-match persistence, same-name fallback, disabled-rule exclusion, refresh persistence, and transaction-safe persistence behavior.
- [ ] Run the three focused test files and confirm failure before implementation.

**验收标准**
- Imports workflow tests exist at unit, route, and integration levels.
- Transaction rollback and same-connection behavior are explicitly asserted.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`

**禁止改动**
- No imports service/API implementation yet.

**预期 git diff 范围**
- Broadcast service tests, route tests, and API integration tests.

---

### Task 15: Imports service and API implementation

**目标**
- Implement the imports workflow in service/router layers using the parser, processor, matcher, generator, and repository modules.

**前置依赖**
- Task 14.

**修改文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/schemas.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`

**新增文件**
- 无

**先编写的失败测试**
- Use the failing tests from Task 14.

**????**
- [ ] Add broadcast-domain error codes/messages for every new imports failure branch in Chinese.
- [ ] Implement upload orchestration: validate scope, parse file outside transaction, load the latest variable profile / `group_field` / enabled group rules / group-name list for the current scope, execute first-match classification immediately, then open one DB write transaction to create batch/rows/stats.
- [ ] During first upload matching, extract and clean `group_value`, mark `invalid`, run `exact / contains / regex`, apply same-name fallback, and persist `matched / unmatched / invalid` plus `matched_conversation_name` and `matched_rule_id`.
- [ ] Ensure the import matching page can show real matched/unmatched/invalid results immediately after upload, without requiring a rematch action first.
- [ ] Implement import listing, detail querying, and delete flows.
- [ ] Implement rematch in one transaction: scope check, ready-draft guard, latest-config validation, row recomputation, matcher rerun, stats update, `drafts_stale` update.
- [ ] Implement generate-drafts in one transaction: ready-draft guard, template validation, delete-old-drafts/rebuild, update batch status and `drafts_stale = false`.
- [ ] Add/import new routes for all six imports endpoints, including multipart upload handling.
- [ ] Re-run focused unit/route/integration tests until green.

**验收标准**
- Parser work happens outside DB write transactions.
- Rematch/generate-drafts each use one connection and one transaction.
- Imports API exactly matches the request/response contract in the spec.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`

**禁止改动**
- No frontend implementation yet.
- No Runtime-related code.

**预期 git diff 范围**
- Broadcast errors, schemas, service, and router.

---

### Task 16: Drafts service and API failure tests

**目标**
- Add failing tests for draft list/detail, edit rules, ready-edit rollback, invalid-edit persistence, and batch status updates before implementing them.

**前置依赖**
- Task 15.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_service.py`
- `C:/Users/33031/Desktop/bot/tests/unit_tests/broadcast/test_routes.py`
- `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py`

**新增文件**
- 无

**先编写的失败测试**
- draft list and detail queries by scope and filters.
- edit `pending_review` keeps `pending_review`.
- edit `ready` changes to `pending_review` and returns `草稿内容已修改，请重新确认`.
- edit `invalid` keeps `invalid`.
- edit validation rejects empty/whitespace body only for user edits.
- invalid draft cannot be confirmed directly after editing.
- batch status allows only `pending_review -> ready` and `ready -> pending_review`.
- stale drafts cannot be confirmed.
- cross-scope `draft_ids` reject the whole batch.

**实现步骤**
- [ ] Extend service tests for all edit and status-transition rules.
- [ ] Extend route/integration tests for `GET /drafts`, `GET /drafts/{id}`, `PUT /drafts/{id}`, and `POST /drafts/batch-status`.
- [ ] Confirm these tests fail before touching draft API implementation.

**验收标准**
- Ready-edit fallback and invalid-edit persistence each have explicit failing tests.
- User-edit non-empty validation is distinct from system-generated invalid draft creation.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`

**禁止改动**
- No draft implementation yet.

**预期 git diff 范围**
- Existing broadcast unit/route/integration tests only.

---

### Task 17: Drafts service and API implementation

**目标**
- Implement draft querying, editing, and batch status updates exactly per the final Spec rules.

**前置依赖**
- Task 16.

**修改文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/schemas.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/service.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`

**新增文件**
- 无

**先编写的失败测试**
- Use the failing tests from Task 16.

**实现步骤**
- [ ] Implement draft list/detail service methods with scope filtering and the stale/invalid metadata needed by the frontend.
- [ ] Implement draft edit service logic so `pending_review` stays `pending_review`, `ready` auto-falls back to `pending_review`, `invalid` stays `invalid`, and the success response includes `草稿内容已修改，请重新确认` only for ready edits.
- [ ] Keep the “正文不能为空 / 不允许只包含空格” validation only on user-edit saves.
- [ ] Implement batch status updates in one transaction with full-scope validation and allowed-transition enforcement.
- [ ] Reject invalid or stale draft confirmation with the fixed Chinese messages from the spec.
- [ ] Re-run the draft-focused service/route/integration tests until green.

**验收标准**
- Ready edits always revoke confirmation.
- Invalid edits never make a draft confirmable.
- Draft status changes use one transaction and one connection.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`

**禁止改动**
- No frontend implementation yet.

**预期 git diff 范围**
- Broadcast errors, schemas, service, and router.

---

### Task 18: Frontend API types, BackendClient, and data-source failure tests/design checks

**目标**
- Define the frontend transport surface for imports and drafts before wiring page behavior.

**前置依赖**
- Task 17.

**修改文件**
- `C:/Users/33031/Desktop/bot/web/src/app/infra/entities/api/index.ts`
- `C:/Users/33031/Desktop/bot/web/src/app/infra/http/BackendClient.ts`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- `C:/Users/33031/Desktop/bot/web/tests/e2e/fixtures/langbot-api.ts`

**新增文件**
- 无

**先编写的失败测试**
- E2E fixture and/or TypeScript compile failures for the new imports/drafts calls and new response shapes.
- Mock routes for multipart upload, imports list/detail/delete/rematch/generate-drafts, and draft list/detail/edit/batch-status.

**实现步骤**
- [ ] Extend the API entity types with import batch, import row preview, draft detail/list, and batch-status payloads.
- [ ] Add `BackendClient` methods for all new imports and drafts endpoints, keeping multipart upload local to these methods and leaving `BaseHttpClient` unchanged.
- [ ] Extend `BroadcastDataSource` with methods that map API payloads into broadcast page models.
- [ ] Update the Playwright fixture mock server contract so frontend work can proceed against realistic responses.
- [ ] Run TypeScript/Playwright entry checks and confirm failures until the UI is wired.

**验收标准**
- All new API methods exist in `BackendClient` without changing global request semantics.
- Broadcast-specific error extraction remains local.
- Mock fixture contract matches the final backend response shapes.

**精确验证命令**
- `cd C:/Users/33031/Desktop/bot/web; pnpm exec tsc --noEmit`
- `cd C:/Users/33031/Desktop/bot/web; pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts --project chromium`

**禁止改动**
- No UI behavior rewrite yet beyond wiring types and transport.
- No global `BaseHttpClient` changes.

**预期 git diff 范围**
- Frontend API entity types, `BackendClient`, `BroadcastDataSource`, and E2E fixture.

---

### Task 19: Import matching page implementation

**目标**
- Replace the import tab’s mock-only behavior with real import batch, upload, preview, rematch, and generate-drafts workflows.

**前置依赖**
- Task 18.

**修改文件**
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/mockData.ts` only to remove or isolate now-obsolete import mock assumptions
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/utils.ts` if display helpers need extension
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`

**新增文件**
- 无

**先编写的失败测试**
- Use and extend the failing E2E coverage for upload CSV/XLSX, stats display, status filtering, rematch stale warning, and generate-drafts.

**实现步骤**
- [ ] Add batch list/detail state to `BroadcastWorkspace.tsx` and load it from the new data-source methods.
- [ ] Rebuild `ImportMatchingPanel.tsx` to support multipart upload, batch selection, preview rows, status counts, template selection, rematch, generate-drafts, and delete.
- [ ] Surface Chinese parser/import errors directly in the page using broadcast-local handling.
- [ ] Show `matched / unmatched / invalid` explicitly and never hide failed items.
- [ ] Show the stale warning only when `status = matched` and `drafts_stale = true`.
- [ ] Re-run the broadcast E2E spec until import-page scenarios pass.

**验收标准**
- The import page is backed by real API calls and real batch data.
- Multipart upload is used for file submission.
- No raw upload content is echoed into logs/UI beyond structured preview rows.

**精确验证命令**
- `cd C:/Users/33031/Desktop/bot/web; pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts --project chromium`

**禁止改动**
- No review-page final behavior in this task beyond navigation/loading prerequisites.
- No Runtime calls.

**预期 git diff 范围**
- Broadcast import page components and local page state/data-source wiring.

---

### Task 20: Review/send page implementation

**目标**
- Replace the review tab’s mock draft queue/detail behavior with real draft list/detail/edit/status-update flows while keeping execution actions disabled.

**前置依赖**
- Task 19.

**修改文件**
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/types.ts`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/utils.ts`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`

**新增文件**
- 无

**先编写的失败测试**
- Use and extend the failing E2E coverage for draft filters, detail loading, save edit behavior, ready-edit rollback, invalid-edit persistence, confirm/revoke, stale disable, and batch confirm disable rules.

**实现步骤**
- [ ] Replace mock status groupings with real draft statuses: `pending_review`, `ready`, `invalid`, plus stale metadata.
- [ ] Wire draft list/detail queries from the backend.
- [ ] Wire draft save to the new `PUT /drafts/{id}` API and update frontend state according to the response.
- [ ] When a ready draft is edited, immediately reflect `pending_review` in queue/detail and show `草稿内容已修改，请重新确认`.
- [ ] Keep invalid draft save possible but keep confirm actions disabled.
- [ ] Implement confirm/revoke and batch confirm via `POST /drafts/batch-status` while forbidding stale/invalid confirmations in UI.
- [ ] Keep all execution-related buttons disabled and non-networking.
- [ ] Re-run the broadcast E2E spec until review-page scenarios pass.

**验收标准**
- Ready edit auto-withdraw behavior is visible in both queue and detail.
- Invalid edit never enables confirm.
- No Runtime, `paste-draft`, or `send-draft` request is sent from the review page.

**精确验证命令**
- `cd C:/Users/33031/Desktop/bot/web; pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts --project chromium`

**禁止改动**
- Do not enable execution features.
- Do not add Phase 4 actions.

**预期 git diff 范围**
- Broadcast draft queue/detail components and shared workspace state.

---

### Task 21: Chinese errors and interaction-state consolidation

**目标**
- Close the remaining UX and error-state gaps so Chinese user-facing messaging and disable-state logic match the spec exactly.

**前置依赖**
- Task 20.

**修改文件**
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/broadcast/errors.py`
- `C:/Users/33031/Desktop/bot/src/langbot/pkg/api/http/controller/groups/broadcast.py`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftQueue.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/components/drafts/DraftDetail.tsx`
- `C:/Users/33031/Desktop/bot/web/src/app/home/broadcast/utils.ts`

**新增文件**
- 无

**先编写的失败测试**
- Route/API assertions for final Chinese `message/details` coverage.
- E2E assertions for stale warning, ready-edit success toast/message, invalid disable states, and absence of internal enum/API/runtime strings in the visible UI.

**实现步骤**
- [ ] Normalize backend `message/details` coverage for every imports/drafts failure branch listed in the spec.
- [ ] Normalize frontend toast/banner/inline error handling so broadcast pages show only the localized messages intended for end users.
- [ ] Audit visible labels to avoid raw JSON field names, database enum names, Runtime wording, or internal error codes in primary UI.
- [ ] Re-run unit/route/integration/E2E checks that cover these user-visible states.

**验收标准**
- Chinese user-facing messages are complete and consistent.
- Ready edit rollback and stale/invalid disable states are reflected in both behavior and messaging.
- Broadcast-specific error handling remains local; no global HTTP behavior changes.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`
- `cd C:/Users/33031/Desktop/bot/web; pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts --project chromium`

**禁止改动**
- No new feature scope.
- No Runtime hooks.

**预期 git diff 范围**
- Broadcast errors/router plus broadcast frontend components/utilities.

---

### Task 22: E2E, migration, integration, and final acceptance verification

**目标**
- Run the full targeted verification stack for Phase 3 and close any remaining spec-to-test gaps without broad unrelated refactors.

**前置依赖**
- Tasks 1-21.

**修改文件**
- `C:/Users/33031/Desktop/bot/tests/integration/api/test_broadcast.py` only if a verified final coverage gap remains
- `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations.py` only if a verified final coverage gap remains
- `C:/Users/33031/Desktop/bot/tests/integration/persistence/test_migrations_postgres.py` only if a verified final coverage gap remains
- `C:/Users/33031/Desktop/bot/web/tests/e2e/broadcast-workspace.spec.ts` only if a verified final coverage gap remains
- `C:/Users/33031/Desktop/bot/web/tests/e2e/fixtures/langbot-api.ts` only if a verified final coverage gap remains

**新增文件**
- 无

**先编写的失败测试**
- Any remaining missing acceptance assertion discovered during the final coverage audit must be written first before code changes.

**实现步骤**
- [ ] Run all focused broadcast unit tests.
- [ ] Run all focused broadcast integration/API tests.
- [ ] Run SQLite migration tests.
- [ ] Run PostgreSQL migration tests when `TEST_POSTGRES_URL` is available.
- [ ] Run the broadcast Playwright E2E spec.
- [ ] Map every acceptance bullet from the spec to at least one passing test and add a final failing test first if any bullet is uncovered.
- [ ] Fix only the directly verified issues needed to make the full targeted suite pass.

**验收标准**
- Every spec acceptance bullet has at least one test mapping.
- Every shipped Phase 3 production capability was introduced by failing tests first.
- Final verification confirms no Runtime, `paste-draft`, `send-draft`, or Phase 4 behavior is present.

**精确验证命令**
- `uv run pytest tests/unit_tests/broadcast/test_file_parser.py tests/unit_tests/broadcast/test_import_processor.py tests/unit_tests/broadcast/test_group_matcher.py tests/unit_tests/broadcast/test_draft_generator.py tests/unit_tests/broadcast/test_repository.py tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py -q`
- `uv run pytest tests/integration/api/test_broadcast.py -q`
- `uv run pytest tests/integration/persistence/test_migrations.py -q`
- `$env:TEST_POSTGRES_URL='postgresql+asyncpg://user:pass@localhost:5432/test_db'; uv run pytest tests/integration/persistence/test_migrations_postgres.py -q`
- `cd C:/Users/33031/Desktop/bot/web; pnpm exec playwright test tests/e2e/broadcast-workspace.spec.ts --project chromium`

**禁止改动**
- No broad cleanup outside broadcast Phase 3 files.
- No new scope beyond the accepted Spec.

**预期 git diff 范围**
- Only directly relevant broadcast Phase 3 files already named in earlier tasks.

---

## Final self-check matrix for implementers

- Every Spec acceptance item is covered by at least one task above.
- Every production capability follows: failing test -> minimal implementation -> focused test -> necessary refactor -> test again.
- Transaction tasks explicitly require one shared DB connection for each upload, rematch, generate/regenerate, batch-status update, and delete flow.
- Ready-edit auto-withdraw is required in both backend and frontend tasks.
- Invalid-draft body rules are consistent across generator, drafts API, frontend review, tests, and acceptance steps.
- No Task introduces Phase 4, Runtime, `paste-draft`, or `send-draft`.
- All file paths match the current repository layout.
- All validation commands are directly runnable in PowerShell.
