# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260629-001] correction

**Logged**: 2026-06-29T17:36:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
监控面板把 `status: "pending"` 误解为"待审核"，实际 pending = 已发布但未生效

### Details
- 网站中法规的 status 字段含义：`pending`(未生效) → `effective`(已生效) → `active`(已审核确认)
- 监控面板原本显示 "Pending Review: 9" 并列出所有 status=pending 的条目，标记为 "awaiting manual review"
- 用户指出：pending 不是需要人工审核的意思，只是法规还没到生效日期
- **用户真正需要的**：追踪 GitHub Actions 每次运行新发现了什么法规（来自 update_log.json 的 entries[]）

### Suggested Action
重新设计监控面板：显示 update_log.json 中的新增条目列表，而非 status=pending 的法规

### Metadata
- Source: user_feedback
- Related Files: index.html (monitor panel + loadMonitorData function)
- Tags: monitor-dashboard, status-field, update_log, misunderstanding

## [LRN-20260704-001] insight

**Logged**: 2026-07-04T22:48:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
STA 爬虫关键词过滤太窄导致遗漏车船税等非出口退税的税收法规

### Details
- auto_update.py STA 爬虫原关键词：`['出口', '退税', '增值税', '消费税', '公告2026年']`
- 财政部/税务总局/工信部公告2026年第19号（车船税政策调整）因不含上述关键词被跳过
- 用户指出后扩展为：`['出口', '退税', '增值税', '消费税', '公告2026年', '车船税', '印花税', '税收优惠']`
- Bing 降级搜索词也从"出口退税"扩展为"税收 出口退税 车船税"
- 不使用单独的"税收"（太宽泛）或"公告2026年第"（匹配不到具体文号）

### Suggested Action
已实施：auto_update.py、SKILL.md、automation prompt 均已同步更新

### Resolution
- **Resolved**: 2026-07-04T22:48:00+08:00
- **Notes**: 关键词范围扩大但保持精准，避免引入过多噪音
