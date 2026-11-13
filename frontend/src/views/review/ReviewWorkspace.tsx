import { useEffect, useState } from 'react'

import { createCard, fetchSampleHtml, updateCard } from './api'
import type { MappingRuleOption, ReviewCard, ReviewContext, TemplateOption } from './types'

interface Props {
  context: ReviewContext
  editing: ReviewCard | null
  onDone: () => Promise<void>
  onMessage: (message: string, ok: boolean) => void
}

interface FormState {
  模板id: number
  候选模板版本: string
  映射版本: string
  映射规则ids: number[]
  网页片段样本: string
}

const emptyForm = (templates: TemplateOption[]): FormState => ({
  模板id: templates[0]?.id ?? 0,
  候选模板版本: '',
  映射版本: '',
  映射规则ids: [],
  网页片段样本: '',
})

export default function ReviewWorkspace({ context, editing, onDone, onMessage }: Props) {
  const [form, setForm] = useState<FormState>(() => emptyForm(context.templates))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (editing) {
      setForm({
        模板id: editing.模板id,
        候选模板版本: editing.候选模板版本,
        映射版本: editing.映射版本,
        映射规则ids: [...editing.映射规则ids],
        网页片段样本: editing.网页片段样本,
      })
    } else {
      setForm(emptyForm(context.templates))
    }
  }, [editing, context.templates])

  const selectedTemplate = context.templates.find((item) => item.id === form.模板id)

  function patch(values: Partial<FormState>) {
    setForm((prev) => ({ ...prev, ...values }))
  }

  function toggleRule(rule: MappingRuleOption) {
    const exists = form.映射规则ids.includes(rule.id)
    patch({
      映射规则ids: exists
        ? form.映射规则ids.filter((id) => id !== rule.id)
        : [...form.映射规则ids, rule.id],
    })
  }

  async function loadSample() {
    const html = await fetchSampleHtml()
    patch({ 网页片段样本: html })
  }

  async function submit() {
    setSaving(true)
    try {
      const payload: Record<string, unknown> = { ...form }
      const result = editing ? await updateCard(editing.id, payload) : await createCard(payload)
      onMessage(result.message, result.ok)
      if (result.ok) {
        setForm(emptyForm(context.templates))
        await onDone()
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="workspace">
      <h3>{editing ? `编辑评审卡 ${editing.发布卡编号}` : '新建发布评审卡'}</h3>
      {editing && (
        <p className="hint warn">
          任一环节保存都会使该卡原评审结论失效，通过标记清空，需要重新走 选择器 → 映射 → 确认 流程。
        </p>
      )}
      <div className="form-grid">
        <label className="form-item">
          <span>候选模板版本（绑定模板）</span>
          <select
            value={form.模板id}
            disabled={Boolean(editing)}
            onChange={(event) => patch({ 模板id: Number(event.target.value) })}
          >
            {context.templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.模板编号} · 当前版本 {template.模板版本}
              </option>
            ))}
          </select>
        </label>
        <label className="form-item">
          <span>发布版本号</span>
          <input
            placeholder="例如 v1.4.0；同模板并行发布同版本号会报冲突"
            value={form.候选模板版本}
            onChange={(event) => patch({ 候选模板版本: event.target.value })}
          />
        </label>
        <label className="form-item">
          <span>字段映射版本</span>
          <input
            placeholder="例如 MAP-2026.12"
            value={form.映射版本}
            onChange={(event) => patch({ 映射版本: event.target.value })}
          />
        </label>
      </div>

      {selectedTemplate && (
        <div className="selector-preview">
          <span>模板当前选择器：</span>
          <code>列表 {selectedTemplate.列表选择器}</code>
          <code>详情 {selectedTemplate.详情选择器}</code>
        </div>
      )}

      <div className="form-item">
        <span>结构化字段映射规则（不选则视为旧文字映射，不能完成评审）</span>
        <div className="rule-picker">
          {context.mapping_rules.map((rule) => (
            <label key={rule.id} className={`rule-chip ${form.映射规则ids.includes(rule.id) ? 'active' : ''}`}>
              <input type="checkbox" checked={form.映射规则ids.includes(rule.id)} onChange={() => toggleRule(rule)} />
              <span>
                <strong>{rule.规则编号}</strong>
                <code>{rule.源字段名称}</code> → <code>{rule.目标字段名称}</code>
                <em>{rule.数据类型转换}</em>
              </span>
            </label>
          ))}
        </div>
      </div>

      <label className="form-item">
        <span>网页片段样本（评审从原文选区开始）</span>
        <textarea
          rows={8}
          placeholder="粘贴列表页/详情页 HTML 片段，选择器命中与映射产出都基于这份样本"
          value={form.网页片段样本}
          onChange={(event) => patch({ 网页片段样本: event.target.value })}
        />
      </label>
      <div className="workspace-actions">
        <button className="btn" type="button" onClick={() => void loadSample()}>载入演示样本</button>
        <button className="btn primary" type="button" disabled={saving} onClick={() => void submit()}>
          {editing ? '保存修改并作废旧结论' : '建立评审卡'}
        </button>
        {editing && (
          <button className="btn ghost" type="button" onClick={() => void onDone()}>取消编辑</button>
        )}
      </div>
    </div>
  )
}
