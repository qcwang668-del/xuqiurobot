import React, { useEffect, useState } from 'react'
import {
  Button, DatePicker, Drawer, Dropdown, Form, Input, Modal, Popconfirm, Select, Space, Tabs,
  Table, Tag, Timeline, Typography, Upload, message,
} from 'antd'
import { DownOutlined, DownloadOutlined, PlusOutlined } from '@ant-design/icons'
import api from '../api'
import { getUser } from '../store'
import AttachmentList from '../components/AttachmentList'

const TYPE_COLORS = { 新需求: 'blue', 体验优化: 'orange', 缺陷反馈: 'red' }
const STATUS_LABELS = { confirmed: '已确认', assessing: '评估中', scheduled: '已排期', developing: '开发中', released: '已上线', rejected: '已拒绝' }
const STATUS_COLORS = { confirmed: 'default', assessing: 'processing', scheduled: 'warning', developing: 'geekblue', released: 'success', rejected: 'error' }
const NEXT_STATUS = { confirmed: ['assessing', 'rejected'], assessing: ['scheduled', 'rejected'], scheduled: ['developing', 'rejected'], developing: ['released', 'rejected'] }
const TAB_STATUSES = { pending: ['confirmed', 'assessing', 'scheduled', 'developing'], released: ['released'], rejected: ['rejected'] }

export default function RequirementPool() {
  const user = getUser()
  const canManage = user.role === 'leader' || user.role === 'admin'
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [tab, setTab] = useState('pending')
  const [filters, setFilters] = useState({})
  const [meta, setMeta] = useState({ members: [], req_types: [], urgencies: [], statuses: {} })
  const [modules, setModules] = useState([])
  const [versions, setVersions] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [editAttachments, setEditAttachments] = useState([])
  const [detail, setDetail] = useState(null)
  const [rejectTarget, setRejectTarget] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [scheduleTarget, setScheduleTarget] = useState(null)
  const [scheduleVersionId, setScheduleVersionId] = useState(undefined)
  const [form] = Form.useForm()

  const load = async (p = page, f = filters, t = tab) => {
    setLoading(true)
    try {
      const params = { page: p, size: 20, ...f }
      params.status = f.status || TAB_STATUSES[t].join(',')
      Object.keys(params).forEach((k) => (params[k] === undefined || params[k] === '' || params[k] === 0) && delete params[k])
      setData(await api.get('/requirements', { params }))
    } catch (e) { message.error(e.message) } finally { setLoading(false) }
  }

  useEffect(() => {
    api.get('/meta').then(setMeta).catch(() => {})
    api.get('/modules').then(setModules).catch(() => {})
    api.get('/versions').then(setVersions).catch(() => {})
    load(1, {}, 'pending')
  }, [])

  const applyFilter = (patch) => {
    const f = { ...filters, ...patch }
    setFilters(f)
    setPage(1)
    load(1, f, tab)
  }

  const switchTab = (key) => {
    const f = { ...filters }
    delete f.status
    setTab(key)
    setFilters(f)
    setPage(1)
    load(1, f, key)
  }

  const openEdit = (record) => {
    setEditTarget(record || {})
    setEditAttachments([])
    form.setFieldsValue(record ? {
      title: record.title, description: record.description, module_id: record.module_id || undefined,
      version_id: record.version_id || undefined,
      req_type: record.req_type, urgency: record.urgency, expect_time: record.expect_time,
      source_text: (record.source_objects || []).join('、'),
    } : { req_type: '新需求', urgency: '中', source_text: '' })
    if (record && record.id) {
      api.get(`/requirements/${record.id}`).then((d) => setEditAttachments(d.attachments || [])).catch(() => {})
    }
  }

  const reloadEditAttachments = async () => {
    if (editTarget && editTarget.id) {
      const d = await api.get(`/requirements/${editTarget.id}`)
      setEditAttachments(d.attachments || [])
    }
  }

  const removeEditAttachment = async (att) => {
    try {
      await api.delete(`/attachments/${att.id}`)
      message.success('附件已删除')
      reloadEditAttachments()
      if (detail && editTarget && detail.id === editTarget.id) reloadDetail()
    } catch (e) {
      message.error(e.message)
    }
  }

  const editUploadProps = {
    showUploadList: false,
    accept: '.png,.jpg,.jpeg,.gif,.bmp,.webp,.docx,.pdf,.xlsx,.xls,.csv,.txt,.md',
    customRequest: async ({ file, onSuccess, onError }) => {
      const formData = new FormData()
      formData.append('file', file)
      try {
        await api.post(`/requirements/${editTarget.id}/attachments`, formData)
        message.success('附件已添加')
        onSuccess()
        reloadEditAttachments()
        if (detail && detail.id === editTarget.id) reloadDetail()
      } catch (e) {
        message.error(e.message)
        onError(e)
      }
    },
  }

  const submitEdit = async () => {
    const values = await form.validateFields()
    const payload = {
      title: values.title, description: values.description || '', module_id: values.module_id || null,
      version_id: values.version_id ?? null,
      req_type: values.req_type, urgency: values.urgency, expect_time: values.expect_time || '',
      source_objects: (values.source_text || '').split(/[、,，]/).map((s) => s.trim()).filter(Boolean),
    }
    try {
      if (editTarget && editTarget.id) {
        await api.put(`/requirements/${editTarget.id}`, payload)
        message.success('已保存')
      } else {
        const result = await api.post('/requirements', payload)
        if (!result.ok && result.dup) {
          Modal.confirm({
            title: '已存在相同标题需求',
            content: `${result.dup.req_no} ${result.dup.title}，是否仍要保存？`,
            onOk: async () => {
              await api.post('/requirements', { ...payload, force: true })
              message.success('已保存')
              load()
            },
          })
          setEditTarget(null)
          return
        }
        message.success(`已新增，需求编号：${result.req_no}`)
      }
      setEditTarget(null)
      load()
    } catch (e) { message.error(e.message) }
  }

  const doTransition = async (record, toStatus, reason = '', versionId = undefined) => {
    try {
      await api.post(`/requirements/${record.id}/transition`, { to_status: toStatus, reason, version_id: versionId })
      message.success('流转成功')
      load()
      if (detail && detail.id === record.id) openDetail(record)
    } catch (e) { message.error(e.message) }
  }

  const openTransition = (record, key) => {
    if (key === 'rejected') { setRejectTarget(record); setRejectReason('') }
    else if (key === 'scheduled') { setScheduleTarget(record); setScheduleVersionId(undefined) }
    else doTransition(record, key)
  }

  const confirmSchedule = async () => {
    if (!scheduleVersionId) { message.error('请选择版本号'); return }
    await doTransition(scheduleTarget, 'scheduled', '', scheduleVersionId)
    setScheduleTarget(null)
  }

  const doDelete = async (record) => {
    try {
      await api.delete(`/requirements/${record.id}`)
      message.success('已删除')
      load()
    } catch (e) { message.error(e.message) }
  }

  const openDetail = async (record) => setDetail(await api.get(`/requirements/${record.id}`))

  const reloadDetail = async () => {
    if (detail) setDetail(await api.get(`/requirements/${detail.id}`))
  }

  const removeAttachment = async (att) => {
    try {
      await api.delete(`/attachments/${att.id}`)
      message.success('附件已删除')
      reloadDetail()
    } catch (e) {
      message.error(e.message)
    }
  }

  const attachmentUploadProps = {
    showUploadList: false,
    accept: '.png,.jpg,.jpeg,.gif,.bmp,.webp,.docx,.pdf,.xlsx,.xls,.csv,.txt,.md',
    customRequest: async ({ file, onSuccess, onError }) => {
      const form = new FormData()
      form.append('file', file)
      try {
        await api.post(`/requirements/${detail.id}/attachments`, form)
        message.success('附件已添加')
        onSuccess()
        reloadDetail()
      } catch (e) {
        message.error(e.message)
        onError(e)
      }
    },
  }

  const doExport = async () => {
    try {
      const params = { ...filters }
      if (!params.status) params.status = TAB_STATUSES[tab].join(',')
      Object.keys(params).forEach((k) => (params[k] === undefined || params[k] === '') && delete params[k])
      const blob = await api.get('/requirements/export', { params, responseType: 'blob' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'requirements.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) { message.error('导出失败') }
  }

  const columns = [
    { title: '需求编号', dataIndex: 'req_no', width: 150 },
    { title: '标题', dataIndex: 'title', render: (v, r) => <a onClick={() => openDetail(r)}>{v}</a> },
    { title: '模块', dataIndex: 'module_name', width: 110, render: (v) => v || '未分配' },
    { title: '类型', dataIndex: 'req_type', width: 100, render: (v) => <Tag color={TYPE_COLORS[v]}>{v}</Tag> },
    { title: '紧急度', dataIndex: 'urgency', width: 80 },
    { title: '状态', dataIndex: 'status', width: 90, render: (v) => <Tag color={STATUS_COLORS[v]}>{STATUS_LABELS[v] || v}</Tag> },
    { title: '版本号', dataIndex: 'version_name', width: 100, render: (v) => v || '—' },
    { title: '提出次数', dataIndex: 'freq', width: 90, sorter: true },
    { title: '来源', dataIndex: 'source_objects', width: 140, render: (v) => (v || []).join('、') || '—' },
    { title: '创建人', dataIndex: 'created_by', width: 90 },
    { title: '更新时间', dataIndex: 'updated_at', width: 165, sorter: true },
    {
      title: '操作', width: 230, render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => openEdit(r)}>编辑</Button>
          {canManage && (NEXT_STATUS[r.status] || []).length > 0 && (
            <Dropdown menu={{
              items: NEXT_STATUS[r.status].map((s) => ({ key: s, label: '流转为' + STATUS_LABELS[s] })),
              onClick: ({ key }) => openTransition(r, key),
            }}>
              <Button size="small">流转 <DownOutlined /></Button>
            </Dropdown>
          )}
          {canManage && (
            <Popconfirm title="删除后不可恢复，确认删除该需求？" onConfirm={() => doDelete(r)}>
              <Button size="small" danger>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Tabs activeKey={tab} onChange={switchTab} items={[
        { key: 'pending', label: '未上线需求' },
        { key: 'released', label: '已上线需求' },
        { key: 'rejected', label: '已拒绝需求' },
      ]} />
      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search placeholder="标题/描述关键词" allowClear style={{ width: 200 }} onSearch={(v) => applyFilter({ keyword: v })} />
        <Select placeholder="所属模块" allowClear style={{ width: 140 }} showSearch optionFilterProp="label"
          options={modules.map((m) => ({ value: m.id, label: m.name }))} onChange={(v) => applyFilter({ module_id: v })} />
        <Select placeholder="类型" allowClear style={{ width: 120 }}
          options={meta.req_types.map((t) => ({ value: t, label: t }))} onChange={(v) => applyFilter({ req_type: v })} />
        <Select placeholder="版本号" allowClear style={{ width: 120 }} showSearch optionFilterProp="label"
          options={versions.map((v) => ({ value: v.id, label: v.name }))} onChange={(v) => applyFilter({ version_id: v })} />
        {tab === 'pending' && (
          <Select placeholder="状态" allowClear style={{ width: 110 }}
            options={TAB_STATUSES.pending.map((v) => ({ value: v, label: STATUS_LABELS[v] }))} onChange={(v) => applyFilter({ status: v })} />
        )}
        <Select placeholder="紧急度" allowClear style={{ width: 100 }}
          options={meta.urgencies.map((t) => ({ value: t, label: t }))} onChange={(v) => applyFilter({ urgency: v })} />
        <Input placeholder="来源对象" allowClear style={{ width: 130 }} onPressEnter={(e) => applyFilter({ source: e.target.value })} />
        <Select placeholder="提出人" allowClear style={{ width: 110 }}
          options={meta.members.map((t) => ({ value: t, label: t }))} onChange={(v) => applyFilter({ created_by: v })} />
        <DatePicker.RangePicker onChange={(dates) => applyFilter({
          date_from: dates?.[0]?.format('YYYY-MM-DD'), date_to: dates?.[1]?.format('YYYY-MM-DD'),
        })} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新增</Button>
        <Button icon={<DownloadOutlined />} onClick={doExport}>导出</Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data.items}
        columns={columns}
        pagination={{ current: page, total: data.total, pageSize: 20, showTotal: (t) => `共 ${t} 条`, onChange: (p) => { setPage(p); load(p) } }}
        onChange={(pagination, f, sorter) => {
          if (sorter.order) applyFilter({ sort: sorter.field, order: sorter.order === 'ascend' ? 'asc' : 'desc' })
        }}
      />
      <Modal title={editTarget && editTarget.id ? `编辑需求 ${editTarget.req_no}` : '新增需求'} open={!!editTarget}
        onOk={submitEdit} onCancel={() => setEditTarget(null)} okText="保存" width={640} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, max: 30 }]}>
            <Input maxLength={30} showCount />
          </Form.Item>
          <Form.Item name="description" label="需求描述" rules={[{ max: 500 }]}>
            <Input.TextArea rows={4} maxLength={500} showCount />
          </Form.Item>
          <Space size={16} wrap>
            <Form.Item name="req_type" label="需求类型" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={meta.req_types.map((t) => ({ value: t, label: t }))} />
            </Form.Item>
            <Form.Item name="module_id" label="所属模块">
              <Select style={{ width: 160 }} showSearch optionFilterProp="label" allowClear
                options={modules.map((m) => ({ value: m.id, label: m.name }))} />
            </Form.Item>
            <Form.Item name="urgency" label="紧急度">
              <Select style={{ width: 100 }} options={meta.urgencies.map((t) => ({ value: t, label: t }))} />
            </Form.Item>
            {editTarget && editTarget.id && (
              <Form.Item name="version_id" label="版本号">
                <Select style={{ width: 140 }} showSearch optionFilterProp="label" allowClear placeholder="未排期"
                  options={[
                    ...versions.map((v) => ({ value: v.id, label: v.name })),
                    ...(editTarget.version_id && !versions.some((v) => v.id === editTarget.version_id)
                      ? [{ value: editTarget.version_id, label: editTarget.version_name || `版本#${editTarget.version_id}` }]
                      : []),
                  ]} />
              </Form.Item>
            )}
          </Space>
          <Form.Item name="source_text" label="来源对象（多个用顿号分隔）">
            <Input placeholder="如：XX客户、财务部" />
          </Form.Item>
          <Form.Item name="expect_time" label="期望时间">
            <Input placeholder="如：月底前" />
          </Form.Item>
          {editTarget && editTarget.id && (
            <Form.Item label={`附件（${editAttachments.length}/10）`}>
              <div>
                {editAttachments.length < 10 && (
                  <Upload {...editUploadProps}>
                    <Button size="small" icon={<PlusOutlined />}>上传附件</Button>
                  </Upload>
                )}
                {editAttachments.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <AttachmentList attachments={editAttachments} canManage={canManage} onRemove={removeEditAttachment} />
                  </div>
                )}
              </div>
            </Form.Item>
          )}
        </Form>
      </Modal>
      <Modal title="流转为已拒绝" open={!!rejectTarget} onCancel={() => setRejectTarget(null)}
        onOk={async () => {
          if (!rejectReason.trim()) { message.error('请填写拒绝原因'); return }
          await doTransition(rejectTarget, 'rejected', rejectReason)
          setRejectTarget(null)
        }} okText="确认流转">
        <Input.TextArea rows={3} maxLength={200} showCount placeholder="拒绝原因（必填）"
          value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
      </Modal>
      <Modal title="流转为已排期" open={!!scheduleTarget} onCancel={() => setScheduleTarget(null)}
        onOk={confirmSchedule} okText="确认流转">
        <Typography.Paragraph type="secondary">请选择该需求排期的版本号（必选）。如需新增版本，请到「系统管理 - 版本配置」中维护。</Typography.Paragraph>
        <Select style={{ width: '100%' }} placeholder="选择版本号（必选）" value={scheduleVersionId}
          onChange={setScheduleVersionId} showSearch optionFilterProp="label"
          options={versions.map((v) => ({ value: v.id, label: v.name }))} />
      </Modal>
      <Drawer title={`需求详情 ${detail?.req_no || ''}`} open={!!detail} onClose={() => setDetail(null)} width={720}>
        {detail && (
          <div>
            <Typography.Title level={5}>{detail.title}</Typography.Title>
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color={STATUS_COLORS[detail.status]}>{STATUS_LABELS[detail.status]}</Tag>
              <Tag color={TYPE_COLORS[detail.req_type]}>{detail.req_type}</Tag>
              <Tag>紧急度：{detail.urgency}</Tag>
              <Tag>模块：{detail.module_name || '未分配'}</Tag>
              {detail.version_name && <Tag color="purple">版本：{detail.version_name}</Tag>}
              <Tag>提出次数：{detail.freq}</Tag>
              {detail.expect_time && <Tag>期望：{detail.expect_time}</Tag>}
            </Space>
            <Typography.Paragraph>{detail.description}</Typography.Paragraph>
            <Typography.Paragraph type="secondary">
              来源：{(detail.source_objects || []).join('、') || '—'} ｜ 创建人:{detail.created_by} ｜ 创建：{detail.created_at} ｜ 更新：{detail.updated_at}
            </Typography.Paragraph>
            {detail.reject_reason && <Typography.Paragraph type="danger">拒绝原因：{detail.reject_reason}</Typography.Paragraph>}
            <Typography.Title level={5}>原文证据链</Typography.Title>
            <Timeline items={detail.evidences.map((e) => ({
              children: (
                <div>
                  <Typography.Text type="secondary">{e.created_at} ｜ {e.source_display || e.source_user}{e.card_id ? ` ｜ 卡片 #${e.card_id}` : ''}</Typography.Text>
                  <div style={{ background: '#fafafa', padding: 8, marginTop: 4, whiteSpace: 'pre-wrap' }}>{e.raw_text}</div>
                </div>
              ),
            }))} />
            <Typography.Title level={5}>
              附件（{(detail.attachments || []).length}/10）
              {(detail.attachments || []).length < 10 && (
                <Upload {...attachmentUploadProps}>
                  <Button size="small" type="link" icon={<PlusOutlined />}>新增附件</Button>
                </Upload>
              )}
            </Typography.Title>
            {(detail.attachments || []).length > 0 && (
              <AttachmentList attachments={detail.attachments} canManage={canManage} onRemove={removeAttachment} />
            )}
            <Typography.Title level={5}>流转记录</Typography.Title>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={detail.transitions}
              columns={[
                { title: '时间', dataIndex: 'created_at', width: 160 },
                { title: '原状态', dataIndex: 'from_status', width: 90, render: (v) => (v ? STATUS_LABELS[v] : '—') },
                { title: '新状态', dataIndex: 'to_status', width: 90, render: (v) => STATUS_LABELS[v] || v },
                { title: '操作人', dataIndex: 'operator', width: 90 },
                { title: '说明', dataIndex: 'reason' },
              ]}
            />
          </div>
        )}
      </Drawer>
    </div>
  )
}
