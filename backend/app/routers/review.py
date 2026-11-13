"""发布评审接口：评审卡的建立、三段式评审、版本对照、废弃留档与作业绑定。

评审流固定为 选择器命中 → 映射产出 → 人工确认，后端在每一步都做门禁校验；
任何修改导致的失效、同版本号并行发布冲突都在这里转成可读的业务错误。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload
from app.services.review import (
    REVIEW_STATUSES,
    STAGE_MAPPING,
    STAGE_SELECTOR,
    review_service,
)
from app.store import store

router = APIRouter(prefix="/api/review", tags=["发布评审"])


def _payload_values(payload: EntryPayload) -> dict[str, Any]:
    return payload.values or {}


@router.get("/context")
def review_context() -> dict[str, Any]:
    """评审编辑区表单需要的下拉数据：候选模板与结构化映射规则。"""
    return {
        "templates": [
            {
                "id": row.get("id"),
                "模板编号": row.get("模板编号"),
                "模板版本": row.get("模板版本"),
                "列表选择器": row.get("列表选择器"),
                "详情选择器": row.get("详情选择器"),
                "字段映射": row.get("字段映射"),
                "status": row.get("status"),
            }
            for row in store.rows("template")
        ],
        "mapping_rules": [
            {
                "id": row.get("id"),
                "规则编号": row.get("规则编号"),
                "源字段名称": row.get("源字段名称"),
                "目标字段名称": row.get("目标字段名称"),
                "数据类型转换": row.get("数据类型转换"),
                "必填标识": row.get("必填标识"),
            }
            for row in store.rows("extractor")
        ],
        "评审状态": REVIEW_STATUSES,
        "评审环节": [STAGE_SELECTOR, STAGE_MAPPING],
    }


@router.get("/sample-html")
def sample_html() -> dict[str, str]:
    """提供演示用网页片段样本，方便评审卡一键载入原文选区。"""
    from app.services.review import SAMPLE_HTML

    return {"html": SAMPLE_HTML}


@router.get("/cards")
def list_cards(
    status: str | None = Query(default=None, description="待评审、已确认、已废弃"),
    keyword: str | None = Query(default=None, description="按发布卡编号或模板版本检索"),
    include_discarded: bool = Query(default=True, description="废弃卡是否出现在列表；新作业选项永远排除"),
) -> dict[str, Any]:
    items = review_service.list_cards(status=status, keyword=keyword, include_discarded=include_discarded)
    return {"items": items, "total": len(items)}


@router.get("/cards/{card_id}")
def get_card(card_id: int) -> ActionResult:
    card = review_service.get_card(card_id)
    if card is None:
        return ActionResult(ok=False, message=f"发布评审卡 {card_id} 不存在")
    return ActionResult(ok=True, message="ok", entry=card)


@router.post("/cards", response_model=ActionResult)
def create_card(payload: EntryPayload) -> ActionResult:
    """把候选模板版本、字段映射版本与网页片段样本绑成一张待评审卡。"""
    card, message = review_service.create_card(_payload_values(payload))
    if card is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="发布评审卡已建立，等待选择器命中评审", entry=card)


@router.patch("/cards/{card_id}", response_model=ActionResult)
def update_card(card_id: int, payload: EntryPayload) -> ActionResult:
    """修改评审卡任一环节：原评审结论立即失效，不能沿用旧的通过标记。"""
    card, message = review_service.update_card(card_id, _payload_values(payload))
    if card is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="评审卡已更新，原评审结论失效，请重新评审", entry=card)


@router.post("/cards/{card_id}/checks", response_model=ActionResult)
def run_check(card_id: int, payload: EntryPayload) -> ActionResult:
    """执行选择器或映射环节评审；映射环节要求选择器环节先通过。"""
    stage = str(_payload_values(payload).get("stage") or "").strip()
    if stage not in (STAGE_SELECTOR, STAGE_MAPPING):
        return ActionResult(ok=False, message=f"评审环节「{stage}」不支持，只能是{STAGE_SELECTOR}或{STAGE_MAPPING}")
    card, message = review_service.run_check(card_id, stage)
    if card is None:
        return ActionResult(ok=False, message=message)
    result = card["选择器评审"] if stage == STAGE_SELECTOR else card["映射评审"]
    return ActionResult(ok=bool(result and result.get("通过")), message=result.get("结论", ""), entry=card)


@router.post("/cards/{card_id}/confirm", response_model=ActionResult)
def confirm_card(card_id: int, payload: EntryPayload) -> ActionResult:
    """人工确认：两环节通过且无失效、无版本冲突时，卡才进入可选版本池。"""
    values = _payload_values(payload)
    card, message = review_service.confirm(
        card_id,
        reviewer=str(values.get("reviewer") or "值班管理员"),
        remark=str(values.get("remark") or ""),
    )
    if card is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"评审卡 {card['发布卡编号']} 已确认，可作为采集任务发布依据", entry=card)


@router.post("/cards/{card_id}/discard", response_model=ActionResult)
def discard_card(card_id: int, payload: EntryPayload) -> ActionResult:
    """废弃卡只从新作业选项退出，历史作业的样本与映射证据仍可打开。"""
    reason = str(_payload_values(payload).get("reason") or "")
    card, message = review_service.discard(card_id, reason)
    if card is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"评审卡 {card['发布卡编号']} 已废弃，仅退出新作业选项，历史证据保留", entry=card)


@router.get("/cards/{card_id}/compare")
def compare_card(card_id: int) -> ActionResult:
    """与现用版逐项对照：少提、多提、类型转换不符、取值变化。"""
    diff, message = review_service.compare_with_current(card_id)
    if diff is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message or "对照完成", entry=diff)


@router.get("/job-options")
def job_options(template_id: int | None = Query(default=None, description="可按模板过滤可选发布卡")) -> dict[str, Any]:
    """新采集作业的发布依据候选：只返回已确认、未失效、未废弃的卡。"""
    items = review_service.options_for_job(template_id)
    return {"items": items, "total": len(items)}


@router.post("/bindings", response_model=ActionResult)
def bind_job(payload: EntryPayload) -> ActionResult:
    """采集任务绑定经确认的发布卡；绑定时刻固化证据快照，草稿后续编辑不影响作业。"""
    values = _payload_values(payload)
    try:
        job_id = int(values.get("job_id") or 0)
        card_id = int(values.get("card_id") or 0)
    except (TypeError, ValueError):
        return ActionResult(ok=False, message="作业与发布卡标识必须是数字")
    binding, message = review_service.bind_job(job_id, card_id)
    if binding is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="采集作业已绑定发布卡，提取依据已固化为当时快照", entry=binding)


@router.get("/jobs/{job_id}/binding")
def get_job_binding(job_id: int) -> ActionResult:
    """回看某次作业当时采用的样本与映射证据；即使发布卡后来废弃也照常返回。"""
    binding = review_service.get_job_binding(job_id)
    if binding is None:
        return ActionResult(ok=False, message=f"采集作业 {job_id} 尚未绑定发布评审卡")
    return ActionResult(ok=True, message="ok", entry=binding)


@router.get("/bindings")
def list_bindings() -> dict[str, Any]:
    items = review_service.list_bindings()
    return {"items": items, "total": len(items)}
