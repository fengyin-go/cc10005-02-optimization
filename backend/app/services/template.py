"""抽取模板业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "template"
REQUIRED_FIELDS = ["模板编号", "入口地址", "列表选择器"]
STATUS_ORDER = ["草稿", "待校验", "已启用", "已废弃"]
ACTION_RULES = {"提交校验": "待校验", "启用模板": "已启用", "废弃模板": "已废弃"}
NEGATIVE_ACTIONS = []


class TemplateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("模板编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """编辑模板草稿：选择器、映射等任一环节变化，都会让挂在该模板下的评审结论失效。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"网页模板 {entry_id} 不存在或已归档"
        editable = ["入口地址", "列表选择器", "详情选择器", "分页规则", "字段映射", "数据格式", "模板版本"]
        changed = [field for field in editable if field in values and values[field] != entry.get(field)]
        for field in editable:
            if field in values:
                entry[field] = values[field]
        if changed:
            # 延迟导入：评审服务启动时要读模板，反向引用放在方法里避免循环依赖
            from app.services.review import review_service

            affected = review_service.invalidate_for_template(
                entry_id, f"模板草稿的 {'、'.join(changed)} 被修改，原评审结论失效"
            )
            entry["abnormal"] = bool(affected)
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"网页模板 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于抽取模板可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"网页模板已{action}"
