# MULTI-AGENT WORKFLOW

## Vai trò

- Boss: mục tiêu và phê duyệt.
- Integrator: chia task, board, review, merge, gate.
- Contract Owner: shared contracts/schema.
- Implementer: module code.
- QA: test, regression, risk scan.

## Luật

1. Không tự nhận việc.
2. Không tự merge.
3. Handoff là `ready_for_review`, không phải done.
4. Không push sau handoff.
5. Mỗi file một owner trong wave.
6. Task phụ thuộc nhận Base SHA sau merge wave trước.
7. Conflict phải abort và giao lại, không tự giải quyết semantic.

## Files điều phối

- `05_AI/AGENTS.md`
- `docs_active/WORK_BOARD.md`
- `docs_active/SESSION_LOG.md`
