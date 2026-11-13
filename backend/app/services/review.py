"""发布评审卡业务规则。

一张评审卡把「候选模板版本 + 字段映射版本 + 网页片段样本」绑成一个不可拆的评审对象：
评审必须按 选择器命中 → 映射产出 → 人工确认 的顺序推进，任何环节的修改都会让
原评审结论失效，不能沿用旧的通过标记。

关键口径：
- 已确认的卡才能被新采集作业选为发布依据；绑定的是当时的证据快照，日后改草稿不动作业；
- 同一模板并行发布同一版本号要报版本冲突；
- 废弃卡只从新作业选项中退出，历史作业仍能打开当时的样本与映射证据；
- 沿用模板里文字版「字段映射」的旧样例视为尚未完成评审（旧文字映射）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services import review_engine
from app.store import store

CARD_MODULE = "review_cards"
BINDING_MODULE = "job_bindings"
TEMPLATE_MODULE = "template"
EXTRACTOR_MODULE = "extractor"

STAGE_SELECTOR = "选择器"
STAGE_MAPPING = "映射"
CARD_DRAFT = "待评审"
CARD_CONFIRMED = "已确认"
CARD_DISCARDED = "已废弃"

REVIEW_STATUSES = [CARD_DRAFT, CARD_CONFIRMED, CARD_DISCARDED]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 演示用网页片段样本：与种子模板里的选择器、种子映射规则配套，
# 让评审在不联网的情况下也能看到真实的命中节点与字段产出。
SAMPLE_HTML = """
<html><body>
  <ul class="news-list">
    <li class="news-item" data-id="101">
      <a class="title" href="/news/101.html">城区老旧管网改造完成首轮验收</a>
      <span class="publish-time">2026-11-10 09:30</span>
      <span class="view-count">阅读 1,284</span>
    </li>
    <li class="news-item" data-id="102">
      <a class="title" href="/news/102.html">新能源公交专线本周六开通试运营</a>
      <span class="publish-time">2026-11-11 14:05</span>
      <span class="view-count">阅读 860</span>
    </li>
    <li class="news-item" data-id="103">
      <a class="title" href="/news/103.html">社区养老服务中心新增夜间陪护窗口</a>
      <span class="publish-time">2026-11-12 08:12</span>
      <span class="view-count">阅读 2,031</span>
    </li>
  </ul>
  <article class="news-detail">
    <h1 class="detail-title">城区老旧管网改造完成首轮验收</h1>
    <div class="detail-body">
      <p>本轮改造覆盖十二个老旧小区，重点更换锈蚀供水管道与燃气阀门。</p>
      <p>验收组对压力测试、焊缝探伤与回填恢复逐项打分，整体合格率达到预期。</p>
    </div>
  </article>
</body></html>
"""


class ReviewService:
    def __init__(self) -> None:
        self._bootstrapped = False

    # ------------------------------------------------------------------ 基础读取
    def _bootstrap(self) -> None:
        """种子数据里没有评审卡，首次访问时补一套带真实评审证据的演示卡。"""
        if self._bootstrapped:
            return
        self._bootstrapped = True
        if store.rows(CARD_MODULE):
            return
        first = self._build_card({
            "模板id": 1,
            "候选模板版本": "v1.3.0",
            "映射版本": "MAP-2026.11",
            "映射规则ids": [1, 2, 3],
            "网页片段样本": SAMPLE_HTML,
        }, card_id=1, card_no="PUB-0001")
        self._run_stage(first, STAGE_SELECTOR)
        self._run_stage(first, STAGE_MAPPING)
        first["评审状态"] = CARD_CONFIRMED
        first["评审人"] = "值班管理员"
        first["评审说明"] = "首轮验收通过，作为采集任务默认发布依据"
        first["确认时间"] = _now()

        second = self._build_card({
            "模板id": 2,
            "候选模板版本": "v2.0.1",
            "映射版本": "",
            "映射规则ids": [],
            "网页片段样本": SAMPLE_HTML,
        }, card_id=2, card_no="PUB-0002")
        second["旧文字映射"] = True
        self._run_stage(second, STAGE_SELECTOR)
        # 映射环节故意不跑：旧文字映射视为尚未完成评审

        third = self._build_card({
            "模板id": 3,
            "候选模板版本": "v0.9.7",
            "映射版本": "MAP-2026.09",
            "映射规则ids": [1],
            "网页片段样本": SAMPLE_HTML,
        }, card_id=3, card_no="PUB-0003")
        third["评审状态"] = CARD_DISCARDED
        third["评审说明"] = "改版前的历史发布卡，已被 v1.3.0 替代"

        store.rows(CARD_MODULE).extend([first, second, third])

        # 给一条历史采集作业绑定已确认卡，快照里保留当时的样本与证据
        binding = self._snapshot_binding(1, first, binding_id=1)
        store.rows(BINDING_MODULE).append(binding)

    def _cards(self) -> list[dict[str, Any]]:
        self._bootstrap()
        return store.rows(CARD_MODULE)

    def _bindings(self) -> list[dict[str, Any]]:
        self._bootstrap()
        return store.rows(BINDING_MODULE)

    def list_cards(
        self,
        *,
        status: str | None = None,
        include_discarded: bool = True,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(self._cards())
        if not include_discarded:
            rows = [row for row in rows if row["评审状态"] != CARD_DISCARDED]
        if status:
            rows = [row for row in rows if row["评审状态"] == status]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("发布卡编号", "")) or keyword in str(row.get("候选模板版本", ""))]
        return rows

    def get_card(self, card_id: int) -> dict[str, Any] | None:
        for card in self._cards():
            if int(card.get("id", 0)) == card_id:
                return card
        return None

    # ------------------------------------------------------------------ 组装与校验
    def _next_id(self, rows: list[dict[str, Any]]) -> int:
        return max((int(row.get("id", 0)) for row in rows), default=0) + 1

    def _template_of(self, template_id: int) -> dict[str, Any] | None:
        return store.find(TEMPLATE_MODULE, template_id)

    def _rules_of(self, card: dict[str, Any]) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        for rule_id in card.get("映射规则ids", []):
            rule = store.find(EXTRACTOR_MODULE, int(rule_id))
            if rule is not None:
                rules.append(rule)
        return rules

    def _build_card(self, values: dict[str, Any], *, card_id: int | None = None, card_no: str | None = None) -> dict[str, Any]:
        template_id = int(values.get("模板id") or 0)
        rule_ids = [int(item) for item in (values.get("映射规则ids") or []) if str(item).strip()]
        new_id = card_id if card_id is not None else self._next_id(self._cards())
        new_no = card_no if card_no is not None else f"PUB-{self._next_id(self._cards()):04d}"
        return {
            "id": new_id,
            "发布卡编号": new_no,
            "模板id": template_id,
            "候选模板版本": str(values.get("候选模板版本") or "").strip(),
            "映射版本": str(values.get("映射版本") or "").strip(),
            "映射规则ids": rule_ids,
            "网页片段样本": str(values.get("网页片段样本") or ""),
            "评审状态": CARD_DRAFT,
            "选择器评审": None,
            "映射评审": None,
            "选择器通过": False,
            "映射通过": False,
            "已失效": False,
            "失效原因": "",
            "旧文字映射": not rule_ids,
            "评审人": "",
            "评审说明": "",
            "确认时间": "",
            "创建时间": _now(),
            "pending": True,
            "abnormal": False,
        }

    def _same_version_conflict(self, template_id: int, version: str, ignore_id: int | None = None) -> dict[str, Any] | None:
        """同模板下并行发布同一版本号：已确认或未废弃的同名卡都算冲突来源。"""
        for card in self._cards():
            if ignore_id is not None and int(card.get("id", 0)) == ignore_id:
                continue
            if card["评审状态"] == CARD_DISCARDED:
                continue
            if int(card.get("模板id", 0)) == template_id and card.get("候选模板版本") == version:
                return card
        return None

    def create_card(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        template_id = int(values.get("模板id") or 0)
        template = self._template_of(template_id)
        if template is None:
            return None, f"网页模板 {template_id} 不存在，无法建立评审卡"
        version = str(values.get("候选模板版本") or "").strip()
        if not version:
            return None, "候选模板版本不能为空，评审卡必须绑定具体版本号"
        if not str(values.get("网页片段样本") or "").strip():
            return None, "网页片段样本不能为空，评审需要从原文选区开始"
        conflict = self._same_version_conflict(template_id, version)
        if conflict is not None:
            return None, (
                f"版本冲突：模板 {template.get('模板编号')} 的 {version} 已存在"
                f"评审卡 {conflict['发布卡编号']}（{conflict['评审状态']}），不能并行发布同一版本号"
            )
        card = self._build_card(values)
        self._cards().append(card)
        return card, ""

    def update_card(self, card_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        card = self.get_card(card_id)
        if card is None:
            return None, f"发布评审卡 {card_id} 不存在"
        if card["评审状态"] == CARD_DISCARDED:
            return None, "废弃卡为历史留档，不能再编辑；请基于新草稿发起评审"
        if "模板id" in values and int(values.get("模板id") or 0) != int(card["模板id"]):
            return None, "评审卡与模板版本是绑定关系，不允许改挂到其他模板"
        if "候选模板版本" in values and str(values["候选模板版本"]).strip() != card["候选模板版本"]:
            new_version = str(values["候选模板版本"]).strip()
            conflict = self._same_version_conflict(int(card["模板id"]), new_version, ignore_id=card_id)
            if conflict is not None:
                return None, (
                    f"版本冲突：{new_version} 已被评审卡 {conflict['发布卡编号']} 占用，"
                    "并行发布同一版本号会让作业无法确定提取依据"
                )
            card["候选模板版本"] = new_version
        if "映射规则ids" in values:
            card["映射规则ids"] = [int(item) for item in (values.get("映射规则ids") or []) if str(item).strip()]
            card["旧文字映射"] = not card["映射规则ids"]
        if "映射版本" in values:
            card["映射版本"] = str(values["映射版本"] or "").strip()
        if "网页片段样本" in values and str(values["网页片段样本"]).strip():
            card["网页片段样本"] = str(values["网页片段样本"])
        # 任何环节修改都使原评审结论失效：清掉通过标记与证据，等待重新走流程
        self._invalidate(card, "评审卡内容已修改，原评审结论失效，需要重新完成选择器与映射评审")
        return card, ""

    def _invalidate(self, card: dict[str, Any], reason: str) -> None:
        card["已失效"] = True
        card["失效原因"] = reason
        card["选择器通过"] = False
        card["映射通过"] = False
        card["选择器评审"] = None
        card["映射评审"] = None
        if card["评审状态"] == CARD_DRAFT:
            card["pending"] = True
        card["abnormal"] = True

    def invalidate_for_template(self, template_id: int, reason: str) -> list[dict[str, Any]]:
        """模板草稿被编辑：挂在该模板下、尚未废弃的卡全部失效，已确认卡也不例外。"""
        affected: list[dict[str, Any]] = []
        for card in self._cards():
            if card["评审状态"] == CARD_DISCARDED:
                continue
            if int(card.get("模板id", 0)) == template_id:
                self._invalidate(card, reason)
                affected.append(card)
        return affected

    # ------------------------------------------------------------------ 三段式评审
    def _run_stage(self, card: dict[str, Any], stage: str) -> dict[str, Any]:
        template = self._template_of(int(card["模板id"]))
        html = str(card.get("网页片段样本") or "")
        if stage == STAGE_SELECTOR:
            result = {
                "环节": STAGE_SELECTOR,
                "评审时间": _now(),
                "列表选择器": review_engine.describe_hits(str(template.get("列表选择器") or ""), html),
                "详情选择器": review_engine.describe_hits(str(template.get("详情选择器") or ""), html),
            }
            passed = result["列表选择器"]["命中数量"] > 0 and result["详情选择器"]["命中数量"] > 0
            result["通过"] = passed
            result["结论"] = "列表与详情选择器均命中节点" if passed else "存在选择器零命中，请先回到原文选区修正"
            card["选择器评审"] = result
            card["选择器通过"] = passed
            return result

        if card.get("旧文字映射") or not card.get("映射规则ids"):
            result = {
                "环节": STAGE_MAPPING,
                "评审时间": _now(),
                "通过": False,
                "结论": "该卡沿用模板里的文字版字段映射，属于尚未完成评审的旧样例，请先绑定结构化映射规则",
                "字段": [],
            }
            card["映射评审"] = result
            card["映射通过"] = False
            return result

        result = review_engine.evaluate_mapping(html, self._rules_of(card))
        result["环节"] = STAGE_MAPPING
        result["评审时间"] = _now()
        result["结论"] = "字段映射全部产出且必填齐全" if result["通过"] else "存在必填字段缺失，映射评审不通过"
        card["映射评审"] = result
        card["映射通过"] = bool(result["通过"])
        return result

    def run_check(self, card_id: int, stage: str) -> tuple[dict[str, Any] | None, str]:
        card = self.get_card(card_id)
        if card is None:
            return None, f"发布评审卡 {card_id} 不存在"
        if card["评审状态"] == CARD_DISCARDED:
            return None, "废弃卡只保留历史证据，不能重新评审"
        if stage not in (STAGE_SELECTOR, STAGE_MAPPING):
            return None, f"评审环节「{stage}」不支持，只能从选择器或映射环节开始"
        if stage == STAGE_MAPPING and not card.get("选择器通过"):
            return None, "评审顺序不能跳步：请先完成选择器命中评审，再核对映射产出"
        result = self._run_stage(card, stage)
        # 两个环节都已基于最新内容重新评审后，失效标记才能解除；
        # 旧文字映射的卡映射环节永远不通过，也就无法解除失效并进入确认。
        if card.get("选择器通过") and card.get("映射通过"):
            card["已失效"] = False
            card["失效原因"] = ""
            card["abnormal"] = False
        return card, ""

    def confirm(self, card_id: int, reviewer: str, remark: str) -> tuple[dict[str, Any] | None, str]:
        card = self.get_card(card_id)
        if card is None:
            return None, f"发布评审卡 {card_id} 不存在"
        if card["评审状态"] == CARD_DISCARDED:
            return None, "废弃卡不能重新确认，请新建评审卡走完整流程"
        if card.get("已失效"):
            return None, "评审结论已失效（卡片或模板草稿被修改），请重新完成选择器与映射评审后再确认"
        if not card.get("选择器通过") or not card.get("映射通过"):
            return None, "确认前必须依次通过选择器命中评审与映射产出评审，不能沿用旧的通过标记"
        if card.get("旧文字映射"):
            return None, "文字版字段映射尚未完成结构化评审，不能确认发布"
        conflict = self._same_version_conflict(int(card["模板id"]), str(card["候选模板版本"]), ignore_id=card_id)
        if conflict is not None:
            return None, (
                f"版本冲突：{card['候选模板版本']} 已被评审卡 {conflict['发布卡编号']} 确认，"
                "并行发布同一版本号被拒绝"
            )
        card["评审状态"] = CARD_CONFIRMED
        card["评审人"] = reviewer or "值班管理员"
        card["评审说明"] = remark
        card["确认时间"] = _now()
        card["pending"] = False
        card["abnormal"] = False
        return card, ""

    def discard(self, card_id: int, reason: str) -> tuple[dict[str, Any] | None, str]:
        card = self.get_card(card_id)
        if card is None:
            return None, f"发布评审卡 {card_id} 不存在"
        if card["评审状态"] == CARD_DISCARDED:
            return None, "该评审卡已经是废弃状态"
        card["评审状态"] = CARD_DISCARDED
        card["评审说明"] = reason or card.get("评审说明", "")
        card["pending"] = False
        # 废弃只退出新作业选项，评审证据与样本原样保留
        return card, ""

    # ------------------------------------------------------------------ 与现用版对照
    def compare_with_current(self, card_id: int) -> tuple[dict[str, Any] | None, str]:
        card = self.get_card(card_id)
        if card is None:
            return None, f"发布评审卡 {card_id} 不存在"
        template = self._template_of(int(card["模板id"]))
        if template is None:
            return None, "关联模板已不存在，无法对照"
        current = None
        for other in self._cards():
            if (
                other["id"] != card["id"]
                and other["评审状态"] == CARD_CONFIRMED
                and int(other.get("模板id", 0)) == int(card["模板id"])
            ):
                current = other
                break
        if current is None:
            return {
                "现用卡": None,
                "提示": "该模板还没有已确认的现用发布卡，当前卡确认后将成为首个可选版本",
                "选择器差异": [],
                "字段差异": [],
                "一致": False,
            }, ""
        candidate_result = review_engine.evaluate_mapping(str(card["网页片段样本"]), self._rules_of(card))
        current_result = review_engine.evaluate_mapping(str(current["网页片段样本"]), self._rules_of(current))
        current_template = self._template_of(int(current["模板id"]))
        diff = review_engine.compare_versions(
            candidate_html=str(card["网页片段样本"]),
            candidate_list_selector=str(template.get("列表选择器") or ""),
            candidate_detail_selector=str(template.get("详情选择器") or ""),
            candidate_fields=candidate_result["字段"],
            current_html=str(current["网页片段样本"]),
            current_list_selector=str(current_template.get("列表选择器") or ""),
            current_detail_selector=str(current_template.get("详情选择器") or ""),
            current_fields=current_result["字段"],
        )
        diff["现用卡"] = {"发布卡编号": current["发布卡编号"], "候选模板版本": current["候选模板版本"]}
        diff["候选卡"] = {"发布卡编号": card["发布卡编号"], "候选模板版本": card["候选模板版本"]}
        return diff, ""

    # ------------------------------------------------------------------ 作业绑定
    def options_for_job(self, template_id: int | None = None) -> list[dict[str, Any]]:
        """新作业可选的发布依据：已确认、未失效、未废弃；废弃卡与失效卡一律不出现。"""
        options: list[dict[str, Any]] = []
        for card in self._cards():
            if card["评审状态"] != CARD_CONFIRMED or card.get("已失效"):
                continue
            if template_id and int(card.get("模板id", 0)) != template_id:
                continue
            options.append({
                "发布卡id": card["id"],
                "发布卡编号": card["发布卡编号"],
                "模板id": card["模板id"],
                "候选模板版本": card["候选模板版本"],
                "映射版本": card["映射版本"],
                "确认时间": card["确认时间"],
            })
        return options

    def _snapshot_binding(self, job_id: int, card: dict[str, Any], *, binding_id: int | None = None) -> dict[str, Any]:
        return {
            "id": binding_id if binding_id is not None else self._next_id(self._bindings()),
            "作业id": job_id,
            "发布卡id": card["id"],
            "发布卡编号": card["发布卡编号"],
            "绑定时间": _now(),
            "依据快照": {
                "候选模板版本": card["候选模板版本"],
                "映射版本": card["映射版本"],
                "网页片段样本": card["网页片段样本"],
                "选择器评审": card.get("选择器评审"),
                "映射评审": card.get("映射评审"),
            },
        }

    def bind_job(self, job_id: int, card_id: int) -> tuple[dict[str, Any] | None, str]:
        if store.find("spider", job_id) is None:
            return None, f"采集作业 {job_id} 不存在，无法绑定发布依据"
        card = self.get_card(card_id)
        if card is None:
            return None, f"发布评审卡 {card_id} 不存在"
        if card["评审状态"] != CARD_CONFIRMED or card.get("已失效"):
            return None, "只有已确认且未失效的发布卡才能作为采集任务的提取依据"
        for binding in self._bindings():
            if int(binding.get("作业id", 0)) == job_id:
                return None, f"该作业已绑定发布卡 {binding['发布卡编号']}，历史提取依据不允许覆盖"
        binding = self._snapshot_binding(job_id, card)
        self._bindings().append(binding)
        return binding, ""

    def get_job_binding(self, job_id: int) -> dict[str, Any] | None:
        for binding in self._bindings():
            if int(binding.get("作业id", 0)) == job_id:
                return binding
        return None

    def list_bindings(self) -> list[dict[str, Any]]:
        return list(self._bindings())


review_service = ReviewService()
