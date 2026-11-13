/** 发布评审接口封装：所有写操作都返回后端的 ActionResult，由页面统一解读 ok/message。 */
import { request } from '@/api/client'

import type {
  ActionResult,
  BindingSnapshot,
  CompareResult,
  JobOption,
  ReviewCard,
  ReviewContext,
} from './types'

const BASE = '/api/review'

async function unwrap<T>(response: Response): Promise<ActionResult<T>> {
  const payload = (await response.json()) as ActionResult<T>
  return payload
}

export async function fetchContext(): Promise<ReviewContext> {
  const response = await request(`${BASE}/context`)
  return (await response.json()) as ReviewContext
}

export async function fetchSampleHtml(): Promise<string> {
  const response = await request(`${BASE}/sample-html`)
  const payload = (await response.json()) as { html: string }
  return payload.html
}

export async function fetchCards(params?: { status?: string; keyword?: string }): Promise<ReviewCard[]> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.keyword) search.set('keyword', params.keyword)
  const response = await request(`${BASE}/cards?${search.toString()}`)
  const payload = (await response.json()) as { items: ReviewCard[] }
  return payload.items
}

export async function createCard(values: Record<string, unknown>): Promise<ActionResult<ReviewCard>> {
  return unwrap<ReviewCard>(
    await request(`${BASE}/cards`, { method: 'POST', body: JSON.stringify({ values }) }),
  )
}

export async function updateCard(cardId: number, values: Record<string, unknown>): Promise<ActionResult<ReviewCard>> {
  return unwrap<ReviewCard>(
    await request(`${BASE}/cards/${cardId}`, { method: 'PATCH', body: JSON.stringify({ values }) }),
  )
}

export async function runStageCheck(cardId: number, stage: string): Promise<ActionResult<ReviewCard>> {
  return unwrap<ReviewCard>(
    await request(`${BASE}/cards/${cardId}/checks`, {
      method: 'POST',
      body: JSON.stringify({ values: { stage } }),
    }),
  )
}

export async function confirmCard(cardId: number, reviewer: string, remark: string): Promise<ActionResult<ReviewCard>> {
  return unwrap<ReviewCard>(
    await request(`${BASE}/cards/${cardId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ values: { reviewer, remark } }),
    }),
  )
}

export async function discardCard(cardId: number, reason: string): Promise<ActionResult<ReviewCard>> {
  return unwrap<ReviewCard>(
    await request(`${BASE}/cards/${cardId}/discard`, {
      method: 'POST',
      body: JSON.stringify({ values: { reason } }),
    }),
  )
}

export async function compareCard(cardId: number): Promise<ActionResult<CompareResult>> {
  return unwrap<CompareResult>(await request(`${BASE}/cards/${cardId}/compare`))
}

export async function fetchJobOptions(templateId?: number): Promise<JobOption[]> {
  const search = new URLSearchParams()
  if (templateId) search.set('template_id', String(templateId))
  const response = await request(`${BASE}/job-options?${search.toString()}`)
  const payload = (await response.json()) as { items: JobOption[] }
  return payload.items
}

export async function bindJob(jobId: number, cardId: number): Promise<ActionResult<BindingSnapshot>> {
  return unwrap<BindingSnapshot>(
    await request(`${BASE}/bindings`, {
      method: 'POST',
      body: JSON.stringify({ values: { job_id: jobId, card_id: cardId } }),
    }),
  )
}

export async function fetchJobBinding(jobId: number): Promise<ActionResult<BindingSnapshot>> {
  return unwrap<BindingSnapshot>(await request(`${BASE}/jobs/${jobId}/binding`))
}
