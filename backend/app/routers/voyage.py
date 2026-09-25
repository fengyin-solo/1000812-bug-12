"""航次管理接口：维护航次，覆盖确认开航、确认到港、结航航次等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.voyage import VoyageService

router = APIRouter(prefix="/api/voyage", tags=["航次管理"])

service = VoyageService()

LIST_FIELDS = ["航次编号", "关联船舶", "进口航次号", "出口航次号", "预计到港", "实际到港", "航线名称", "航次状态"]
STATUSES = ["待开航", "航行中", "已到港", "已结航"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按航次编号/关联船舶/进口航次号检索"),
    航次编号: str | None = Query(default=None),
    关联船舶: str | None = Query(default=None),
    进口航次号: str | None = Query(default=None),
    status: str | None = Query(default=None, description="待开航、航行中、已到港、已结航"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按航次编号、关联船舶、进口航次号与状态过滤；同一进口航次号只返回一条正本。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        voyage_no=航次编号,
        vessel=关联船舶,
        import_no=进口航次号,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出航次管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "voyage", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
    """读取单条航次明细，连同下面挂着的装卸任务、理货单、单证、堆存记录一起返回。"""
    detail = service.get_detail(entry_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"航次 {entry_id} 不存在或已归档")
    return detail


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条航次；同一进口航次号重复登记会被拦下并指向已有航次。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message=errors[0])
    return ActionResult(ok=True, message="航次已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """原位修改航次；id 不变，列表、详情与导出接口读到的都是保存后的同一条。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}/references", response_model=dict)
def list_references(entry_id: int) -> dict[str, Any]:
    """删除前查看：这条航次下还挂着哪些单据，逐类逐单列出。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"航次 {entry_id} 不存在或已归档")
    return {"entry_id": entry_id, "references": service.voyage_references(entry)}


@router.delete("/{entry_id}", response_model=ActionResult)
def delete_entry(entry_id: int, force: bool = False) -> ActionResult:
    """删除航次本身；有挂账单据时默认拦下并说明。

    force=true 时保留全部单据，只解除单据与航次的关联，绝不级联删除理货单、堆存记录。
    """
    result, message = service.delete_entry(entry_id, force=force)
    if result is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=result)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条航次执行确认开航、确认到港、结航航次；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
