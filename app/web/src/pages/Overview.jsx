import React, { useEffect, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import api from '../api'

const STATUS_LABELS = { confirmed: '已确认', assessing: '评估中', scheduled: '已排期', developing: '开发中', released: '已上线', rejected: '已拒绝' }
const TYPE_COLORS = { 新需求: 'blue', 体验优化: 'orange', 缺陷反馈: 'red' }

export default function Overview() {
  const [data, setData] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/overview').then(setData).catch(() => {})
  }, [])

  if (!data) return null
  const statusMap = Object.fromEntries(data.status_dist.map((s) => [s.status, s.c]))

  return (
    <div>
      <Row gutter={16}>
        <Col span={4}><Card><Statistic title="需求池总量" value={data.total} /></Card></Col>
        <Col span={4}><Card><Statistic title="待确认卡片" value={data.pending} /></Card></Col>
        <Col span={4}><Card><Statistic title="我的待确认" value={data.my_pending} /></Card></Col>
        <Col span={4}><Card><Statistic title="今日新增上报" value={data.today_new} /></Card></Col>
        <Col span={4}><Card><Statistic title="今日确认入池" value={data.today_confirmed} /></Card></Col>
        <Col span={4}>
          <Card>
            <Typography.Text type="secondary">状态分布</Typography.Text>
            <div style={{ marginTop: 8 }}>
              {Object.entries(STATUS_LABELS).map(([k, label]) => (
                <div key={k}>{label}：{statusMap[k] || 0}</div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>
      <Card title="最新待确认卡片" style={{ marginTop: 16 }}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={data.latest_pending}
          columns={[
            { title: 'ID', dataIndex: 'id', width: 60 },
            { title: '标题', dataIndex: 'title' },
            { title: '类型', dataIndex: 'req_type', width: 100, render: (v) => <Tag color={TYPE_COLORS[v]}>{v}</Tag> },
            { title: '紧急度', dataIndex: 'urgency', width: 80 },
            { title: '置信度', dataIndex: 'confidence', width: 90, render: (v) => (v || 0).toFixed(2) },
            { title: '提出人', dataIndex: 'source_user', width: 100 },
            { title: '上报时间', dataIndex: 'created_at', width: 170 },
          ]}
          onRow={() => ({ onClick: () => navigate('/inbox'), style: { cursor: 'pointer' } })}
        />
      </Card>
    </div>
  )
}
