"""航次管理业务规则：同一进口航次号唯一、列表/详情同一口径、删除先交代挂账单据。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "voyage"
REQUIRED_FIELDS = ["航次编号", "关联船舶", "进口航次号"]
EDITABLE_FIELDS = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称"]
STATUS_ORDER = ["待开航", "航行中", "已到港", "已结航"]
ACTION_RULES = {"确认开航": "航行中", "确认到港": "已到港", "结航航次": "已结航"}
NEGATIVE_ACTIONS = []

# 挂在航次下面的单据：(模块名, 展示名, 单号字段)。删除航次前必须逐一向用户交代。
RELATED_MODULES = (
    ("loading", "装卸任务", "任务编号"),
    ("tally", "理货单", "理货单号"),
    ("manifest", "单证", "单证编号"),
    ("yardstore", "堆存记录", "堆存单号"),
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


class VoyageService:
    def __init__(self) -> None:
        # 服务装载即整理存量：历史重复登记的同一进口航次号只保留一条正本。
        self._coalesce_duplicates()

    # ------------------------------------------------------------------ 读取
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        voyage_no: str | None = None,
        vessel: str | None = None,
        import_no: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in _norm(row.get("航次编号"))
                or keyword in _norm(row.get("关联船舶"))
                or keyword in _norm(row.get("进口航次号"))
            ]
        if voyage_no:
            rows = [row for row in rows if voyage_no in _norm(row.get("航次编号"))]
        if vessel:
            rows = [row for row in rows if vessel in _norm(row.get("关联船舶"))]
        if import_no:
            rows = [row for row in rows if import_no in _norm(row.get("进口航次号"))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def get_detail(self, entry_id: int) -> dict[str, Any] | None:
        """详情与列表取的是同一条正本行，挂账单据按航次编号/进口航次号匹配。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None
        return {"entry": entry, "references": self.voyage_references(entry)}

    def voyage_references(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        """汇总航次下挂着的装卸任务、理货单、单证、堆存记录。"""
        keys = self._voyage_keys(entry)
        groups: list[dict[str, Any]] = []
        for module, label, code_field in RELATED_MODULES:
            items = [
                {"id": row.get("id"), code_field: row.get(code_field), "status": row.get("status")}
                for row in store.rows(module)
                if _norm(row.get("关联航次")) in keys
            ]
            if items:
                groups.append({"module": module, "label": label, "code_field": code_field, "items": items})
        return groups

    # ------------------------------------------------------------------ 写入
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _norm(values.get(field))]
        if missing:
            return None, [f"缺少必填字段：{'、'.join(missing)}"]
        import_no = _norm(values.get("进口航次号"))
        duplicate = self._find_duplicate(import_no)
        if duplicate is not None:
            return None, [
                f"进口航次号「{import_no}」已登记为航次「{_norm(duplicate.get('航次编号'))}」，"
                f"同一进口航次号只能保留一条，请在原航次上修改"
            ]
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in EDITABLE_FIELDS:
            entry[field] = _norm(values.get(field))
        entry["status"] = STATUS_ORDER[0]
        entry["航次状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """原位更新：id 不变，列表、详情、接口始终能查到同一条。"""
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"航次 {entry_id} 不存在或已归档"
        merged = {field: _norm(values.get(field, entry.get(field))) for field in EDITABLE_FIELDS}
        missing = [field for field in REQUIRED_FIELDS if not merged[field]]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        duplicate = self._find_duplicate(merged["进口航次号"], exclude_id=entry_id)
        if duplicate is not None:
            return None, (
                f"进口航次号「{merged['进口航次号']}」已被航次「{_norm(duplicate.get('航次编号'))}」占用，"
                f"同一进口航次号只能保留一条"
            )
        old_keys = self._voyage_keys(entry)
        entry.update(merged)
        # 航次编号/进口航次号被改掉后，挂着的单据改挂新编号，避免详情对不上、接口查不到。
        stale_keys = old_keys - self._voyage_keys(entry)
        if stale_keys:
            self._repoint_references(entry, stale_keys)
        return entry, "航次已保存"

    def delete_entry(
        self, entry_id: int, *, force: bool = False
    ) -> tuple[dict[str, Any] | None, str]:
        """删除航次本身；默认在有挂账单据时拦下并把单据逐类列清楚。

        force=True 时也只解除单据上的关联航次，绝不级联删除理货单、堆存记录等任何单据。
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"航次 {entry_id} 不存在或已归档"
        groups = self.voyage_references(entry)
        if groups and not force:
            summary = "、".join(
                f"{group['label']} {len(group['items'])} 条（"
                + "、".join(_norm(item.get(group["code_field"])) for item in group["items"])
                + "）"
                for group in groups
            )
            return None, f"该航次下还挂着 {summary}，请先处理这些单据，或确认保留单据并解除关联后再删除"

        detached: list[dict[str, Any]] = []
        if groups:
            keys = self._voyage_keys(entry)
            for module, label, code_field in RELATED_MODULES:
                codes: list[str] = []
                for row in store.rows(module):
                    if _norm(row.get("关联航次")) in keys:
                        codes.append(_norm(row.get(code_field)))
                        row["关联航次"] = ""
                if codes:
                    detached.append({"module": module, "label": label, "codes": codes})
        store.rows(MODULE).remove(entry)

        if detached:
            detail = "、".join(f"{item['label']} {len(item['codes'])} 条" for item in detached)
            return {"id": entry_id, "detached": detached}, f"航次已删除；{detail}已保留并解除关联"
        return {"id": entry_id, "detached": []}, "航次已删除，其下没有挂账单据"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None, f"航次 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于航次管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["航次状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"航次已{action}"

    # ------------------------------------------------------------------ 内部
    def _voyage_keys(self, entry: dict[str, Any]) -> set[str]:
        """航次在单据「关联航次」字段里可能出现的键：航次编号与进口航次号。"""
        return {key for key in (_norm(entry.get("航次编号")), _norm(entry.get("进口航次号"))) if key}

    def _find_duplicate(
        self, import_no: str, *, exclude_id: int | None = None
    ) -> dict[str, Any] | None:
        if not import_no:
            return None
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if _norm(row.get("进口航次号")) == import_no:
                return row
        return None

    def _repoint_references(self, entry: dict[str, Any], old_keys: set[str]) -> None:
        target = _norm(entry.get("航次编号"))
        if not target:
            return
        for module, _label, _code in RELATED_MODULES:
            for row in store.rows(module):
                if _norm(row.get("关联航次")) in old_keys:
                    row["关联航次"] = target

    def _coalesce_duplicates(self) -> None:
        """存量数据里同一进口航次号可能被重复登记成多条：

        保留最早一条为正本，其余条目的非空字段补进正本的空位，挂着的单据改挂正本，
        再删除重复行——列表、详情与接口从此只看到一条、同一艘船。
        """
        rows = store.rows(MODULE)
        for row in rows:
            # 展示用的「航次状态」与内部 status 始终保持一致。
            row["航次状态"] = row.get("status", STATUS_ORDER[0])

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            import_no = _norm(row.get("进口航次号"))
            if import_no:
                grouped.setdefault(import_no, []).append(row)

        for dup_rows in grouped.values():
            if len(dup_rows) <= 1:
                continue
            canonical, *redundant = dup_rows
            dropped_keys: set[str] = set()
            for dup in redundant:
                for field in EDITABLE_FIELDS:
                    if not _norm(canonical.get(field)) and _norm(dup.get(field)):
                        canonical[field] = dup.get(field)
                dropped_keys.update(
                    key for key in (_norm(dup.get("航次编号")), _norm(dup.get("进口航次号"))) if key
                )
            for dup in redundant:
                rows.remove(dup)
            dropped_keys -= self._voyage_keys(canonical)
            if dropped_keys:
                self._repoint_references(canonical, dropped_keys)
