import React, { useEffect, useState } from 'react'
import { Button, Modal, Space, Table, Tag, Typography, message } from 'antd'
import api from '../api'
import { getUser } from '../store'

const TYPE_LABELS = { daily: '每日播报', weekly: '每周播报' }
const STATUS_LABELS = { success: '推送成功', failed: '推送失败', no_webhook: '未配置Webhook' }
const STATUS_COLORS = { success: 'success', failed: 'error', no_webhook: 'warning' }

export default function Broadcasts() {
  const user = getUser()
  const canGenerate = user.role === 'leader' || user.role === 'admin'
  const [data, setData] = useState({ total: 0, items: [] })
  const [page, setPage] = useState(1)
  const [content, setContent] = useState(null)

  const load = async (p = page) => {
    setData(await api.get('/broadcasts', { params: { page: p, size: 20 } }))
  }

  useEffect(() => { load(1) }, [])

  const generate = async (btype) => {
    try {
      const r = await api.post('/broadcasts/generate', { btype })
      if (r.status === 'no_webhook') message.warning('已生成，但未配置群机器人 Webhook，仅记录未推送')
      else if (r.status === 'failed') message.error('推送失败，请检查 Webhook 配置')
      else message.success('已生成并推送')
      load()
    } catch (e) { message.error(e.message) }
  }

  const resend = async (record) => {
    try {
      const r = await api.post(`/broadcasts/${record.id}/resend`)
      if (r.status === 'no_webhook') message.warning('未配置 Webhook，未推送')
      else message.success('已补发')
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div>
      {canGenerate && (
        <Space style={{ marginBottom: 12 }}>
          <Button type="primary" onClick={() => generate('daily')}>立即生成日报</Button>
          <Button onClick={() => generate('weekly')}>立即生成周报</Button>
        </Space>
      )}
      <Table
        rowKey="id"
        dataSource={data.items}
        pagination={{ current: page, total: data.total, pageSize: 20, showTotal: (t) => `共 ${t} 条`, onChange: (p) => { setPage(p); load(p) } }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '类型', dataIndex: 'btype', width: 110, render: (v) => TYPE_LABELS[v] || v },
          { title: '业务日期', dataIndex: 'biz_date', width: 120 },
          { title: '推送状态', dataIndex: 'status', width: 120, render: (v) => <Tag color={STATUS_COLORS[v]}>{STATUS_LABELS[v] || v}</Tag> },
          { title: '推送时间', dataIndex: 'pushed_at', width: 170, render: (v) => v || '—' },
          { title: '生成时间', dataIndex: 'created_at', width: 170 },
          {
            title: '操作', width: 160, render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => setContent(r.content)}>查看内容</Button>
                {canGenerate && <Button size="small" onClick={() => resend(r)}>补发</Button>}
              </Space>
            ),
          },
        ]}
      />
      <Modal title="播报内容" open={!!content} footer={null} onCancel={() => setContent(null)} width={560}>
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{content}</Typography.Paragraph>
      </Modal>
    </div>
  )
}
