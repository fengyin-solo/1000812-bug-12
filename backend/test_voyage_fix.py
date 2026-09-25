"""航次台账问题的回归验证：重复进口航次号、同船口径、更新可见、删除交代单据。"""
from __future__ import annotations

from app import seed
from app.store import store
from app.services.voyage import VoyageService


def reset_with_duplicates() -> VoyageService:
    """构造现场：同船同进口航次号被登记两条，且分别挂着不同单据。"""
    seed.SEED_ROWS["voyage"] = [
        {
            "id": 1, "status": "已到港", "pending": False, "abnormal": False,
            "航次编号": "V-1001", "关联船舶": "远洋之星", "进口航次号": "IMP-88",
            "出口航次号": "", "预计到港": "2026-09-20", "实际到港": "",
            "航线名称": "欧洲线", "航次状态": "已到港",
        },
        {
            "id": 2, "status": "航行中", "pending": True, "abnormal": False,
            "航次编号": "V-1001B", "关联船舶": "远洋之星", "进口航次号": "IMP-88",
            "出口航次号": "EXP-88", "预计到港": "", "实际到港": "",
            "航线名称": "", "航次状态": "航行中",
        },
    ]
    seed.SEED_ROWS["loading"] = [
        {"id": 11, "status": "作业中", "关联航次": "V-1001", "任务编号": "LOAD-1"},
        {"id": 12, "status": "待开工", "关联航次": "V-1001B", "任务编号": "LOAD-2"},
    ]
    seed.SEED_ROWS["tally"] = [
        {"id": 21, "status": "理货中", "关联航次": "IMP-88", "理货单号": "TALLY-1"},
    ]
    seed.SEED_ROWS["manifest"] = [
        {"id": 31, "status": "已提交", "关联航次": "V-1001B", "单证编号": "MANI-1"},
    ]
    seed.SEED_ROWS["yardstore"] = [
        {"id": 41, "status": "堆存中", "关联航次": "V-1001", "堆存单号": "YS-1", "关联箱号": "C1"},
        {"id": 42, "status": "堆存中", "关联航次": "", "堆存单号": "YS-2", "关联箱号": "C2"},
    ]
    store._tables = {name: [dict(row) for row in rows] for name, rows in seed.SEED_ROWS.items()}
    return VoyageService()


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"✓ {message}")


service = reset_with_duplicates()

# 1. 同一进口航次号只保留一条正本，重复行的非空字段补进正本
rows = store.rows("voyage")
assert_true(len(rows) == 1, f"去重后只剩一条航次（实际 {len(rows)} 条）")
canonical = rows[0]
assert_true(canonical["id"] == 1, "保留最早一条（id=1）为正本")
assert_true(canonical["关联船舶"] == "远洋之星", "正本关联船舶为远洋之星")
assert_true(canonical["出口航次号"] == "EXP-88", "重复行的非空字段（出口航次号）补入正本")

# 2. 挂在重复行/进口航次号上的单据全部改挂正本，详情看到的是同一组装卸任务
detail = service.get_detail(1)
assert_true(detail is not None, "详情能取到正本")
groups = {g["module"]: g for g in detail["references"]}
assert_true(set(groups) == {"loading", "tally", "manifest", "yardstore"},
            f"详情列出装卸任务、理货单、单证、堆存记录四类（实际 {sorted(set(groups))}）")
loading_codes = {item["任务编号"] for item in groups["loading"]["items"]}
assert_true(loading_codes == {"LOAD-1", "LOAD-2"},
            f"两组装卸任务都归到正本（实际 {loading_codes}）")
assert_true({item["理货单号"] for item in groups["tally"]["items"]} == {"TALLY-1"}, "理货单按进口航次号匹配到正本")
assert_true(len(groups["yardstore"]["items"]) == 1, "堆存记录只统计真正挂在本航次的那条")

# 3. 列表、详情、导出接口取到同一艘船
items, total = service.list_entries()
assert_true(total == 1 and items[0]["关联船舶"] == "远洋之星", "列表只有一条且关联船舶=远洋之星")
exported, export_total = service.list_entries(page=1, size=10000)
assert_true(export_total == 1 and exported[0]["id"] == canonical["id"], "导出接口也是同一条正本")

# 4. 重复的进口航次号禁止再登记
entry, errors = service.create_entry({"航次编号": "V-2000", "关联船舶": "新船", "进口航次号": "IMP-88"})
assert_true(entry is None and "IMP-88" in errors[0] and "V-1001" in errors[0],
            "重复登记被拦下，并指明已有的航次编号")

# 5. 换掉关联船舶：原位保存、id 不变，接口立刻能查到、且列表/详情同船
saved, message = service.update_entry(1, {
    "航次编号": "V-1001", "关联船舶": "远海之翼", "进口航次号": "IMP-88",
})
assert_true(saved is not None and saved["id"] == 1 and saved["关联船舶"] == "远海之翼",
            f"换船保存成功且仍为 id=1（{message}）")
fetched = service.get_entry(1)
assert_true(fetched is not None and fetched["关联船舶"] == "远海之翼", "接口按原 id 能查到新船名")
assert_true(service.list_entries()[0][0]["关联船舶"] == "远海之翼", "列表读到的也是新船名")

# 6. 改航次编号后，挂账单据改挂新编号，详情仍能取到同一组装卸任务
saved, _ = service.update_entry(1, {
    "航次编号": "V-9999", "关联船舶": "远海之翼", "进口航次号": "IMP-88",
})
assert_true(store.rows("loading")[0]["关联航次"] == "V-9999", "原编号挂着的装卸任务改挂新编号")
detail_groups = {g["module"]: g for g in service.get_detail(1)["references"]}
codes = {item["任务编号"] for item in detail_groups["loading"]["items"]}
assert_true(codes == {"LOAD-1", "LOAD-2"}, "改编号后详情仍是同一组装卸任务")

# 7. 删除：有挂账单据时默认拦下
result, message = service.delete_entry(1)
assert_true(result is None and "装卸任务 2 条" in message and "理货单 1 条" in message
            and "堆存记录 1 条" in message, f"删除前逐类交代单据（{message}）")
assert_true(len(store.rows("voyage")) == 1, "拦截删除时航次仍在")
assert_true(len(store.rows("tally")) == 1 and len(store.rows("yardstore")) == 2,
            "拦截删除时理货单与堆存记录一条不少")

# 8. 强制删除：航次删除，单据全部保留（只解关联），堆存记录不丢失
result, message = service.delete_entry(1, force=True)
assert_true(result is not None, f"强制删除成功（{message}）")
assert_true(len(store.rows("voyage")) == 0, "航次已删除")
assert_true(len(store.rows("loading")) == 2, "装卸任务保留")
assert_true(len(store.rows("tally")) == 1, "理货单保留")
assert_true(len(store.rows("manifest")) == 1, "单证保留")
assert_true(len(store.rows("yardstore")) == 2, "堆存记录两条全部保留，未被级联删除")
assert_true(all(not str(r.get("关联航次")).strip() for r in store.rows("loading")), "装卸任务已解除关联")
assert_true(not str(store.rows("yardstore")[1].get("关联航次")).strip(),
            "原本就未挂航次的堆存记录内容不受影响")

# 9. 无单据的航次可直接删除
new_entry, _ = service.create_entry({"航次编号": "V-3000", "关联船舶": "空载船", "进口航次号": "IMP-99"})
result, message = service.delete_entry(int(new_entry["id"]))
assert_true(result is not None and "没有挂账单据" in message, f"无单据航次直接删除（{message}）")

# 10. 中文筛选参数生效
service.create_entry({"航次编号": "V-4000", "关联船舶": "检索目标船", "进口航次号": "IMP-77"})
items, total = service.list_entries(vessel="检索目标")
assert_true(total == 1 and items[0]["进口航次号"] == "IMP-77", "按关联船舶中文参数可筛到航次")
items, total = service.list_entries(import_no="IMP-77")
assert_true(total == 1, "按进口航次号中文参数可筛到航次")

print("\n全部场景验证通过")
