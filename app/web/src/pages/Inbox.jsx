import React, { useEffect, useState } from 'react'
import {
  Button, DatePicker, Drawer, Form, Input, Modal, Popconfirm, Select, Space,
  Table, Tabs, Tag, Typography, message,
} from 'antd'
import api from '../api'

const TYPE_COLORS = { 新需求: 'blue', 体验优化: 'orange', 缺陷反馈: 'red' }

function ConfidenceTag({ value }) {
  const v = value || 0
  const color = v < 0.6 ? 'red' : v < 0.8 ? 'orange' : 'green'
  return <Tag color={color}>{v.toFixed(2)}</Tag>
}

export default function Inbox() {
  const [tab, setTab] = useState('pending')
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(false)
  const [confirmingId, setConfirmingId] = useState(null)
  const [reextractingId, setReextractingId] = useState(null)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({})
  const [meta, setMeta] = useState({ members: [], req_types: [], urgencies: [] })
  const [modules, setModules] = useState([])
  const [selectedRowKeys, setSelectedRowKeys] = useState([])
  const [detail, setDetail] = useState(null)
  const [editCard, setEditCard] = useState(null)
  const [form] = Form.useForm()

  const load = async (p = page, f = filters, s = tab) => {
    setLoading(true)
    try {
      const params = { status: s, page: p, size: 20, ...f }
      Object.keys(params).forEach((k) => (params[k] === undefined || params[k] === '') && delete params[k])
      setData(await api.get('/inbox', { params }))
    } catch (e) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    api.get('/meta').then(setMeta).catch(() => {})
    api.get('/modules').then(setModules).catch(() => {})
  }, [])

  useEffect(() => { setPage(1); setSelectedRowKeys([]); load(1, filters, tab) }, [tab])

  const doConfirm = async (card, edits = null, decision = null) => {
    setConfirmingId(card.id)
    try {
      const result = await api.post(`/inbox/${card.id}/confirm`, { edits, decision })
      if (result.need_decision) {
        Modal.confirm({
          title: '检测到相似需求',
          content: `相似需求：${result.similar.req_no} ${result.similar.title}（相似度 ${result.similar.score}）。选择「合并」则该需求提出次数+1，选择「仍新建」创建新需求。`,
          okText: '合并至已有需求',
          cancelText: '仍新建',
          onOk: () => doConfirm(card, edits, 'merge'),
          onCancel: () => doConfirm(card, edits, 'new'),
        })
        return
      }
      message.success(`已加入需求池，需求编号：${result.req_no}`)
      load()
    } catch (e) {
      message.error(e.message)
    } finally {
      setConfirmingId(null)
    }
  }

  const doIgnore = async (card) => {
    try {
      await api.post(`/inbox/${card.id}/ignore`)
      message.success('已忽略')
      load()
    } catch (e) { message.error(e.message) }
  }

  const doReextract = async (card) => {
    setReextractingId(card.id)
    try {
      const r = await api.post(`/inbox/${card.id}/reextract`)
      message.success(`重新提炼成功：${r.title}`)
      load()
    } catch (e) { message.error(e.message) } finally { setReextractingId(null) }
  }

  const doBatchIgnore = async () => {
    try {
      const r = await api.post('/inbox/batch-ignore', { ids: selectedRowKeys })
      message.success(`已忽略 ${r.count} 张卡片`)
      setSelectedRowKeys([])
      load()
    } catch (e) { message.error(e.message) }
  }

  const doRestore = async (card) => {
    try {
      await api.post(`/inbox/${card.id}/restore`)
      message.success('已恢复至待确认')
      load()
    } catch (e) { message.error(e.message) }
  }

  const openEdit = (card) => {
    setEditCard(card)
    form.setFieldsValue({
      title: card.title, description: card.description, req_type: card.req_type,
      module_id: card.module_id || undefined, urgency: card.urgency || '中',
      source_object: card.source_object, expect_time: card.expect_time,
    })
  }

  const submitEdit = async () => {
    const values = await form.validateFields()
    const card = editCard
    setEditCard(null)
    await doConfirm(card, values)
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '标题', dataIndex: 'title', render: (v, r) => (
      <a onClick={async () => setDetail(await api.get(`/inbox/${r.id}`))}>
        {v}
        {r.manual_modified ? <Tag style={{ marginLeft: 4 }}>已修正</Tag> : null}
        {r.pending_action === 'merge_prompt' ? <Tag color="purple" style={{ marginLeft: 4 }}>待合并决策</Tag> : null}
      </a>
    ) },
    { title: '类型', dataIndex: 'req_type', width: 100, render: (v) => <Tag color={TYPE_COLORS[v]}>{v}</Tag> },
    { title: '紧急度', dataIndex: 'urgency', width: 80 },
    { title: '置信度', dataIndex: 'confidence', width: 90, sorter: true, render: (v) => <ConfidenceTag value={v} /> },
    { title: '提出人', dataIndex: 'source_user', width: 110, render: (v, r) => r.source_display || v },
    { title: '上报时间', dataIndex: 'created_at', width: 170, sorter: true },
    {
      title: '操作', width: 340, render: (_, r) => tab === 'pending' ? (
        <Space>
          <Button size="small" type="primary" loading={confirmingId === r.id} onClick={() => doConfirm(r)}>确认入池</Button>
          <Button size="small" onClick={() => openEdit(r)}>编辑后入池</Button>
          <Button size="small" loading={reextractingId === r.id} onClick={() => doReextract(r)}>重新提炼</Button>
          <Popconfirm title="忽略后可在已忽略列表中恢复，确认忽略？" onConfirm={() => doIgnore(r)}>
            <Button size="small" danger>忽略</Button>
          </Popconfirm>
        </Space>
      ) : (
        <Button size="small" onClick={() => doRestore(r)}>恢复</Button>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search placeholder="标题/描述关键词" allowClear style={{ width: 220 }}
          onSearch={(v) => { const f = { ...filters, keyword: v }; setFilters(f); load(1, f) }} />
        <Select placeholder="需求类型" allowClear style={{ width: 130 }}
          options={meta.req_types.map((t) => ({ value: t, label: t }))}
          onChange={(v) => { const f = { ...filters, req_type: v }; setFilters(f); load(1, f) }} />
        <Select placeholder="紧急度" allowClear style={{ width: 100 }}
          options={meta.urgencies.map((t) => ({ value: t, label: t }))}
          onChange={(v) => { const f = { ...filters, urgency: v }; setFilters(f); load(1, f) }} />
        <Select placeholder="AI 置信度" allowClear style={{ width: 140 }}
          options={[{ value: 'low', label: '低于 0.6' }, { value: 'mid', label: '0.6 ~ 0.8' }, { value: 'high', label: '0.8 以上' }]}
          onChange={(v) => { const f = { ...filters, confidence: v }; setFilters(f); load(1, f) }} />
        <Select placeholder="提出人" allowClear style={{ width: 120 }}
          options={meta.members.map((t) => ({ value: t, label: t }))}
          onChange={(v) => { const f = { ...filters, source_user: v }; setFilters(f); load(1, f) }} />
        <DatePicker.RangePicker onChange={(dates) => {
          const f = { ...filters, date_from: dates?.[0]?.format('YYYY-MM-DD'), date_to: dates?.[1]?.format('YYYY-MM-DD') }
          setFilters(f); load(1, f)
        }} />
        {tab === 'pending' && selectedRowKeys.length > 0 && (
          <Popconfirm title={`批量忽略 ${selectedRowKeys.length} 张卡片？`} onConfirm={doBatchIgnore}>
            <Button danger>批量忽略</Button>
          </Popconfirm>
        )}
      </Space>
      <Tabs activeKey={tab} onChange={setTab} items={[{ key: 'pending', label: '待确认' }, { key: 'ignored', label: '已忽略' }]} />
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data.items}
        columns={columns}
        rowSelection={tab === 'pending' ? { selectedRowKeys, onChange: setSelectedRowKeys } : undefined}
        pagination={{ current: page, total: data.total, pageSize: 20, showTotal: (t) => `共 ${t} 条`, onChange: (p) => { setPage(p); load(p) } }}
        onChange={(pagination, f, sorter) => {
          if (sorter.order) {
            const f2 = { ...filters, sort: sorter.field, order: sorter.order === 'ascend' ? 'asc' : 'desc' }
            setFilters(f2); load(1, f2)
          }
        }}
      />
      <Drawer title={`卡片详情 #${detail?.id || ''}`} open={!!detail} onClose={() => setDetail(null)} width={640}>
        {detail && (
          <div>
            <Typography.Title level={5}>{detail.title}</Typography.Title>
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color={TYPE_COLORS[detail.req_type]}>{detail.req_type}</Tag>
              <Tag>紧急度：{detail.urgency}</Tag>
              <ConfidenceTag value={detail.confidence} />
              {detail.source_object && <Tag>来源：{detail.source_object}</Tag>}
              {detail.expect_time && <Tag>期望：{detail.expect_time}</Tag>}
            </Space>
            <Typography.Paragraph>{detail.description}</Typography.Paragraph>
            <Typography.Title level={5}>原文引用（已脱敏）</Typography.Title>
            <Typography.Paragraph type="secondary" style={{ whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12 }}>
              {detail.masked_text}
            </Typography.Paragraph>
            {detail.similar && (
              <Typography.Paragraph type="warning">
                待合并决策：相似需求 {detail.similar.req_no} {detail.similar.title}
              </Typography.Paragraph>
            )}
          </div>
        )}
      </Drawer>
      <Modal title="编辑后入池" open={!!editCard} onOk={submitEdit} onCancel={() => setEditCard(null)} okText="保存并入池" width={640} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, max: 30 }]}>
            <Input maxLength={30} showCount />
          </Form.Item>
          <Form.Item name="description" label="需求描述" rules={[{ required: true, max: 500 }]}>
            <Input.TextArea rows={4} maxLength={500} showCount />
          </Form.Item>
          <Space size={16} wrap>
            <Form.Item name="req_type" label="需求类型" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={meta.req_types.map((t) => ({ value: t, label: t }))} />
            </Form.Item>
            <Form.Item name="module_id" label="所属模块" rules={[{ required: true, message: '请选择模块' }]}>
              <Select style={{ width: 160 }} showSearch optionFilterProp="label"
                options={modules.map((m) => ({ value: m.id, label: m.name }))} />
            </Form.Item>
            <Form.Item name="urgency" label="紧急度">
              <Select style={{ width: 100 }} options={meta.urgencies.map((t) => ({ value: t, label: t }))} />
            </Form.Item>
          </Space>
          <Form.Item name="source_object" label="来源对象">
            <Input placeholder="客户/部门/个人" />
          </Form.Item>
          <Form.Item name="expect_time" label="期望时间">
            <Input placeholder="如：月底前" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
