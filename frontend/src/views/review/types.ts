/** 发布评审卡相关的接口类型，字段命名与后端返回保持一致（中文业务键）。 */

export interface ActionResult<T = unknown> {
  ok: boolean
  message: string
  entry?: T
}

export interface SelectorHit {
  路径: string
  标签: string
  文本预览: string
}

export interface SelectorReview {
  选择器: string
  命中数量: number
  命中节点: SelectorHit[]
}

export interface SelectorStageResult {
  环节: string
  评审时间: string
  列表选择器: SelectorReview
  详情选择器: SelectorReview
  通过: boolean
  结论: string
}

export interface MappedField {
  目标字段: string
  源选择器: string
  声明类型: string
  命中: boolean
  原始文本: string
  产出取值: unknown
  使用默认值: boolean
  必填: boolean
}

export interface MappingStageResult {
  环节: string
  评审时间: string
  通过: boolean
  结论: string
  字段数量: number
  字段: MappedField[]
  缺失必填: string[]
}

export interface DiffItem {
  环节?: string
  节点?: string
  目标字段?: string
  差异: string
  说明: string
}

export interface CompareResult {
  一致: boolean
  提示?: string
  选择器差异: DiffItem[]
  字段差异: DiffItem[]
  现用卡: { 发布卡编号: string; 候选模板版本: string } | null
  候选卡?: { 发布卡编号: string; 候选模板版本: string }
}

export interface ReviewCard {
  id: number
  发布卡编号: string
  模板id: number
  候选模板版本: string
  映射版本: string
  映射规则ids: number[]
  网页片段样本: string
  评审状态: '待评审' | '已确认' | '已废弃'
  选择器评审: SelectorStageResult | null
  映射评审: MappingStageResult | null
  选择器通过: boolean
  映射通过: boolean
  已失效: boolean
  失效原因: string
  旧文字映射: boolean
  评审人: string
  评审说明: string
  确认时间: string
  创建时间: string
}

export interface TemplateOption {
  id: number
  模板编号: string
  模板版本: string
  列表选择器: string
  详情选择器: string
  字段映射: string
  status: string
}

export interface MappingRuleOption {
  id: number
  规则编号: string
  源字段名称: string
  目标字段名称: string
  数据类型转换: string
  必填标识: string
}

export interface ReviewContext {
  templates: TemplateOption[]
  mapping_rules: MappingRuleOption[]
  评审状态: string[]
  评审环节: string[]
}

export interface JobOption {
  发布卡id: number
  发布卡编号: string
  模板id: number
  候选模板版本: string
  映射版本: string
  确认时间: string
}

export interface BindingSnapshot {
  id: number
  作业id: number
  发布卡id: number
  发布卡编号: string
  绑定时间: string
  依据快照: {
    候选模板版本: string
    映射版本: string
    网页片段样本: string
    选择器评审: SelectorStageResult | null
    映射评审: MappingStageResult | null
  }
}
