import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

import { fetchCards, fetchContext, fetchJobBinding, fetchJobOptions, bindJob } from './api'
import CardDetail from './CardDetail'
import type { BindingSnapshot, JobOption, ReviewCard, ReviewContext } from './types'
import ReviewWorkspace from './ReviewWorkspace'

const STATUS_FILTERS = ['全部', '待评审', '已确认', '已废弃'] as const

interface SpiderRow {
  id: number
  作业编号: string
}

export default function ReviewView() {
  const [context, setContext] = useState<ReviewContext | null>(null)
  const [cards, setCards] = useState<ReviewCard[]>([])
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>('全部')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editing, setEditing] = useState<ReviewCard | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [jobs, setJobs] = useState<SpiderRow[]>([])
  const [jobOptions, setJobOptions] = useState<JobOption[]>([])
  const [pickedJob, setPickedJob] = useState<number>(2)
  const [pickedCard, setPickedCard] = useState<number>(0)
  const [binding, setBinding] = useState<BindingSnapshot | null>(null)

  const showMessage = useCallback((text: string, ok: boolean) => {
    setMessage({ text, ok })
  }, [])

  const reload = useCallback(async () => {
    const [ctx, cardRows, spiderResp] = await Promise.all([
      fetchContext(),
      fetchCards(),
      request('/api/spider?page=1&size=50'),
    ])
    setContext(ctx)
    setCards(cardRows)
    const spiderPayload = (await spiderResp.json()) as { items: SpiderRow[] }
    setJobs(spiderPayload.items ?? [])
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const reloadJobPanel = useCallback(async () => {
    const options = await fetchJobOptions()
    setJobOptions(options)
    if (options.length && !options.some((item) => item.发布卡id === pickedCard)) {
      setPickedCard(options[0].发布卡id)
    }
    const result = await fetchJobBinding(pickedJob)
    setBinding(result.ok ? result.entry ?? null : null)
  }, [pickedJob, pickedCard])

  useEffect(() => {
    void reloadJobPanel()
  }, [reloadJobPanel])

  const visibleCards = useMemo(
    () => (statusFilter === '全部' ? cards : cards.filter((card) => card.评审状态 === statusFilter)),
    [cards, statusFilter],
  )
  const selected = cards.find((card) => card.id === selectedId) ?? null

  const stats = useMemo(() => ({
    total: cards.length,
    confirmed: cards.filter((card) => card.评审状态 === '已确认').length,
    invalid: cards.filter((card) => card.已失效 && card.评审状态 !== '已废弃').length,
    legacy: cards.filter((card) => card.旧文字映射 && card.评审状态 !== '已废弃').length,
  }), [cards])

  async function handleBind() {
    const result = await bindJob(pickedJob, pickedCard)
    showMessage(result.message, result.ok)
    if (result.ok) {
      const refreshed = await fetchJobBinding(pickedJob)
      setBinding(refreshed.entry ?? null)
    }
  }

  if (!context) {
    return <section className="page"><p className="hint">评审上下文加载中…</p></section>
  }

  return (
    <section className="page review-page" data-module="review">
      <header className="page-head">
        <div>
          <h2>发布评审</h2>
          <p className="page-desc">
            把候选模板版本、字段映射版本与网页片段样本绑成评审卡，按「选择器命中 → 映射产出 → 人工确认」推进；
            任何环节修改都会作废旧结论，采集任务只选取经确认的发布卡。
          </p>
        </div>
      </header>

      <div className="stat-row">
        <article className="stat-card"><span className="stat-label">评审卡总数</span><strong className="stat-value">{stats.total}</strong></article>
        <article className="stat-card"><span className="stat-label">已确认可选版本</span><strong className="stat-value">{stats.confirmed}</strong></article>
        <article className="stat-card"><span className="stat-label">结论失效待重评</span><strong className="stat-value">{stats.invalid}</strong></article>
        <article className="stat-card"><span className="stat-label">旧文字映射未完成</span><strong className="stat-value">{stats.legacy}</strong></article>
      </div>

      {message && (
        <div className={`flash ${message.ok ? 'flash-ok' : 'flash-error'}`}>
          {message.text}
          <button className="link" type="button" onClick={() => setMessage(null)}>关闭</button>
        </div>
      )}

      <ReviewWorkspace context={context} editing={editing} onDone={async () => { setEditing(null); await reload() }} onMessage={showMessage} />

      <div className="filter-bar status-filter">
        {STATUS_FILTERS.map((status) => (
          <button
            key={status}
            type="button"
            className={`btn small ${statusFilter === status ? 'primary' : ''}`}
            onClick={() => setStatusFilter(status)}
          >
            {status}
          </button>
        ))}
      </div>

      <div className="review-layout">
        <div className="card-list-panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>发布卡</th><th>模板/版本</th><th>评审状态</th><th>两环节</th><th>标记</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleCards.map((card) => (
                <tr key={card.id} className={selectedId === card.id ? 'row-selected' : ''}>
                  <td>
                    <button className="link" type="button" onClick={() => setSelectedId(card.id)}>{card.发布卡编号}</button>
                  </td>
                  <td>
                    <span>TEMP-{String(card.模板id).padStart(4, '0')}</span>
                    <br /><code>{card.候选模板版本}</code>
                  </td>
                  <td><span className={`state-pill state-${card.评审状态}`}>{card.评审状态}</span></td>
                  <td className="stage-dots">
                    <span className={card.选择器通过 ? 'dot pass' : 'dot'}>选择器</span>
                    <span className={card.映射通过 ? 'dot pass' : 'dot'}>映射</span>
                  </td>
                  <td>
                    {card.已失效 && <span className="state-pill state-invalid">失效</span>}
                    {card.旧文字映射 && <span className="state-pill state-legacy">旧文字</span>}
                  </td>
                  <td>
                    {card.评审状态 !== '已废弃' && (
                      <button
                        className="link"
                        type="button"
                        onClick={() => { setEditing(card); setSelectedId(card.id) }}
                      >
                        编辑
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {visibleCards.length === 0 && (
                <tr><td className="empty-state" colSpan={6}>当前筛选下暂无评审卡</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card-detail-panel">
          {selected ? (
            <CardDetail card={selected} onChanged={reload} onMessage={showMessage} />
          ) : (
            <p className="hint">从左侧选择一张评审卡，查看选择器命中节点、映射产出证据与版本对照。</p>
          )}
        </div>
      </div>

      <section className="job-binding-panel">
        <h3>采集任务选取发布依据</h3>
        <p className="hint">
          下拉只列出已确认、未失效、未废弃的发布卡；绑定时刻固化样本与映射证据快照，
          之后再编辑草稿不会改变这次作业的提取依据。
        </p>
        <div className="binding-row">
          <label className="form-item">
            <span>采集作业</span>
            <select value={pickedJob} onChange={(event) => setPickedJob(Number(event.target.value))}>
              {jobs.map((job) => <option key={job.id} value={job.id}>{job.作业编号}</option>)}
            </select>
          </label>
          <label className="form-item">
            <span>经确认的发布卡</span>
            <select value={pickedCard} onChange={(event) => setPickedCard(Number(event.target.value))}>
              {jobOptions.length === 0 && <option value={0}>暂无可选发布卡</option>}
              {jobOptions.map((option) => (
                <option key={option.发布卡id} value={option.发布卡id}>
                  {option.发布卡编号} · {option.候选模板版本}（{option.映射版本 || '无映射版本'}）
                </option>
              ))}
            </select>
          </label>
          <button className="btn primary" type="button" disabled={pickedCard === 0} onClick={() => void handleBind()}>
            绑定并固化快照
          </button>
        </div>
        {binding ? (
          <div className="snapshot-box">
            <h4>作业 {binding.作业id} 的历史提取依据（发布卡 {binding.发布卡编号}，绑定于 {binding.绑定时间}）</h4>
            <p className="hint">
              固化版本：{binding.依据快照.候选模板版本} · 映射版本：{binding.依据快照.映射版本 || '—'}
            </p>
            <details>
              <summary>查看当时网页片段样本与评审证据</summary>
              <pre className="sample-pre">{binding.依据快照.网页片段样本}</pre>
              {binding.依据快照.选择器评审 && (
                <p className="hint">选择器结论：{binding.依据快照.选择器评审.结论}</p>
              )}
              {binding.依据快照.映射评审 && (
                <p className="hint">映射结论：{binding.依据快照.映射评审.结论}（字段 {binding.依据快照.映射评审.字段数量} 个）</p>
              )}
            </details>
          </div>
        ) : (
          <p className="hint">该作业尚未绑定发布卡。</p>
        )}
      </section>
    </section>
  )
}
