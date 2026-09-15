import React, { useEffect, useRef, useState } from 'react'
import { Button, Card, Col, Input, Row, Select, Space, Tag, Typography, message } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import api from '../api'

export default function BotSimulator() {
  const [user, setUser] = useState('王雁')
  const [members, setMembers] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const listRef = useRef(null)

  const load = async (u = user) => {
    try {
      setMessages(await api.get('/simulate/messages', { params: { user_name: u, limit: 80 } }))
    } catch { /* ignore */ }
  }

  useEffect(() => {
    api.get('/meta').then((m) => setMembers(m.members)).catch(() => {})
    load()
    const timer = setInterval(() => load(), 3000)
    return () => clearInterval(timer)
  }, [user])

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages])

  const send = async () => {
    if (!input.trim()) return
    setSending(true)
    try {
      await api.post('/simulate/message', { user, text: input.trim() })
      setInput('')
      load()
    } catch (e) {
      message.error(e.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <Row gutter={16}>
      <Col span={14}>
        <Card
          title={
            <Space>
              机器人会话模拟器
              <Select value={user} style={{ width: 140 }} onChange={(v) => { setUser(v); setMessages([]) }}
                options={members.map((m) => ({ value: m, label: m }))} />
            </Space>
          }
        >
          <div ref={listRef} style={{ height: 480, overflowY: 'auto', padding: 8, background: '#f5f5f5', borderRadius: 8 }}>
            {messages.map((m) => (
              <div key={m.id} style={{ display: 'flex', justifyContent: m.direction === 'in' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
                <div style={{
                  maxWidth: '75%', padding: '8px 12px', borderRadius: 8, whiteSpace: 'pre-wrap',
                  background: m.direction === 'in' ? '#95ec69' : '#fff', boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
                }}>
                  <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>
                    {m.direction === 'in' ? user : '需求助手'} ｜ {m.created_at}
                  </div>
                  {m.content}
                </div>
              </div>
            ))}
            {messages.length === 0 && <Typography.Text type="secondary">暂无会话记录，发送一条需求试试</Typography.Text>}
          </div>
          <Space.Compact style={{ width: '100%', marginTop: 12 }}>
            <Input value={input} onChange={(e) => setInput(e.target.value)} onPressEnter={send}
              placeholder="输入需求内容，或回复 确认 / 修改：意见 / 忽略 / 合并 / 新建 / 帮助" />
            <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={send}>发送</Button>
          </Space.Compact>
        </Card>
      </Col>
      <Col span={10}>
        <Card title="指令说明" size="small">
          <Typography.Paragraph>
            <Tag>上报</Tag>直接发送需求文字，5 分钟内连续消息自动合并为一条。
          </Typography.Paragraph>
          <Typography.Paragraph>
            <Tag>确认</Tag>收到确认卡片后回复「确认」加入需求池。
          </Typography.Paragraph>
          <Typography.Paragraph>
            <Tag>修改</Tag>回复「修改：你的意见」，AI 重新整理（最多 3 轮）。
          </Typography.Paragraph>
          <Typography.Paragraph>
            <Tag>忽略</Tag>回复「忽略」归档卡片，可在网页端已忽略列表恢复。
          </Typography.Paragraph>
          <Typography.Paragraph>
            <Tag>合并/新建</Tag>检测到相似需求时，回复「合并」或「新建」。
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary">
            模拟器用于本地联调，消息流与真实企微机器人一致；接入真实机器人后在企微会话中按同样指令操作。
          </Typography.Paragraph>
        </Card>
      </Col>
    </Row>
  )
}
