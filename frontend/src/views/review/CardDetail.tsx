import { useState } from 'react'

import { compareCard, confirmCard, discardCard, runStageCheck } from './api'
import type { CompareResult, MappedField, ReviewCard, SelectorReview } from './types'

interface Props {
  card: ReviewCard
  onChanged: () => Promise<void>
  onMessage: (message: string, ok: boolean) => void
}

const stageBadgeClass = (passed: boolean) => (passed ? 'stage-badge pass' : 'stage-badge pending')

function SelectorEvidence({ review }: { review: SelectorReview }) {
  return (
    <div className="evidence-block">
      <div className="evidence-head">
        <code>{review.选择器}</code>
        <span className={stageBadgeClass(review.命中数量 > 0)}>
          命中 {review.命中数量} 个节点
        </span>
      </div>
      {review.命中节点.length === 0 ? (
        <p className="hint warn">零命中：请回到原文选区修正选择器</p>
      ) : (
        <ul className="hit-list">
          {review.命中节点.map((hit, index) => (
            <li key={`${hit.路径}-${index}`}>
              <code className="node-path">{hit.路径}</code>
              <span className="node-text">{hit.文本预览 || '（无文本节点）'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function FieldEvidence({ field }: { field: MappedField }) {
  return (
    <tr className={field.命中 ? '' : 'row-warn'}>
      <td>{field.目标字段}{field.必填 && <em className="required">必填</em>}</td>
      <td><code>{field.源选择器}</code></td>
      <td>{field.声明类型}</td>
      <td className="raw-text">{field.原始文本 || '—'}</td>
      <td>
        <strong>{field.产出取值 === null || field.产出取值 === '' ? '空' : String(field.产出取值)}</strong>
        {field.使用默认值 && <span className="tag">默认值</span>}
      </td>
    </tr>
  )
}

export default function CardDetail({ card, onChanged, onMessage }: Props) {
  const [compare, setCompare] = useState<CompareResult | null>(null)
  const [remark, setRemark] = useState('')
  const [discardReason, setDiscardReason] = useState('')
  const [busy, setBusy] = useState(false)
  const discarded = card.评审状态 === '已废弃'

  async function handleStage(stage: string) {
    setBusy(true)
    try {
      const result = await runStageCheck(card.id, stage)
      onMessage(result.message, result.ok)
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function handleConfirm() {
    setBusy(true)
    try {
      const result = await confirmCard(card.id, '值班管理员', remark)
      onMessage(result.message, result.ok)
      if (result.ok) {
        setRemark('')
        setCompare(null)
      }
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function handleDiscard() {
    if (!discardReason.trim()) {
      onMessage('废弃前请填写原因，便于历史留档追溯', false)
      return
    }
    setBusy(true)
    try {
      const result = await discardCard(card.id, discardReason)
      onMessage(result.message, result.ok)
      if (result.ok) setDiscardReason('')
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function handleCompare() {
    setBusy(true)
    try {
      const result = await compareCard(card.id)
      if (result.ok && result.entry) setCompare(result.entry)
      onMessage(result.message, result.ok)
    } finally {
      setBusy(false)
    }
  }

  const selectorLocked = !card.选择器通过
  const canConfirm = card.选择器通过 && card.映射通过 && !card.已失效 && !discarded

  return (
    <article className={`card-detail ${discarded ? 'is-discarded' : ''}`}>
      <header className="detail-head">
        <div>
          <h4>
            {card.发布卡编号}
            <span className="version-tag">模板版本 {card.候选模板版本}</span>
            {card.映射版本 && <span className="version-tag">映射版本 {card.映射版本}</span>}
          </h4>
          <p className="hint">
            模板 id：{card.模板id} · 创建于 {card.创建时间}
            {card.确认时间 && ` · 确认于 ${card.确认时间}（${card.评审人}）`}
          </p>
        </div>
        <div className="status-flags">
          <span className={`state-pill state-${card.评审状态}`}>{card.评审状态}</span>
          {card.旧文字映射 && <span className="state-pill state-legacy">旧文字映射·未完成评审</span>}
          {card.已失效 && <span className="state-pill state-invalid">结论已失效</span>}
        </div>
      </header>

      {card.已失效 && (
        <div className="invalid-banner">
          原评审结论已失效：{card.失效原因}。修改后不能沿用旧的通过标记，请依次重跑两个评审环节。
        </div>
      )}

      <section className="stage-section">
        <div className="stage-title">
          <span className={stageBadgeClass(card.选择器通过)}>
            第一步 · 选择器命中 {card.选择器通过 ? '✓' : '○'}
          </span>
          <button className="btn small" type="button" disabled={busy || discarded} onClick={() => void handleStage('选择器')}>
            执行选择器评审
          </button>
        </div>
        {card.选择器评审 ? (
          <>
            <SelectorEvidence review={card.选择器评审.列表选择器} />
            <SelectorEvidence review={card.选择器评审.详情选择器} />
            <p className={`stage-conclusion ${card.选择器评审.通过 ? 'ok' : 'warn'}`}>{card.选择器评审.结论}</p>
          </>
        ) : (
          <p className="hint">尚未评审：先看列表与详情选择器在原文选区上命中了哪些节点。</p>
        )}
      </section>

      <section className="stage-section">
        <div className="stage-title">
          <span className={stageBadgeClass(card.映射通过)}>
            第二步 · 映射产出 {card.映射通过 ? '✓' : '○'}
          </span>
          <button
            className="btn small"
            type="button"
            disabled={busy || discarded || selectorLocked}
            title={selectorLocked ? '请先通过选择器命中评审' : ''}
            onClick={() => void handleStage('映射')}
          >
            执行映射评审
          </button>
        </div>
        {selectorLocked && <p className="hint warn">评审顺序不能跳步：选择器通过后才能核对映射产出。</p>}
        {card.映射评审 ? (
          card.映射评审.字段.length === 0 ? (
            <p className="hint warn">{card.映射评审.结论}</p>
          ) : (
            <>
              <table className="data-table evidence-table">
                <thead>
                  <tr><th>目标字段</th><th>源选择器</th><th>声明类型</th><th>原始文本</th><th>产出取值</th></tr>
                </thead>
                <tbody>
                  {card.映射评审.字段.map((field) => (
                    <FieldEvidence key={field.目标字段} field={field} />
                  ))}
                </tbody>
              </table>
              {card.映射评审.缺失必填.length > 0 && (
                <p className="hint warn">缺失必填字段：{card.映射评审.缺失必填.join('、')}</p>
              )}
              <p className={`stage-conclusion ${card.映射评审.通过 ? 'ok' : 'warn'}`}>{card.映射评审.结论}</p>
            </>
          )
        ) : (
          <p className="hint">尚未评审：逐字段核对取值、类型转换与默认值填充。</p>
        )}
      </section>

      <section className="stage-section">
        <div className="stage-title">
          <span className={stageBadgeClass(card.评审状态 === '已确认')}>
            第三步 · 人工确认 {card.评审状态 === '已确认' ? '✓' : '○'}
          </span>
          <button className="btn small" type="button" disabled={busy || discarded} onClick={() => void handleCompare()}>
            与现用版对照
          </button>
        </div>
        {compare && (
          <div className="compare-panel">
            {compare.现用卡 ? (
              <p className="hint">
                现用版：{compare.现用卡.发布卡编号}（{compare.现用卡.候选模板版本}）
                {compare.一致 && <span className="tag ok">两版证据一致</span>}
              </p>
            ) : (
              <p className="hint">{compare.提示}</p>
            )}
            {compare.选择器差异.length > 0 && (
              <div>
                <h5>选择器差异（少提 / 多提）</h5>
                <ul className="diff-list">
                  {compare.选择器差异.map((diff, index) => (
                    <li key={`s-${index}`} className={`diff diff-${diff.差异}`}>
                      <span className="diff-kind">{diff.差异}</span>{diff.说明}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {compare.字段差异.length > 0 && (
              <div>
                <h5>字段差异（少提 / 多提 / 类型转换不符 / 取值变化）</h5>
                <ul className="diff-list">
                  {compare.字段差异.map((diff, index) => (
                    <li key={`f-${index}`} className={`diff diff-${diff.差异}`}>
                      <span className="diff-kind">{diff.差异}</span>
                      {diff.目标字段 ? `【${diff.目标字段}】` : ''}{diff.说明}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        <div className="confirm-row">
          <input
            className="remark-input"
            placeholder="评审说明（可选）"
            value={remark}
            onChange={(event) => setRemark(event.target.value)}
            disabled={discarded}
          />
          <button className="btn primary small" type="button" disabled={busy || !canConfirm} onClick={() => void handleConfirm()}>
            确认为可选版本
          </button>
        </div>
        {!canConfirm && !discarded && (
          <p className="hint warn">
            {card.已失效
              ? '结论失效中，重跑两个环节后才能确认'
              : '需依次通过选择器与映射评审，确认后才进入采集任务可选版本池'}
          </p>
        )}
      </section>

      {!discarded && (
        <section className="stage-section discard-section">
          <div className="stage-title"><span className="stage-badge pending">废弃留档</span></div>
          <div className="confirm-row">
            <input
              className="remark-input"
              placeholder="废弃原因（废弃后只退出新作业选项，历史作业证据保留）"
              value={discardReason}
              onChange={(event) => setDiscardReason(event.target.value)}
            />
            <button className="btn danger small" type="button" disabled={busy} onClick={() => void handleDiscard()}>
              废弃该卡
            </button>
          </div>
        </section>
      )}
      {discarded && <p className="hint">废弃原因：{card.评审说明 || '未填写'}。卡片仅从新作业选项退出，样本与映射证据继续留档。</p>}
    </article>
  )
}
