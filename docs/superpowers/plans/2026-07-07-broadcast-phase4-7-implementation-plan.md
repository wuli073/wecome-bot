# Broadcast Phase 4-7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add batch-scoped group field persistence, two-phase import field confirmation, new-customer candidate classification, atomic exact-rule bulk assignment with rematch, and the minimum frontend interactions required to drive the flow.

**Architecture:** Keep `group_field_used` as a batch fact on `broadcast_import_batches`, make the backend the only authority for field resolution and customer/rule state classification, and expose thin new APIs for candidate listing and atomic bulk assignment. Reuse the existing import/group/rule stack by extracting shared helpers for field resolution, exact-rule diagnostics, and rematch-in-transaction so single-rule editing, import rematch, and bulk assignment all share one semantic core.

**Tech Stack:** Quart, SQLAlchemy ORM, Alembic, Python 3.11, Vite + React Router 7 + TypeScript, shadcn/ui, Playwright, pytest.

---

## File map

**Backend models / schema**
- Modify: `src/langbot/pkg/entity/persistence/broadcast.py`
- Create: `src/langbot/pkg/persistence/alembic/versions/0022_bc_import_group_field_used.py`
- Test: `tests/integration/persistence/test_migrations.py`
- Test: `tests/integration/persistence/test_migrations_postgres.py`

**Backend service / repository / controller**
- Modify: `src/langbot/pkg/broadcast/errors.py`
- Modify: `src/langbot/pkg/broadcast/import_processor.py`
- Modify: `src/langbot/pkg/broadcast/repository.py`
- Modify: `src/langbot/pkg/broadcast/service.py`
- Modify: `src/langbot/pkg/api/http/controller/groups/broadcast.py`
- Test: `tests/unit_tests/broadcast/test_import_processor.py`
- Test: `tests/unit_tests/broadcast/test_repository.py`
- Test: `tests/unit_tests/broadcast/test_routes.py`
- Test: `tests/unit_tests/broadcast/test_service.py`
- Test: `tests/integration/api/test_broadcast.py`

**Frontend data contracts / orchestration**
- Modify: `web/src/app/infra/entities/api/index.ts`
- Modify: `web/src/app/home/broadcast/types.ts`
- Modify: `web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`

**Frontend import/rule UI**
- Modify: `web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- Modify: `web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupConversationSelector.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupRuleStatusBadge.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupMatchPreview.tsx`
- Create: `web/src/app/home/broadcast/components/import/BulkGroupAssignmentDialog.tsx`
- Modify: `web/src/i18n/locales/zh-Hans.ts`
- Modify: `web/src/i18n/locales/en-US.ts`

**Frontend E2E**
- Modify: `web/tests/e2e/broadcast-workspace.spec.ts`
- Modify: `web/tests/e2e/broadcast-import-feedback.spec.ts`
- Modify: `web/tests/e2e/fixtures/langbot-api.ts`

---

### Task 1: Add batch-scoped import field persistence

**Files:**
- Modify: `src/langbot/pkg/entity/persistence/broadcast.py`
- Create: `src/langbot/pkg/persistence/alembic/versions/0022_bc_import_group_field_used.py`
- Test: `tests/integration/persistence/test_migrations.py`
- Test: `tests/integration/persistence/test_migrations_postgres.py`

- [ ] **Step 1: Add the ORM columns to `BroadcastImportBatch`**

```python
class BroadcastImportBatch(Base):
    __tablename__ = 'broadcast_import_batches'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    bot_uuid = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    connector_id = sqlalchemy.Column(sqlalchemy.String(255), nullable=False, index=True)
    original_file_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=False)
    file_type = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    worksheet_name = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    status = sqlalchemy.Column(sqlalchemy.String(32), nullable=False)
    group_field_used = sqlalchemy.Column(sqlalchemy.String(255), nullable=True)
    group_field_source = sqlalchemy.Column(sqlalchemy.String(32), nullable=True)
```

- [ ] **Step 2: Create the Alembic migration with nullable columns only**

```python
revision = '0022_bc_imp_group_field'
down_revision = '0021_bc_target_conv_id'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('broadcast_import_batches')}
    with op.batch_alter_table('broadcast_import_batches') as batch_op:
        if 'group_field_used' not in columns:
            batch_op.add_column(sa.Column('group_field_used', sa.String(length=255), nullable=True))
        if 'group_field_source' not in columns:
            batch_op.add_column(sa.Column('group_field_source', sa.String(length=32), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('broadcast_import_batches')}
    with op.batch_alter_table('broadcast_import_batches') as batch_op:
        if 'group_field_source' in columns:
            batch_op.drop_column('group_field_source')
        if 'group_field_used' in columns:
            batch_op.drop_column('group_field_used')
```

- [ ] **Step 3: Extend migration assertions to cover both columns**

```python
columns = {column['name'] for column in inspector.get_columns('broadcast_import_batches')}
assert 'group_field_used' in columns
assert 'group_field_source' in columns
```

- [ ] **Step 4: Run the migration tests**

Run: `uv run pytest tests/integration/persistence/test_migrations.py -q`
Expected: PASS with the new revision applied successfully.

- [ ] **Step 5: Run the PostgreSQL migration test if `TEST_POSTGRES_URL` is configured**

Run: `uv run pytest tests/integration/persistence/test_migrations_postgres.py -q`
Expected: PASS; if the environment variable is absent, record the skip in the execution log.

---

### Task 2: Introduce shared import field resolution and new error codes

**Files:**
- Modify: `src/langbot/pkg/broadcast/errors.py`
- Modify: `src/langbot/pkg/broadcast/import_processor.py`
- Modify: `src/langbot/pkg/broadcast/service.py`
- Test: `tests/unit_tests/broadcast/test_import_processor.py`
- Test: `tests/unit_tests/broadcast/test_service.py`

- [ ] **Step 1: Add the new error codes**

```python
BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED = 'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED'
BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID = 'BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID'
BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE = 'BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE'
BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED = 'BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED'
```

- [ ] **Step 2: Add field alias constants and a minimal normalizer**

```python
GROUP_FIELD_ALIASES = (
    '用户名',
    '用户名称',
    '客户名称',
    '客户名',
    '客户',
    '姓名',
    '昵称',
)


def normalize_header_name(value: Any) -> str:
    return str(value or '').strip()
```

- [ ] **Step 3: Add a helper that resolves the upload field deterministically**

```python
def detect_import_group_field(
    *,
    headers: list[str],
    configured_group_field: str | None,
    group_field_override: str | None,
) -> tuple[str, str]:
    normalized_headers = [normalize_header_name(header) for header in headers]
    header_set = {header for header in normalized_headers if header}

    override = normalize_header_name(group_field_override)
    if override:
        if override not in header_set:
            raise BroadcastError(
                BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID,
                '当前确认的客户字段不存在于导入文件表头中。',
                details={'group_field_override': override, 'headers': normalized_headers},
            )
        return override, 'user_confirmed'

    if '用户名' in header_set:
        return '用户名', 'auto_detected'

    configured = normalize_header_name(configured_group_field)
    if configured and configured in header_set:
        return configured, 'configured'

    alias_hits = [alias for alias in GROUP_FIELD_ALIASES if alias in header_set]
    if len(alias_hits) == 1:
        return alias_hits[0], 'auto_detected'

    raise BroadcastError(
        BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
        '无法唯一确定客户分组字段，请确认后继续导入。',
        details={
            'headers': normalized_headers,
            'candidates': alias_hits,
            'configured_group_field': configured or None,
        },
    )
```

- [ ] **Step 4: Add a helper for persisted batch field resolution**

```python
def resolve_import_batch_group_field(batch, variable_profile) -> tuple[str, str]:
    batch_group_field = str(getattr(batch, 'group_field_used', '') or '').strip()
    batch_group_source = str(getattr(batch, 'group_field_source', '') or '').strip()
    if batch_group_field:
        return batch_group_field, batch_group_source or 'configured'

    fallback = str(getattr(variable_profile, 'group_field', '') or '').strip()
    if fallback:
        return fallback, 'legacy_fallback'

    raise BroadcastError(
        BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE,
        '历史导入批次未保存客户字段，且当前变量配置无法用于兼容处理。',
    )
```

- [ ] **Step 5: Update the import processor tests for override, auto-detect, ambiguity, and unresolvable fallback**

```python
assert detect_import_group_field(
    headers=['运单号', '用户名'],
    configured_group_field='客户名称',
    group_field_override=None,
) == ('用户名', 'auto_detected')

with pytest.raises(BroadcastError) as exc:
    detect_import_group_field(
        headers=['用户名', '客户名称'],
        configured_group_field='客户',
        group_field_override=None,
    )
assert exc.value.code == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
```

- [ ] **Step 6: Run the focused unit tests**

Run: `uv run pytest tests/unit_tests/broadcast/test_import_processor.py tests/unit_tests/broadcast/test_service.py -q`
Expected: PASS with new field-resolution branches covered.

---

### Task 3: Refactor upload and rematch to use batch-scoped fields consistently

**Files:**
- Modify: `src/langbot/pkg/broadcast/service.py`
- Modify: `src/langbot/pkg/broadcast/import_processor.py`
- Modify: `src/langbot/pkg/broadcast/repository.py`
- Test: `tests/unit_tests/broadcast/test_service.py`
- Test: `tests/integration/api/test_broadcast.py`

- [ ] **Step 1: Extend `upload_import()` to accept `group_field_override` and write the resolved field**

```python
async def upload_import(self, scope: dict[str, Any], file_payload: dict[str, Any]) -> dict[str, Any]:
    validated_scope = await self.validate_scope(scope)
    variable_profile = await self.repository.get_variable_profile(**validated_scope)
    parsed = await parse_import_file(file_payload['filename'], file_payload['body'])
    group_field_used, group_field_source = detect_import_group_field(
        headers=list(parsed['headers']),
        configured_group_field=getattr(variable_profile, 'group_field', None),
        group_field_override=file_payload.get('group_field_override'),
    )
    validate_import_headers(
        headers=list(parsed['headers']),
        variable_profile={'group_field': group_field_used, 'mapping_rules': list(variable_profile.mapping_rules or [])},
    )
    classified_rows = classify_import_rows(
        rows=list(parsed['rows']),
        group_field=group_field_used,
        match_resolver=lambda group_value: match_group(group_value=group_value, rules=serialized_rules, group_names=group_names),
    )
```

- [ ] **Step 2: Persist `group_field_used` and `group_field_source` when creating the batch**

```python
import_id = await self.repository.create_import_batch(
    conn,
    {
        **validated_scope,
        'original_file_name': parsed['original_file_name'],
        'file_type': parsed['file_type'],
        'worksheet_name': parsed['worksheet_name'],
        'status': 'imported',
        'group_field_used': group_field_used,
        'group_field_source': group_field_source,
        **stats,
    },
)
```

- [ ] **Step 3: Add an internal transaction-aware rematch helper and use it from `rematch_import()`**

```python
async def rematch_import_batch_in_transaction(self, conn, *, batch, scope, variable_profile) -> dict[str, Any]:
    group_field_used, group_field_source = resolve_import_batch_group_field(batch, variable_profile)
    existing_rows = await self.repository.list_import_rows(
        import_batch_id=int(batch.id),
        bot_uuid=scope['bot_uuid'],
        connector_id=scope['connector_id'],
        conn=conn,
    )
    headers = list((existing_rows[0].raw_data or {}).keys()) if existing_rows else []
    validate_rematch_headers(
        headers=headers,
        variable_profile={'group_field': group_field_used, 'mapping_rules': list(variable_profile.mapping_rules or [])},
    )
    classified_rows = classify_import_rows(
        rows=[{'source_row_number': row.source_row_number, 'raw_data': dict(row.raw_data or {})} for row in existing_rows],
        group_field=group_field_used,
        match_resolver=lambda group_value: match_group(group_value=group_value, rules=serialized_rules, group_names=group_names),
    )
    await self.repository.replace_import_rows(conn, import_batch_id=int(batch.id), rows=classified_rows)
    await self.repository.update_import_batch_counts(conn, import_batch_id=int(batch.id), stats=calculate_batch_stats(classified_rows))
    return {'group_field_used': group_field_used, 'group_field_source': group_field_source}
```

- [ ] **Step 4: Block legacy operations when the batch field cannot be resolved**

```python
with pytest.raises(BroadcastError) as exc:
    await service.rematch_import(import_id, scope)
assert exc.value.code == BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE
```

- [ ] **Step 5: Run rematch/import integration tests**

Run: `uv run pytest tests/unit_tests/broadcast/test_service.py tests/integration/api/test_broadcast.py -q`
Expected: PASS with upload and rematch both pinned to the persisted batch field.

---

### Task 4: Add exact-rule diagnostics, uniqueness checks, and shared state classification helpers

**Files:**
- Modify: `src/langbot/pkg/broadcast/service.py`
- Modify: `src/langbot/pkg/broadcast/repository.py`
- Modify: `src/langbot/pkg/broadcast/errors.py`
- Test: `tests/unit_tests/broadcast/test_service.py`
- Test: `tests/unit_tests/broadcast/test_repository.py`

- [ ] **Step 1: Centralize customer-name normalization for exact rules and candidates**

```python
def normalize_group_customer_name(value: Any) -> str:
    normalized = str(value or '').strip()
    return normalized
```

- [ ] **Step 2: Add a uniqueness validator for exact rules**

```python
async def validate_exact_rule_uniqueness(
    self,
    *,
    bot_uuid: str,
    connector_id: str,
    source_value: str,
    match_expression: str,
    exclude_rule_id: int | None = None,
    conn=None,
) -> None:
    duplicates = await self.repository.find_duplicate_exact_rules(
        bot_uuid=bot_uuid,
        connector_id=connector_id,
        source_value=normalize_group_customer_name(source_value),
        match_expression=normalize_group_customer_name(match_expression),
        exclude_rule_id=exclude_rule_id,
        conn=conn,
    )
    if duplicates:
        raise BroadcastError(BROADCAST_GROUP_RULE_DUPLICATE, '已存在相同客户名称的有效 exact 规则。')
```

- [ ] **Step 3: Expand the rule match preview payload to include candidate diagnostics**

```python
return {
    'matched': bool(final_match),
    'matched_rule_id': final_match.get('id') if final_match else None,
    'source_value': source_value,
    'match_type': final_match.get('match_type') if final_match else None,
    'target_conversation_id': final_match.get('target_conversation_id') if final_match else None,
    'target_conversation_name': final_match.get('target_conversation_name') if final_match else None,
    'candidate_count': len(candidate_rules),
    'candidate_rules': candidate_rules,
    'conflict': len(candidate_rules) > 1,
    'reason': reason,
}
```

- [ ] **Step 4: Reuse the helpers in create/update exact rule flows before writing**

```python
if normalized['match_type'] == 'exact':
    await self.validate_exact_rule_uniqueness(
        bot_uuid=validated_scope['bot_uuid'],
        connector_id=validated_scope['connector_id'],
        source_value=normalized['source_value'],
        match_expression=normalized['match_expression'],
        exclude_rule_id=rule_id if is_update else None,
        conn=conn,
    )
```

- [ ] **Step 5: Run unit tests for duplicate exact rules and diagnostics ordering**

Run: `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_repository.py -q`
Expected: PASS with exact duplicate creation blocked and preview candidates sorted exactly like formal matching.

---

### Task 5: Add the `group-rule-candidates` backend API

**Files:**
- Modify: `src/langbot/pkg/api/http/controller/groups/broadcast.py`
- Modify: `src/langbot/pkg/broadcast/repository.py`
- Modify: `src/langbot/pkg/broadcast/service.py`
- Modify: `src/langbot/pkg/broadcast/errors.py`
- Test: `tests/unit_tests/broadcast/test_routes.py`
- Test: `tests/unit_tests/broadcast/test_service.py`
- Test: `tests/integration/api/test_broadcast.py`

- [ ] **Step 1: Add the route under the existing import subresource style**

```python
@self.route('/imports/<int:import_id>/group-rule-candidates', methods=['GET'], auth_type=group.AuthType.USER_TOKEN)
async def import_group_rule_candidates(import_id: int) -> str:
    scope = await self.validate_scope(from_query=True)
    filters = {
        'status': str(quart.request.args.get('status') or '').strip() or 'new',
        'keyword': str(quart.request.args.get('keyword') or '').strip() or None,
        'page': int(quart.request.args.get('page')) if quart.request.args.get('page') else None,
        'page_size': int(quart.request.args.get('page_size')) if quart.request.args.get('page_size') else None,
    }
    data = await self.ap.broadcast_service.list_import_group_rule_candidates(import_id, scope, filters)
    return self.success(data=data)
```

- [ ] **Step 2: Build candidate items from current batch group summaries instead of reparsing the original file**

```python
summaries = await self.repository.list_all_import_group_summaries(
    import_batch_id=import_id,
    bot_uuid=validated_scope['bot_uuid'],
    connector_id=validated_scope['connector_id'],
    order_number_source_field=order_number_source_field,
)
items = [
    self.classify_group_rule_candidate(
        summary=summary,
        batch=batch,
        rules=rules,
        group_names=group_names,
    )
    for summary in summaries
]
```

- [ ] **Step 3: Return the agreed detail shape with `existing_rule_ids`, `existing_rules`, and `current_matched_rule`**

```python
candidate = {
    'group_key': group_key,
    'customer_name': customer_name,
    'raw_row_count': int(summary['raw_row_count'] or 0),
    'status': state.status,
    'reason': state.reason,
    'existing_rule_ids': [rule['id'] for rule in state.existing_rules],
    'existing_rules': state.existing_rules,
    'current_matched_rule': state.current_matched_rule,
    'current_target_conversation_id': state.current_target_conversation_id,
    'current_target_conversation_name': state.current_target_conversation_name,
    'current_match_type': state.current_match_type,
}
```

- [ ] **Step 4: Reject historical batches that cannot resolve their field**

```python
with pytest.raises(BroadcastError) as exc:
    await service.list_import_group_rule_candidates(import_id, scope, {'status': 'new'})
assert exc.value.code == BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE
```

- [ ] **Step 5: Run route and API tests for pagination, status filters, and legacy fallback**

Run: `uv run pytest tests/unit_tests/broadcast/test_routes.py tests/unit_tests/broadcast/test_service.py tests/integration/api/test_broadcast.py -q`
Expected: PASS with default `status=new`, correct totals, and one customer per normalized username.

---

### Task 6: Add atomic bulk exact-rule assignment with formal-match verification

**Files:**
- Modify: `src/langbot/pkg/api/http/controller/groups/broadcast.py`
- Modify: `src/langbot/pkg/broadcast/repository.py`
- Modify: `src/langbot/pkg/broadcast/service.py`
- Modify: `src/langbot/pkg/broadcast/errors.py`
- Test: `tests/unit_tests/broadcast/test_service.py`
- Test: `tests/unit_tests/broadcast/test_routes.py`
- Test: `tests/integration/api/test_broadcast.py`

- [ ] **Step 1: Add the bulk-assign route**

```python
@self.route('/imports/<int:import_id>/group-rules/bulk-assign', methods=['POST'], auth_type=group.AuthType.USER_TOKEN)
async def import_group_rules_bulk_assign(import_id: int) -> str:
    payload = await quart.request.get_json(silent=True) or {}
    scope = await self.validate_scope(from_query=False, payload=payload)
    data = await self.ap.broadcast_service.bulk_assign_import_group_rules(import_id, scope, payload)
    return self.success(data=data)
```

- [ ] **Step 2: Resolve customers by querying the current batch summaries, not by parsing `group_key` text**

```python
summary_by_group_key = {
    self._build_import_group_key(import_id, item.get('group_value')): item
    for item in summaries
}
summary = summary_by_group_key.get(group_key)
if summary is None:
    item_errors.append({'group_key': group_key, 'code': BROADCAST_IMPORT_GROUP_NOT_FOUND, 'message': '当前客户分组不存在或已被删除。'})
    continue
customer_name = normalize_group_customer_name(summary.get('group_value'))
```

- [ ] **Step 3: Perform all read-only validation before opening the write transaction**

```python
if not items:
    raise BroadcastError(BROADCAST_IMPORT_FILE_INVALID, '批量分配请求不能为空。')
if len({item['group_key'] for item in items}) != len(items):
    raise BroadcastError(BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED, '批量分配请求包含重复客户。', details={'items': item_errors})
# validate ready drafts, batch ownership, target conversations, current state == new, exact uniqueness precheck
```

- [ ] **Step 4: Insert rules, verify final formal matches with the same transaction connection, then rematch**

```python
async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
    created_rules = []
    for item in validated_items:
        rule_id = await self.repository.create_group_rule(
            conn,
            {
                **validated_scope,
                'source_value': item['customer_name'],
                'match_type': 'exact',
                'match_expression': item['customer_name'],
                'target_conversation_id': item['target_conversation_id'],
                'target_conversation_name': item['target_conversation_name'],
                'priority': item['priority'],
                'enabled': True,
            },
        )
        created_rules.append({'rule_id': rule_id, **item})

    verified_rules = await self.repository.list_group_rules(
        bot_uuid=validated_scope['bot_uuid'],
        connector_id=validated_scope['connector_id'],
    )
    for item in created_rules:
        diagnostic = build_group_rule_match_diagnostics(
            source_value=item['customer_name'],
            rules=verified_rules,
            group_names=group_names,
        )
        if diagnostic.final_rule_id != item['rule_id'] or diagnostic.final_target_conversation_id != item['target_conversation_id']:
            raise BroadcastError(
                BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED,
                '新建 exact 规则未能成为正式命中结果。',
                details={'items': [{'group_key': item['group_key'], 'customer_name': item['customer_name'], 'code': 'FORMAL_MATCH_CONFLICT', 'message': '存在更高优先级规则截获该客户。'}]},
            )

    await self.rematch_import_batch_in_transaction(
        conn,
        batch=batch,
        scope=validated_scope,
        variable_profile=variable_profile,
    )
```

- [ ] **Step 5: Return a top-level bulk failure code only for per-item validation/write conflicts**

```python
raise BroadcastError(
    BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED,
    '批量创建群规则失败。',
    details={'items': item_errors},
)
```

- [ ] **Step 6: Run service and integration tests for atomic rollback behavior**

Run: `uv run pytest tests/unit_tests/broadcast/test_service.py tests/unit_tests/broadcast/test_routes.py tests/integration/api/test_broadcast.py -q`
Expected: PASS; duplicate rule races, missing target IDs, and formal-match conflicts must roll back the entire batch.

---

### Task 7: Extend frontend types and data source methods

**Files:**
- Modify: `web/src/app/infra/entities/api/index.ts`
- Modify: `web/src/app/home/broadcast/types.ts`
- Modify: `web/src/app/home/broadcast/datasources/BroadcastDataSource.ts`
- Modify: `web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Test: `pnpm exec tsc --noEmit`

- [ ] **Step 1: Extend API and domain types for batch field metadata, candidate lists, and bulk assignment**

```ts
export type BroadcastImportGroupFieldSource =
  | 'configured'
  | 'auto_detected'
  | 'user_confirmed'
  | 'legacy_fallback';

export interface ApiBroadcastImportBatch {
  group_field_used?: string | null;
  group_field_source?: BroadcastImportGroupFieldSource | null;
}

export interface BroadcastImportBatch {
  groupFieldUsed?: string | null;
  groupFieldSource?: BroadcastImportGroupFieldSource | null;
}
```

- [ ] **Step 2: Add client-side shapes for field confirmation and new-customer candidates**

```ts
export interface BroadcastImportGroupFieldConfirmationDetails {
  headers: string[];
  candidates: string[];
  configuredGroupField: string | null;
  originalFileName: string;
}

export interface BroadcastGroupRuleCandidateItem {
  groupKey: string;
  customerName: string;
  rawRowCount: number;
  status: 'new' | 'configured' | 'needs_repair' | 'conflict' | 'invalid';
  reason: string | null;
  existingRuleIds: number[];
  existingRules: GroupRuleSummary[];
  currentMatchedRule: GroupRuleSummary | null;
  currentTargetConversationId?: string | null;
  currentTargetConversationName: string | null;
  currentMatchType: BroadcastGroupMatchType | null;
}
```

- [ ] **Step 3: Extend the data source methods**

```ts
uploadImport: (
  scope: BroadcastScope,
  file: File,
  options?: { groupFieldOverride?: string },
) => Promise<BroadcastImportBatch>;
getImportGroupRuleCandidates: (
  scope: BroadcastScope,
  importId: number,
  filters?: { status?: 'new' | 'configured' | 'needs_repair' | 'conflict' | 'invalid' | 'all'; keyword?: string; page?: number; pageSize?: number },
) => Promise<BroadcastGroupRuleCandidateList>;
bulkAssignImportGroupRules: (
  scope: BroadcastScope,
  importId: number,
  items: Array<{ groupKey: string; targetConversationId: string }>,
) => Promise<BroadcastBulkAssignResult>;
```

- [ ] **Step 4: Update `uploadImport()` to append `group_field_override` only when provided**

```ts
const formData = new FormData();
formData.append('bot_uuid', scope.botUuid);
formData.append('connector_id', scope.connectorId);
formData.append('file', file);
if (options?.groupFieldOverride?.trim()) {
  formData.append('group_field_override', options.groupFieldOverride.trim());
}
```

- [ ] **Step 5: Run TypeScript compilation**

Run: `pnpm exec tsc --noEmit`
Expected: PASS with no `any` fallbacks added for the new import/candidate/bulk-assign contracts.

---

### Task 8: Add import field confirmation and bulk assignment UI with minimal workspace changes

**Files:**
- Modify: `web/src/app/home/broadcast/components/BroadcastWorkspace.tsx`
- Modify: `web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx`
- Create: `web/src/app/home/broadcast/components/import/BulkGroupAssignmentDialog.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupConversationSelector.tsx`
- Modify: `web/src/i18n/locales/zh-Hans.ts`
- Modify: `web/src/i18n/locales/en-US.ts`
- Test: `pnpm exec eslint web/src/app/home/broadcast/components/BroadcastWorkspace.tsx web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx web/src/app/home/broadcast/components/import/BulkGroupAssignmentDialog.tsx web/src/app/home/broadcast/components/shared/GroupConversationSelector.tsx web/src/i18n/locales/zh-Hans.ts web/src/i18n/locales/en-US.ts`

- [ ] **Step 1: Add a dedicated field-confirmation state bundle in `ImportMatchingPanel`**

```ts
const [pendingImportFile, setPendingImportFile] = useState<File | null>(null);
const [groupFieldDialogOpen, setGroupFieldDialogOpen] = useState(false);
const [groupFieldHeaders, setGroupFieldHeaders] = useState<string[]>([]);
const [groupFieldCandidates, setGroupFieldCandidates] = useState<string[]>([]);
const [configuredGroupField, setConfiguredGroupField] = useState<string | null>(null);
const [selectedGroupField, setSelectedGroupField] = useState('');
```

- [ ] **Step 2: Capture the confirmation-required error in `BroadcastWorkspace` and preserve the same `File` object**

```ts
try {
  await dataSource.uploadImport(scope, file);
} catch (error) {
  if (isBackendErrorCode(error, 'BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED')) {
    setPendingImportConfirmation({
      file,
      details: readConfirmationDetails(error),
    });
    return;
  }
  throw error;
}
```

- [ ] **Step 3: Re-submit the same file with `groupFieldOverride` from the dialog**

```ts
await dataSource.uploadImport(scope, pendingImportFile, {
  groupFieldOverride: selectedGroupField,
});
clearPendingImportConfirmation();
```

- [ ] **Step 4: Add the new-customer entry point and a bulk dialog driven by `group-rule-candidates`**

```ts
<Button onClick={() => setBulkAssignDialogOpen(true)}>
  {t('broadcast.import.bulkAssign.open', { count: candidateList?.stats.newCount ?? 0 })}
</Button>
```

```ts
<BulkGroupAssignmentDialog
  open={bulkAssignDialogOpen}
  candidates={candidateList}
  groupNames={groupNames}
  onApplyBulkConversation={(conversationId) => applyConversationToSelectedRows(conversationId)}
  onSubmit={(items) => onBulkAssign(items)}
/>
```

- [ ] **Step 5: Clear all transient file/selection/error state on dialog close or file replacement**

```ts
function clearPendingImportConfirmation() {
  setPendingImportFile(null);
  setGroupFieldDialogOpen(false);
  setGroupFieldHeaders([]);
  setGroupFieldCandidates([]);
  setConfiguredGroupField(null);
  setSelectedGroupField('');
}
```

- [ ] **Step 6: Run focused ESLint on the touched UI files**

Run: `pnpm exec eslint web/src/app/home/broadcast/components/BroadcastWorkspace.tsx web/src/app/home/broadcast/components/import/ImportMatchingPanel.tsx web/src/app/home/broadcast/components/import/BulkGroupAssignmentDialog.tsx web/src/app/home/broadcast/components/shared/GroupConversationSelector.tsx web/src/i18n/locales/zh-Hans.ts web/src/i18n/locales/en-US.ts`
Expected: PASS for the touched files even if unrelated files still fail the repo-wide baseline.

---

### Task 9: Reuse shared rule UI pieces for exact form simplification and preview diagnostics

**Files:**
- Modify: `web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupRuleStatusBadge.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupMatchPreview.tsx`
- Create: `web/src/app/home/broadcast/components/shared/GroupConversationSelector.tsx`
- Modify: `web/src/i18n/locales/zh-Hans.ts`
- Modify: `web/src/i18n/locales/en-US.ts`
- Test: `pnpm exec eslint web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx web/src/app/home/broadcast/components/shared/GroupRuleStatusBadge.tsx web/src/app/home/broadcast/components/shared/GroupMatchPreview.tsx`

- [ ] **Step 1: Replace the exact-rule dual-field input with a single customer field**

```ts
if (draft.matchType === 'exact') {
  return (
    <div className="space-y-2">
      <Label>{t('broadcast.groupRule.customerName')}</Label>
      <Input
        value={draft.sourceValue}
        onChange={(event) =>
          setDraft((current) => ({
            ...current,
            sourceValue: event.target.value,
            matchExpression: event.target.value,
          }))
        }
      />
    </div>
  );
}
```

- [ ] **Step 2: Move conversation search and stable-ID display into the shared selector**

```ts
<GroupConversationSelector
  value={draft.targetConversationId}
  groupNames={groupNames}
  onChange={(conversation) =>
    setDraft((current) => ({
      ...current,
      targetConversationId: conversation?.externalConversationId ?? '',
      targetConversationName: conversation?.name ?? '',
    }))
  }
/>
```

- [ ] **Step 3: Render preview diagnostics using the backend-provided candidate list**

```ts
<GroupMatchPreview
  result={matchResult}
  emptyLabel={t('broadcast.groupRule.preview.empty')}
/>
```

- [ ] **Step 4: Keep all user-visible text in i18n**

```ts
'broadcast.groupRule.preview.conflict': '存在多个可命中规则，当前将按正式顺序采用第一条。'
'broadcast.groupRule.preview.candidateRules': '候选规则'
'broadcast.import.groupFieldDetected': '本批次已识别客户字段：{{field}}'
```

- [ ] **Step 5: Run focused ESLint on the rule UI files**

Run: `pnpm exec eslint web/src/app/home/broadcast/components/rules/GroupMatchingPanel.tsx web/src/app/home/broadcast/components/shared/GroupRuleStatusBadge.tsx web/src/app/home/broadcast/components/shared/GroupMatchPreview.tsx`
Expected: PASS with no duplicate conversation-selection logic left in the rule and import panels.

---

### Task 10: Cover the new flow with backend and E2E regression tests

**Files:**
- Modify: `tests/unit_tests/broadcast/test_service.py`
- Modify: `tests/unit_tests/broadcast/test_routes.py`
- Modify: `tests/unit_tests/broadcast/test_import_processor.py`
- Modify: `tests/integration/api/test_broadcast.py`
- Modify: `web/tests/e2e/broadcast-workspace.spec.ts`
- Modify: `web/tests/e2e/broadcast-import-feedback.spec.ts`
- Modify: `web/tests/e2e/fixtures/langbot-api.ts`

- [ ] **Step 1: Add backend coverage for the new field-confirmation upload branches**

```python
response = await quart_test_client.post(
    '/api/v1/broadcast/imports',
    headers=_auth_headers(),
    form={'bot_uuid': 'bot-1', 'connector_id': 'wxwork-local'},
    files={'file': FileStorage(stream=BytesIO('用户名,客户名称\nA,A\n'.encode('utf-8')), filename='customers.csv')},
)
assert response.status_code == 400 or response.status_code == 409
payload = await response.get_json()
assert payload['msg'] == BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED
```

- [ ] **Step 2: Add backend coverage for candidates and bulk assignment**

```python
response = await quart_test_client.get(
    f'/api/v1/broadcast/imports/{import_id}/group-rule-candidates?{_query_scope()}&status=new',
    headers=_auth_headers(),
)
assert response.status_code == 200
assert response_payload['data']['group_field_used'] == '用户名'
```

```python
bulk_response = await quart_test_client.post(
    f'/api/v1/broadcast/imports/{import_id}/group-rules/bulk-assign',
    headers=_auth_headers(),
    json={
        'bot_uuid': 'bot-1',
        'connector_id': 'wxwork-local',
        'items': [{'group_key': group_key, 'target_conversation_id': 'conv-1'}],
    },
)
assert bulk_response.status_code == 200
```

- [ ] **Step 3: Add Playwright coverage for the field confirmation dialog and new-customer bulk assignment UI**

```ts
await page.getByLabel('Upload file').setInputFiles(csvPath);
await expect(page.getByRole('dialog', { name: /确认客户字段/i })).toBeVisible();
await page.getByRole('radio', { name: '用户名' }).check();
await page.getByRole('button', { name: /继续导入/i }).click();
await expect(page.getByText(/本批次已识别客户字段：用户名/)).toBeVisible();
```

```ts
await page.getByRole('button', { name: /批量分配群聊/i }).click();
await page.getByRole('checkbox', { name: /select Alice/i }).check();
await page.getByRole('combobox', { name: /批量应用群聊/i }).click();
await page.getByRole('option', { name: /Alice群.*wxid-1/i }).click();
await page.getByRole('button', { name: /创建 1 条规则并重新匹配/i }).click();
await expect(page.getByText(/创建 1 条规则/)).toBeVisible();
```

- [ ] **Step 4: Run the backend regression suite requested by the task**

Run: `uv run pytest tests/unit_tests/broadcast -q`
Expected: PASS across import, rules, service, and repository coverage.

- [ ] **Step 5: Run the API integration suite requested by the task**

Run: `uv run pytest tests/integration/api/test_broadcast.py -q`
Expected: PASS for upload, rematch, new-customer candidates, and bulk assignment.

- [ ] **Step 6: Run the frontend typecheck and build**

Run: `pnpm exec tsc --noEmit`
Expected: PASS.

Run: `pnpm run build`
Expected: PASS with the broadcast workspace bundle built successfully.

- [ ] **Step 7: Run the targeted Playwright specs**

Run: `pnpm exec playwright test web/tests/e2e/broadcast-workspace.spec.ts web/tests/e2e/broadcast-import-feedback.spec.ts`
Expected: PASS for the new import confirmation and bulk assignment flows.

---

## Self-review checklist

- Spec coverage: migration, upload confirmation, batch-scoped rematch, candidates API, bulk assign, exact preview, and UI changes are all mapped to dedicated tasks.
- Placeholder scan: no `TODO`, `TBD`, or “similar to previous task” language remains.
- Type consistency: `group_field_used`, `group_field_source`, `existing_rule_ids`, `existing_rules`, `current_matched_rule`, and `BROADCAST_IMPORT_GROUP_RULE_BULK_ASSIGN_FAILED` are used consistently across backend and frontend tasks.
- Guardrail alignment: no reset/checkout/restore/clean, no commit step, no `git add .`, no template/draft/send workflow changes, and no inference from `group_key` string parsing.
