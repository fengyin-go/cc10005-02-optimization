"""发布评审的离线解析引擎。

评审要在「不真正发起采集」的前提下回答三件事：
1. 列表/详情选择器在给定网页片段上命中了哪些节点；
2. 字段映射版本在这些节点上产出了哪些字段、取值与类型；
3. 候选版本与现用版本逐项对照时差在哪里（少提、多提、类型转换不符）。

只依赖标准库：html.parser 建树，正则解析一小撮 CSS 选择器
（标签、.class、#id、[attr]、[attr=value]、后代空格与子选择器 >、逗号分组），
足够覆盖模板编辑区里人工维护的选择器，又不用引入第三方解析依赖。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
TRUTHY_WORDS = {"是", "true", "1", "yes", "y", "on"}


def normalize_space(text: str) -> str:
    """把换行与连续空白压成单个空格，便于评审界面稳定展示。"""
    return re.sub(r"\s+", " ", text or "").strip()


@dataclass
class DomNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["DomNode"] = field(default_factory=list)
    parent: "DomNode | None" = None
    text_parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text)
        return normalize_space("".join(parts))

    def path(self) -> str:
        """生成节点在文档里的唯一定位路径，用于对照时说明「哪个节点少提/多提」。"""
        chain: list[str] = []
        current: DomNode | None = self
        while current is not None and current.tag != "#root":
            siblings = [sib for sib in (current.parent.children if current.parent else []) if sib.tag == current.tag]
            index = siblings.index(current) if current in siblings else 0
            label = current.tag
            if current.attrs.get("id"):
                label += f"#{current.attrs['id']}"
            classes = current.attrs.get("class", "").split()
            if classes:
                label += "." + ".".join(classes[:2])
            chain.append(f"{label}[{index}]")
            current = current.parent
        return " > ".join(reversed(chain))


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = DomNode(tag="#root")
        self._stack: list[DomNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = DomNode(
            tag=tag.lower(),
            attrs={str(key).lower(): value or "" for key, value in attrs},
        )
        node.parent = self._stack[-1]
        self._stack[-1].children.append(node)
        if tag.lower() not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = DomNode(
            tag=tag.lower(),
            attrs={str(key).lower(): value or "" for key, value in attrs},
        )
        node.parent = self._stack[-1]
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for depth in range(len(self._stack) - 1, 0, -1):
            if self._stack[depth].tag == tag:
                del self._stack[depth:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].text_parts.append(data)


def parse_html(html: str) -> DomNode:
    """把网页片段样本解析成一棵可遍历的最小 DOM 树。"""
    builder = _TreeBuilder()
    builder.feed(html or "")
    builder.close()
    return builder.root


def walk(node: DomNode) -> list[DomNode]:
    """按文档顺序展平整棵子树（含节点自身）。"""
    result = [node]
    for child in node.children:
        result.extend(walk(child))
    return result


def _make_predicate(token: str) -> Callable[[DomNode], bool]:
    if token.startswith("."):
        class_name = token[1:]
        return lambda n: class_name in n.attrs.get("class", "").split()
    if token.startswith("#"):
        node_id = token[1:]
        return lambda n: n.attrs.get("id") == node_id
    if token.startswith("["):
        body = token[1:-1].strip()
        if "=" in body:
            key, value = body.split("=", 1)
            value = value.strip().strip("\"'")
            return lambda n: n.attrs.get(key.strip()) == value
        return lambda n: body in n.attrs
    tag = token.lower()
    return lambda n: n.tag == tag


def _parse_compound(compound: str) -> list[Callable[[DomNode], bool]]:
    return [_make_predicate(match.group(0)) for match in re.finditer(r"[#.]?[\w-]+|\[[^\]]+\]", compound)]


def _parse_group(group: str) -> list[tuple[str, list[Callable[[DomNode], bool]]]]:
    """把一条选择器拆成 (组合符, 谓词列表) 步骤，组合符只支持后代空格与 >。

    用 finditer 顺序取词，避免 re.split 捕获组把空串和组合符混进步骤序列；
    复合词（如 li.news-item、a.title[href]）整体识别，不能拆成多个步骤。
    """
    steps: list[tuple[str, list[Callable[[DomNode], bool]]]] = []
    combinator = " "
    for match in re.finditer(r"\s*>\s*|\s+|[\w-]+(?:[#.][\w-]+|\[[^\]]+\])*|#[\w-]+|\.[\w-]+|\[[^\]]+\]", group.strip()):
        token = match.group(0).strip()
        if not token:
            continue
        if token == ">":
            combinator = ">"
        else:
            steps.append((combinator, _parse_compound(token)))
            combinator = " "
    return steps


def _match_compound(node: DomNode, predicates: list[Callable[[DomNode], bool]]) -> bool:
    return all(predicate(node) for predicate in predicates)


def _match_steps(node: DomNode, steps: list[tuple[str, list[Callable[[DomNode], bool]]]]) -> bool:
    if not steps or not _match_compound(node, steps[-1][1]):
        return False
    current = node
    for combinator, predicates in reversed(steps[:-1]):
        candidate = current.parent
        found: DomNode | None = None
        while candidate is not None and candidate.tag != "#root":
            if _match_compound(candidate, predicates):
                found = candidate
                break
            if combinator == ">":
                # 子选择器只看紧邻父节点，不向上爬
                break
            candidate = candidate.parent
        if found is None:
            return False
        current = found
    return True


def select_all(root: DomNode, selector: str) -> list[DomNode]:
    """按选择器分组在子树内取全部命中节点，保持文档顺序、去重。"""
    if not normalize_space(selector):
        return []
    groups = [_parse_group(group) for group in selector.split(",") if group.strip()]
    matched: list[DomNode] = []
    for node in walk(root):
        if node.tag == "#root":
            continue
        if any(_match_steps(node, steps) for steps in groups):
            matched.append(node)
    return matched


def select_one(root: DomNode, selector: str) -> DomNode | None:
    nodes = select_all(root, selector)
    return nodes[0] if nodes else None


def describe_hits(selector: str, html: str) -> dict[str, Any]:
    """选择器评审：回传命中数量、节点路径与文本预览，告诉评审人「命中了哪些节点」。"""
    root = parse_html(html)
    nodes = select_all(root, selector)
    return {
        "选择器": selector,
        "命中数量": len(nodes),
        "命中节点": [
            {"路径": node.path(), "标签": node.tag, "文本预览": node.text[:80]}
            for node in nodes[:20]
        ],
    }


_SOURCE_SUFFIX_RE = re.compile(r"^(.*?)(?:::(attr\(([\w-]+)\)|text))?$")


def _split_source(source: str) -> tuple[str, str | None]:
    """拆「选择器::text / 选择器::attr(href)」形式的源字段，返回 (基础选择器, 属性名)。"""
    match = _SOURCE_SUFFIX_RE.match(source.strip())
    if not match:
        return source.strip(), None
    base = match.group(1).strip()
    attribute = match.group(3)
    return base, attribute


def _coerce_value(raw: str, data_type: str) -> Any:
    """按声明的目标类型做转换；转不出来时回退 None，由默认值/必填校验接手。"""
    kind = (data_type or "string").strip().lower()
    if kind in ("int", "integer", "整数", "数字"):
        cleaned = re.sub(r"[^\d-]", "", raw)
        return int(cleaned) if cleaned not in ("", "-") else None
    if kind in ("float", "decimal", "小数"):
        cleaned = re.sub(r"[^\d.\-]", "", raw)
        try:
            return float(cleaned) if cleaned not in ("", "-", ".") else None
        except ValueError:
            return None
    if kind in ("bool", "boolean", "布尔"):
        return raw.strip().lower() in TRUTHY_WORDS
    return raw


def _is_required(rule: dict[str, Any]) -> bool:
    return str(rule.get("必填标识") or "").strip().lower() in TRUTHY_WORDS


def evaluate_mapping(html: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
    """映射评审：在网页片段上跑一遍结构化映射规则，逐字段给出取值与类型证据。"""
    root = parse_html(html)
    fields: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for rule in rules:
        source = str(rule.get("源字段名称") or "").strip()
        target = str(rule.get("目标字段名称") or source).strip()
        data_type = str(rule.get("数据类型转换") or "string").strip()
        default = rule.get("默认填充值")
        base_selector, attribute = _split_source(source)
        node = select_one(root, base_selector)
        hit = node is not None
        raw_value = ""
        if node is not None:
            raw_value = node.attrs.get(attribute or "", "") if attribute else node.text
        value = _coerce_value(raw_value, data_type)
        used_default = False
        if value in (None, "") and default not in (None, ""):
            value = default
            used_default = True
        required = _is_required(rule)
        if required and value in (None, ""):
            missing_required.append(target)
        fields.append({
            "目标字段": target,
            "源选择器": source,
            "声明类型": data_type,
            "命中": hit,
            "原始文本": normalize_space(raw_value)[:120],
            "产出取值": value,
            "使用默认值": used_default,
            "必填": required,
        })
    return {
        "字段数量": len(fields),
        "字段": fields,
        "缺失必填": missing_required,
        "通过": not missing_required,
    }


def _node_signatures(selector: str, html: str) -> set[str]:
    return {node.path() for node in select_all(parse_html(html), selector)}


def compare_versions(
    *,
    candidate_html: str,
    candidate_list_selector: str,
    candidate_detail_selector: str,
    candidate_fields: list[dict[str, Any]],
    current_html: str,
    current_list_selector: str,
    current_detail_selector: str,
    current_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """候选卡与现用版逐项对照：选择器层面看少提/多提，字段层面看少提、多提、类型不符与取值变化。"""
    selector_diff: list[dict[str, str]] = []
    for scope, candidate_selector, current_selector in (
        ("列表选择器", candidate_list_selector, current_list_selector),
        ("详情选择器", candidate_detail_selector, current_detail_selector),
    ):
        candidate_hits = _node_signatures(candidate_selector, candidate_html)
        current_hits = _node_signatures(current_selector, current_html)
        for signature in sorted(current_hits - candidate_hits):
            selector_diff.append({"环节": scope, "差异": "少提", "节点": signature,
                                  "说明": f"现用版能命中 {signature}，候选版本未命中"})
        for signature in sorted(candidate_hits - current_hits):
            selector_diff.append({"环节": scope, "差异": "多提", "节点": signature,
                                  "说明": f"候选版本新命中 {signature}，现用版没有该节点"})

    candidate_index = {item["目标字段"]: item for item in candidate_fields}
    current_index = {item["目标字段"]: item for item in current_fields}
    field_diff: list[dict[str, str]] = []
    for name in sorted(current_index.keys() - candidate_index.keys()):
        field_diff.append({"目标字段": name, "差异": "少提", "说明": "现用版产出该字段，候选版本未配置映射"})
    for name in sorted(candidate_index.keys() - current_index.keys()):
        field_diff.append({"目标字段": name, "差异": "多提", "说明": "候选版本新增了该字段映射，现用版不产出"})
    for name in sorted(candidate_index.keys() & current_index.keys()):
        candidate_item = candidate_index[name]
        current_item = current_index[name]
        if candidate_item.get("声明类型") != current_item.get("声明类型"):
            field_diff.append({
                "目标字段": name,
                "差异": "类型转换不符",
                "说明": f"现用版声明 {current_item.get('声明类型')}，候选版本声明 {candidate_item.get('声明类型')}",
            })
        elif candidate_item.get("产出取值") != current_item.get("产出取值"):
            field_diff.append({
                "目标字段": name,
                "差异": "取值变化",
                "说明": f"现用版取值 {current_item.get('产出取值')!r}，候选版本取值 {candidate_item.get('产出取值')!r}",
            })
    return {
        "选择器差异": selector_diff,
        "字段差异": field_diff,
        "一致": not selector_diff and not field_diff,
    }
