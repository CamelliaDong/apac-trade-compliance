# Errors

Command failures and integration errors.

---

## [ERR-20260629-001] auto_update.py MOFCOM date extraction failure

**Logged**: 2026-06-29T06:25:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
MOFCOM announcements all got date "2026-01-01" instead of actual publication dates (2026-06-26, 2026-06-24, etc.)

### Error
```
3 MOFCOM entries showed date: 2026-01-01, effectiveDate: 2026-01-01
But descriptions clearly show "来源：... 2026-06-26 10:17" or similar
All were incorrectly grouped under January timeline
```

### Context
- `scrape_mofcom_announcements()` only extracted title_raw and url, NOT the publication date
- MOFCOM listing page format: `[Title](URL) YYYY-MM-DD` (date in text node after <a>)
- `extract_date_from_title_or_url()` fallback could only get year from URL path `/art/2026/art_xxx.html`
- Resulted in all dates defaulting to `CURRENT_YEAR-01-01` = "2026-01-01"

### Suggested Fix ✅ APPLIED
1. Modified `scrape_mofcom_announcements()` to extract date from text sibling after `<a>` tag
2. Added 3 extraction methods: next_sibling → parent_text → URL path fallback
3. Modified `main()` to prioritize `reg['pub_date']` over `extract_date_from_title_or_url()`
4. Also added /zcjd/, /xwfb/, /tj/ URL path filtering for non-regulation content

### Resolution
- **Resolved**: 2026-06-29T06:24:59Z
- **Commit**: 9b23c58f5bba9896bc30c1cc0cb5322e0867d16a
- **Test result**: All 5 MOFCOM announcements now get correct dates (2026-06-29, 2026-06-26, 2026-06-24)

### Metadata
- Reproducible: yes
- Related Files: scripts/auto_update.py
- See Also:
- Recurrence-Count: 2 (first seen: 2026-06-28 when duplicate entries appeared)

---

## [ERR-20260630-001] auto_update.py_dedup

**Logged**: 2026-06-30T11:46:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend, infra

### Summary
GitHub Actions 重复将相同 numberCN 的条目添加为新条目，导致同一法规多次出现（如 2026-034 和 2026-041 都是 MOFCOM #26）

### Error
- 2026-040 (GACC #80 海关总署公告2026年第80号 关于进口非洲腰果检验检疫) — 这是通讯稿 URL (customs.gov.cn/customs/2026-06/10/...)，不是正式法规
- 2026-041 (MOFCOM #26) — 与已有 2026-034 完全重复（同一 numberCN）

### Context
- 早期运行（修复四重去重之前）已添加这些错误条目
- 修复 force-push 同步问题后，最近一次运行 (#33) 正确识别了重复并拒绝
- 但旧的错误条目（040/041）已被固化在 index.html 中

### Suggested Fix ✅ APPLIED
1. 强化 `auto_update.py`：
   - 新增 `normalize_numberCN()` 处理空格/全角空格变体
   - 新增 `is_press_release_url()` 拒绝 customs.gov.cn/YYYY-MM/DD/ 和 mofcom /zcjd/ /xwfb/ /tj/ 路径
   - 改"占位符 description"为"拒绝录入"（fetch < 20 字符直接跳过）
2. 手动清理 index.html 中的 040/041 错误条目
3. 验证：单元测试覆盖关键 dedup 场景

### Resolution
- **Resolved**: 2026-06-30T11:50:00+08:00
- **Commits**: 66981ef7f5e5 (delete bad entries) + c9265e196a76 (harden script)
- **Result**: 59 → 57 法规，0 重复；press-release URL 模式被自动拒绝

### Metadata
- Reproducible: yes
- Related Files: scripts/auto_update.py, index.html
- See Also: ERR-20260629-001, LRN-20260630-001
- Pattern-Key: harden.dedup_strict
- Recurrence-Count: 3

---

## [ERR-20260630-002] auto_update.py MOFCOM numberCN missing

**Logged**: 2026-06-30T16:15:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
GitHub Actions 添加了 2026-040（MOFCOM #26 战略矿产举报制度），与已存在的 2026-034 完全重复。dedup 7 层都没拦住。

### Error
```
update_log.json entries:
- 2026-040 | 商务部公告2026年第26号 公布关于... | url: art_34c1dcb07...
```

但 2026-034 已经在 index.html 数组中，numberCN 字段一模一样：
```
2026-034 | 商务部公告2026年第26号 | url: art_c07f4d54ca13...
```

### Context
**根因（双层问题）**：
1. MOFCOM 爬虫在 `new_regs.append({...})` 时**只设置了 `numberCN_raw`**（完整标题），**没有设置 `numberCN`** 字段
2. dedup 第 1 步查的是 `existing_numberCNs`，里面存的是 `商务部公告2026年第26号`，但新条目的 `numberCN` 是空字符串 → 字符串匹配失败

**这是 ERR-20260630-001 的回归** — 7 层去重机制存在设计漏洞。

### Suggested Fix ✅ APPLIED
1. **MOFCOM 爬虫**：在 `scrape_mofcom_announcements()` 中用正则从 title 提取 numberCN，同时设置 `numberCN` 和 `numberCN_raw` 字段
2. **主 dedup 逻辑**：增加 fallback — 如果 `numberCN` 为空，从 `numberCN_raw` 用正则提取
3. 正则覆盖：`商务部公告2026年第26号` / `商务部 公告 2026年 第 26 号` / `商务部公告\u30002026\u3000年第\u300026号`
4. **本地 automation prompt**：增加「重复项核查」为最高优先级（之前只在 GitHub Actions 层面）
5. **测试验证**：用 Python 模拟失败场景，确认新逻辑能拦住

### Resolution
- **Resolved**: 2026-06-30T16:30:00+08:00
- **Commits**: 85159b4ddb22 (delete 2026-040) + 33165aa0fce9 (fix auto_update.py)
- **Test result**:
  ```
  Extracted numberCN: '商务部公告2026年第26号'
  In existing_numberCNs: True  ✅ (现在能拦住了)
  ```

### Metadata
- Reproducible: yes
- Related Files: scripts/auto_update.py
- See Also: ERR-20260630-001, ERR-20260629-001
- Pattern-Key: harden.dedup_field_extraction
- Recurrence-Count: 4 (去重问题第 4 次发生)

---

## [ERR-20260630-001] auto_update.py_dedup

**Logged**: 2026-06-30T11:46:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend, infra

### Summary
GitHub Actions 重复将相同 numberCN 的条目添加为新条目，导致同一法规多次出现（如 2026-034 和 2026-041 都是 MOFCOM #26）

### Error
- 2026-040 (GACC #80 海关总署公告2026年第80号 关于进口非洲腰果检验检疫) — 这是通讯稿 URL (customs.gov.cn/customs/2026-06/10/...)，不是正式法规
- 2026-041 (MOFCOM #26) — 与已有 2026-034 完全重复（同一 numberCN）

### Context
- 早期运行（修复四重去重之前）已添加这些错误条目
- 修复 force-push 同步问题后，最近一次运行 (#33) 正确识别了重复并拒绝
- 但旧的错误条目（040/041）已被固化在 index.html 中

### Suggested Fix ✅ APPLIED
1. 强化 `auto_update.py`：
   - 新增 `normalize_numberCN()` 处理空格/全角空格变体
   - 新增 `is_press_release_url()` 拒绝 customs.gov.cn/YYYY-MM/DD/ 和 mofcom /zcjd/ /xwfb/ /tj/ 路径
   - 改"占位符 description"为"拒绝录入"（fetch < 20 字符直接跳过）
2. 手动清理 index.html 中的 040/041 错误条目
3. 验证：单元测试覆盖关键 dedup 场景

### Resolution
- **Resolved**: 2026-06-30T11:50:00+08:00
- **Commits**: 66981ef7f5e5 (delete bad entries) + c9265e196a76 (harden script)
- **Result**: 59 → 57 法规，0 重复；press-release URL 模式被自动拒绝

### Metadata
- Reproducible: yes
- Related Files: scripts/auto_update.py, index.html
- See Also: ERR-20260629-001, LRN-20260630-001
- Pattern-Key: harden.dedup_strict
- Recurrence-Count: 3
