"""航次管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "voyage"
REQUIRED_FIELDS = ["航次编号", "关联船舶", "进口航次号"]
EDITABLE_FIELDS = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称", "航次状态"]
STATUS_ORDER = ["待开航", "航行中", "已到港", "已结航"]
ACTION_RULES = {"确认开航": "航行中", "确认到港": "已到港", "结航航次": "已结航"}
NEGATIVE_ACTIONS = []

# 挂在航次下的单据：模块 -> (单据名称, 单据编号字段)，关联口径是「关联航次 == 航次编号」
ATTACHED_MODULES = [
    ("loading", "装卸任务", "任务编号"),
    ("tally", "理货单", "理货单号"),
    ("manifest", "单证", "单证编号"),
]


class VoyageService:
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
            rows = [row for row in rows if keyword in str(row.get("航次编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def _find_duplicate(
        self,
        vessel: str,
        import_no: str,
        *,
        exclude_id: int | None = None,
    ) -> dict[str, Any] | None:
        """同一艘船的同一个进口航次号只允许存在一条航次。"""
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("关联船舶", "")).strip() == vessel and str(row.get("进口航次号", "")).strip() == import_no:
                return row
        return None

    def _find_by_code(self, code: str, *, exclude_id: int | None = None) -> dict[str, Any] | None:
        """航次编号是挂接装卸任务、理货单、单证的锚点，同样不能重号。"""
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("航次编号", "")).strip() == code:
                return row
        return None

    def _validate(self, values: dict[str, Any], *, exclude_id: int | None = None) -> str:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return f"缺少必填字段：{'、'.join(missing)}"
        code = str(values.get("航次编号", "")).strip()
        vessel = str(values.get("关联船舶", "")).strip()
        import_no = str(values.get("进口航次号", "")).strip()
        clash = self._find_by_code(code, exclude_id=exclude_id)
        if clash is not None:
            return f"航次编号「{code}」已存在（记录 {clash.get('id')}），请换一个编号"
        clash = self._find_duplicate(vessel, import_no, exclude_id=exclude_id)
        if clash is not None:
            return (
                f"船舶「{vessel}」的进口航次号「{import_no}」已登记过"
                f"（航次编号 {clash.get('航次编号')}），同一船舶同一进口航次号只保留一条"
            )
        return ""

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        error = self._validate(values)
        if error:
            return None, error
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in EDITABLE_FIELDS if values.get(field) is not None})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, ""

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """原地修改同一条航次：id 不变，列表、详情与接口读到的都是这一条。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"航次 {entry_id} 不存在或已归档"
        merged = {**entry, **{field: values.get(field) for field in EDITABLE_FIELDS if field in values}}
        error = self._validate(merged, exclude_id=entry_id)
        if error:
            return None, error
        entry.update({field: merged[field] for field in EDITABLE_FIELDS if field in merged})
        return entry, ""

    def attached_documents(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        """列出挂在该航次下的全部单据，删除前必须先看清楚。"""
        code = str(entry.get("航次编号", "")).strip()
        attached: list[dict[str, Any]] = []
        for module, label, code_field in ATTACHED_MODULES:
            for row in store.rows(module):
                if str(row.get("关联航次", "")).strip() == code:
                    attached.append({
                        "module": module,
                        "label": label,
                        "code": row.get(code_field),
                        "id": row.get("id"),
                        "row": row,
                    })
        return attached

    def delete_entry(self, entry_id: int) -> tuple[bool, str]:
        """删除航次：挂着装卸任务、理货单、单证时只说明不删除，绝不连带丢单据。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return False, f"航次 {entry_id} 不存在或已归档"
        attached = self.attached_documents(entry)
        if attached:
            summary = "、".join(f"{item['label']} {item['code']}" for item in attached)
            return False, (
                f"航次 {entry.get('航次编号')} 下仍挂着 {len(attached)} 份单据：{summary}。"
                "请先处理这些单据再删除，航次未删除，单据也都保留"
            )
        store.rows(MODULE).remove(entry)
        return True, f"航次 {entry.get('航次编号')} 已删除，删除前已确认没有挂接单据"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"航次 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于航次管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"航次已{action}"
