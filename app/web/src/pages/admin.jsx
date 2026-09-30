import React, { useEffect, useState } from 'react'
import {
  Alert, Button, Form, Input, Modal, Popconfirm, Radio, Select, Space, Switch,
  Table, Tag, TimePicker, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import api from '../api'

const ROLE_LABELS = { member: '成员', leader: '产品负责人', admin: '系统管理员' }

export function Members() {
  const [rows, setRows] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [form] = Form.useForm()

  const load = () => api.get('/admin/members').then(setRows).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const openEdit = (record) => {
    setEditTarget(record || {})
    form.setFieldsValue(record ? { ...record, password: '' } : { role: 'member', password: '' })
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      if (editTarget && editTarget.id) {
        await api.put(`/admin/members/${editTarget.id}`, values)
        message.success('已保存')
      } else {
        await api.post('/admin/members', values)
        message.success('已新增，初始密码：' + (values.password || '123456'))
      }
      setEditTarget(null)
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => openEdit(null)}>新增成员</Button>
      <Table rowKey="id" dataSource={rows} pagination={false}
        columns={[
          { title: '用户名', dataIndex: 'username' },
          { title: '姓名', dataIndex: 'name' },
          { title: '企微 UserID', dataIndex: 'wecom_userid', render: (v) => v || '—' },
          { title: '角色', dataIndex: 'role', render: (v) => <Tag>{ROLE_LABELS[v]}</Tag> },
          { title: '创建时间', dataIndex: 'created_at' },
          { title: '操作', render: (_, r) => <Button size="small" onClick={() => openEdit(r)}>编辑</Button> },
        ]} />
      <Modal title={editTarget && editTarget.id ? '编辑成员' : '新增成员'} open={!!editTarget} onOk={submit}
        onCancel={() => setEditTarget(null)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input disabled={!!(editTarget && editTarget.id)} />
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="wecom_userid" label="企微 UserID / 群聊 OpenID（机器人消息按此映射成员姓名，群聊中为 wo 开头 ID）">
            <Input placeholder="企业微信通讯录中的账号 ID" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={Object.entries(ROLE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          </Form.Item>
          <Form.Item name="password" label={editTarget && editTarget.id ? '重置密码（留空不修改）' : '初始密码（默认 123456）'}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export function Contacts() {
  const [rows, setRows] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [form] = Form.useForm()

  const load = () => api.get('/admin/contacts').then(setRows).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const openEdit = (record) => {
    setEditTarget(record)
    form.setFieldsValue({ name: record.name })
  }

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await api.put(`/admin/contacts/${encodeURIComponent(editTarget.wecom_userid)}`, values)
      message.success('已保存')
      setEditTarget(null)
      load()
    } catch (e) { message.error(e.message) }
  }

  const remove = async (userid) => {
    await api.delete(`/admin/contacts/${encodeURIComponent(userid)}`)
    load()
  }

  const sync = async () => {
    setSyncing(true)
    try {
      const res = await api.post('/admin/contacts/sync')
      message.success(`同步完成：${res.total} 个待解析，成功 ${res.resolved} 个`)
      load()
    } catch (e) { message.error(e.message) } finally { setSyncing(false) }
  }

  return (
    <div>
      <Alert style={{ marginBottom: 16 }} type="info" showIcon
        message="机器人会话中出现过的企微 UserID 会自动记录在此。设置显示名称后，收件箱与需求池的「提出人」将显示该名称；若对方是系统成员，也可在「成员管理」中直接绑定企微 UserID。" />
      <Button type="primary" loading={syncing} style={{ marginBottom: 12 }} onClick={sync}>从企微同步名称</Button>
      <Table rowKey="wecom_userid" dataSource={rows} pagination={false}
        columns={[
          { title: '企微 UserID', dataIndex: 'wecom_userid' },
          {
            title: '显示名称', dataIndex: 'name',
            render: (v, r) => (r.member_name ? <Tag color="blue">成员：{r.member_name}</Tag> : v || <Tag>未设置</Tag>),
          },
          { title: '首次出现', dataIndex: 'first_seen' },
          { title: '更新时间', dataIndex: 'updated_at' },
          {
            title: '操作', width: 150, render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => openEdit(r)}>设置名称</Button>
                <Popconfirm title="确认删除该记录？" onConfirm={() => remove(r.wecom_userid)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]} />
      <Modal title="设置显示名称" open={!!editTarget} onOk={submit} onCancel={() => setEditTarget(null)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item label="企微 UserID">
            <Input value={editTarget ? editTarget.wecom_userid : ''} disabled />
          </Form.Item>
          <Form.Item name="name" label="显示名称（留空则仍显示 UserID）">
            <Input placeholder="如：张三" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export function BotConfig() {
  const [form] = Form.useForm()
  const [status, setStatus] = useState(null)

  const load = () => api.get('/admin/bot-config').then((d) => {
    setStatus(d)
    form.setFieldsValue({ bot_id: d.bot_id, bot_mode: d.bot_mode, bot_secret: '', wecom_corpid: d.wecom_corpid, wecom_contact_secret: '' })
  }).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await api.put('/admin/bot-config', values)
      message.success('已保存')
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      {status && (
        <Alert style={{ marginBottom: 16 }} type={status.connected ? 'success' : 'warning'} showIcon
          message={status.bot_mode === 'mock'
            ? '当前为本地模拟模式，消息经「机器人模拟器」收发'
            : status.connected
              ? '企微长连接已连接，机器人会话可正常收发'
              : '企微长连接未连接：保存配置后需重启服务生效；请确认 Bot ID/Secret 正确且服务器可访问企业微信'} />
      )}
      <Form form={form} layout="vertical" initialValues={{ bot_mode: 'mock' }}>
        <Form.Item name="bot_id" label="Bot ID">
          <Input placeholder="企业微信管理后台 API 配置中获取" />
        </Form.Item>
        <Form.Item name="bot_secret" label={`Secret（${status && status.secret_set ? '已设置 ' + status.secret_masked + '，留空不修改' : '未设置'}）`}>
          <Input.Password placeholder="输入后加密存储，不回显" />
        </Form.Item>
        <Form.Item name="wecom_corpid" label="企业 ID（用于按通讯录解析提出人姓名）">
          <Input placeholder="管理后台「我的企业 → 企业信息」中获取，ww 开头" />
        </Form.Item>
        <Form.Item name="wecom_contact_secret" label={`自建应用 Secret（需有通讯录读取权限，${status && status.contact_secret_set ? '已设置 ' + status.contact_secret_masked + '，留空不修改' : '未设置'}）`}>
          <Input.Password placeholder="输入后加密存储，不回显" />
        </Form.Item>
        <Form.Item name="bot_mode" label="接入模式">
          <Radio.Group>
            <Radio.Button value="mock">本地模拟</Radio.Button>
            <Radio.Button value="wecom">企微长连接</Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Button type="primary" onClick={submit}>保存</Button>
      </Form>
    </div>
  )
}

export function ModelConfig() {
  const [form] = Form.useForm()
  const [masked, setMasked] = useState('')

  const load = () => api.get('/admin/model-config').then((d) => {
    setMasked(d.api_key_set ? d.api_key_masked : '')
    form.setFieldsValue({
      model_base_url: d.model_base_url, model_name: d.model_name,
      model_timeout: d.model_timeout, similarity_threshold: d.similarity_threshold, api_key: '',
    })
  }).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await api.put('/admin/model-config', values)
      message.success('已保存')
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      {!masked && <Alert style={{ marginBottom: 16 }} type="warning" showIcon message="未配置 API Key，AI 提炼将使用本地模拟提炼（仅用于联调），配置后自动切换为真实大模型。" />}
      <Form form={form} layout="vertical">
        <Form.Item name="model_base_url" label="Base URL" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="model_name" label="模型名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="api_key" label={`API Key（${masked ? '已设置 ' + masked + '，留空不修改' : '未设置'}）`}>
          <Input.Password placeholder="输入后加密存储，不回显" />
        </Form.Item>
        <Space size={16}>
          <Form.Item name="model_timeout" label="调用超时（秒）" rules={[{ required: true }]}>
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="similarity_threshold" label="相似度阈值" rules={[{ required: true }]}>
            <Input style={{ width: 120 }} />
          </Form.Item>
        </Space>
        <Button type="primary" onClick={submit}>保存</Button>
      </Form>
    </div>
  )
}

export function BroadcastConfig() {
  const [form] = Form.useForm()
  const [last, setLast] = useState(null)

  const load = () => api.get('/admin/broadcast-config').then((d) => {
    setLast(d.last_status)
    form.setFieldsValue({
      daily_time: dayjs(d.broadcast_daily_time, 'HH:mm'),
      weekly_time: dayjs(d.broadcast_weekly_time, 'HH:mm'),
      weekly_day: d.broadcast_weekly_day,
      webhooks: d.broadcast_webhooks,
    })
  }).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await api.put('/admin/broadcast-config', {
        broadcast_daily_time: values.daily_time.format('HH:mm'),
        broadcast_weekly_time: values.weekly_time.format('HH:mm'),
        broadcast_weekly_day: values.weekly_day,
        broadcast_webhooks: values.webhooks || '',
      })
      message.success('已保存')
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      {last && last.status && (
        <Alert style={{ marginBottom: 16 }} showIcon
          type={last.status === 'success' ? 'success' : 'warning'}
          message={`最近一次推送：${last.status === 'success' ? '成功' : last.status === 'no_webhook' ? '未配置 Webhook' : '失败'} ${last.pushed_at || ''}`} />
      )}
      <Form form={form} layout="vertical">
        <Space size={16} wrap>
          <Form.Item name="daily_time" label="每日播报时间" rules={[{ required: true }]}>
            <TimePicker format="HH:mm" minuteStep={5} />
          </Form.Item>
          <Form.Item name="weekly_day" label="每周播报日" rules={[{ required: true }]}>
            <Select style={{ width: 120 }} options={[
              { value: '1', label: '周一' }, { value: '2', label: '周二' }, { value: '3', label: '周三' },
              { value: '4', label: '周四' }, { value: '5', label: '周五' }, { value: '6', label: '周六' }, { value: '7', label: '周日' },
            ]} />
          </Form.Item>
          <Form.Item name="weekly_time" label="每周播报时间" rules={[{ required: true }]}>
            <TimePicker format="HH:mm" minuteStep={5} />
          </Form.Item>
        </Space>
        <Form.Item name="webhooks" label="目标群 Webhook（多个用英文逗号分隔）">
          <Input.TextArea rows={3} placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
        </Form.Item>
        <Button type="primary" onClick={submit}>保存</Button>
      </Form>
    </div>
  )
}

export function Modules() {
  const [rows, setRows] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [form] = Form.useForm()

  const load = () => api.get('/modules', { params: { all: true } }).then(setRows).catch(() => {})
  useEffect(() => { load() }, [])

  const openEdit = (record) => {
    setEditTarget(record || {})
    form.setFieldsValue(record ? { name: record.name, status: record.status === '启用' } : { name: '', status: true })
  }

  const submit = async () => {
    const values = await form.validateFields()
    const payload = { name: values.name, status: values.status ? '启用' : '停用' }
    try {
      if (editTarget && editTarget.id) await api.put(`/admin/modules/${editTarget.id}`, payload)
      else await api.post('/admin/modules', payload)
      message.success('已保存')
      setEditTarget(null)
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => openEdit(null)}>新增模块</Button>
      <Table rowKey="id" dataSource={rows} pagination={false}
        columns={[
          { title: '模块名称', dataIndex: 'name' },
          { title: '状态', dataIndex: 'status', render: (v) => <Tag color={v === '启用' ? 'success' : 'default'}>{v}</Tag> },
          { title: '操作', render: (_, r) => <Button size="small" onClick={() => openEdit(r)}>编辑</Button> },
        ]} />
      <Modal title={editTarget && editTarget.id ? '编辑模块' : '新增模块'} open={!!editTarget} onOk={submit}
        onCancel={() => setEditTarget(null)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="模块名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="status" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export function Versions() {
  const [rows, setRows] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [form] = Form.useForm()

  const load = () => api.get('/versions', { params: { all: true } }).then(setRows).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const openEdit = (record) => {
    setEditTarget(record || {})
    form.setFieldsValue(record ? { name: record.name, status: record.status === '启用' } : { name: '', status: true })
  }

  const submit = async () => {
    const values = await form.validateFields()
    const payload = { name: values.name, status: values.status ? '启用' : '停用' }
    try {
      if (editTarget && editTarget.id) await api.put(`/admin/versions/${editTarget.id}`, payload)
      else await api.post('/admin/versions', payload)
      message.success('已保存')
      setEditTarget(null)
      load()
    } catch (e) { message.error(e.message) }
  }

  return (
    <div>
      <Alert style={{ marginBottom: 16 }} type="info" showIcon
        message="维护产品版本号。需求池中将需求流转为「已排期」时必须选择一个启用中的版本号；已停用的版本号不可再被选择，但不影响已排期需求的显示。" />
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => openEdit(null)}>新增版本号</Button>
      <Table rowKey="id" dataSource={rows} pagination={false}
        columns={[
          { title: '版本号', dataIndex: 'name' },
          { title: '状态', dataIndex: 'status', render: (v) => <Tag color={v === '启用' ? 'success' : 'default'}>{v}</Tag> },
          { title: '创建时间', dataIndex: 'created_at' },
          { title: '操作', render: (_, r) => <Button size="small" onClick={() => openEdit(r)}>编辑</Button> },
        ]} />
      <Modal title={editTarget && editTarget.id ? '编辑版本号' : '新增版本号'} open={!!editTarget} onOk={submit}
        onCancel={() => setEditTarget(null)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="版本号" rules={[{ required: true }]}>
            <Input placeholder="如：V1.0、2026.09" />
          </Form.Item>
          <Form.Item name="status" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export function MaskingWords() {
  const [rows, setRows] = useState([])
  const [word, setWord] = useState('')

  const load = () => api.get('/admin/masking-words').then(setRows).catch((e) => message.error(e.message))
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!word.trim()) return
    try {
      await api.post('/admin/masking-words', { word: word.trim() })
      setWord('')
      load()
    } catch (e) { message.error(e.message) }
  }

  const remove = async (id) => {
    await api.delete(`/admin/masking-words/${id}`)
    load()
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <Alert style={{ marginBottom: 16 }} type="info" showIcon
        message="手机号、身份证号、银行卡号由系统内置规则自动打码；此处维护扩展脱敏词表（如内部敏感项目名称），命中后将替换为 ***。" />
      <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
        <Input value={word} onChange={(e) => setWord(e.target.value)} onPressEnter={add} placeholder="输入需要脱敏的词" />
        <Button type="primary" onClick={add}>添加</Button>
      </Space.Compact>
      <Table rowKey="id" dataSource={rows} pagination={false} size="small"
        columns={[
          { title: '脱敏词', dataIndex: 'word' },
          {
            title: '操作', width: 100, render: (_, r) => (
              <Popconfirm title="确认删除该词条？" onConfirm={() => remove(r.id)}>
                <Button size="small" danger>删除</Button>
              </Popconfirm>
            ),
          },
        ]} />
    </div>
  )
}

export function AiLogs() {
  const [data, setData] = useState({ total: 0, items: [] })
  const [page, setPage] = useState(1)

  const load = (p = page) => api.get('/admin/ai-logs', { params: { page: p, size: 20 } }).then(setData).catch((e) => message.error(e.message))
  useEffect(() => { load(1) }, [])

  return (
    <Table
      rowKey="id"
      dataSource={data.items}
      pagination={{ current: page, total: data.total, pageSize: 20, showTotal: (t) => `共 ${t} 条`, onChange: (p) => { setPage(p); load(p) } }}
      expandable={{
        expandedRowRender: (r) => (
          <div>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }} copyable={{ text: r.request }}>
              <b>请求：</b>{r.request}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }} copyable={{ text: r.response }}>
              <b>响应：</b>{r.response}
            </Typography.Paragraph>
          </div>
        ),
      }}
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '卡片', dataIndex: 'card_id', width: 80, render: (v) => (v ? '#' + v : '—') },
        { title: '状态', dataIndex: 'status', width: 90, render: (v) => <Tag color={v === 'success' ? 'success' : v === 'mock' ? 'default' : 'error'}>{v}</Tag> },
        { title: '耗时(ms)', dataIndex: 'latency_ms', width: 100 },
        { title: '重试次数', dataIndex: 'retries', width: 90 },
        { title: '时间', dataIndex: 'created_at', width: 170 },
      ]}
    />
  )
}
