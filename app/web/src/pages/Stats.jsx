import React, { useEffect, useState } from 'react'
import { Card, Col, Progress, Row, Table, Typography } from 'antd'
import api from '../api'

const STATUS_LABELS = { confirmed: '已确认', assessing: '评估中', scheduled: '已排期', developing: '开发中', released: '已上线', rejected: '已拒绝' }

function DistCard({ title, data, nameMap }) {
  const total = data.reduce((s, i) => s + i.c, 0) || 1
  return (
    <Card title={title} size="small">
      {data.length === 0 && <Typography.Text type="secondary">暂无数据</Typography.Text>}
      {data.map((item) => (
        <div key={item.name} style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{(nameMap && nameMap[item.name]) || item.name}</span>
            <span>{item.c}</span>
          </div>
          <Progress percent={Math.round((item.c / total) * 100)} showInfo={false} size="small" />
        </div>
      ))}
    </Card>
  )
}

export default function Stats() {
  const [data, setData] = useState(null)

  useEffect(() => { api.get('/stats').then(setData).catch(() => {}) }, [])
  if (!data) return null

  return (
    <div>
      <Row gutter={16}>
        <Col span={12}>
          <Card title="近 14 天需求上报趋势" size="small">
            <Table
              rowKey="day"
              size="small"
              pagination={false}
              dataSource={data.trend}
              columns={[
                { title: '日期', dataIndex: 'day' },
                { title: '上报数量', dataIndex: 'c', width: 100 },
                {
                  title: '分布', render: (_, r) => {
                    const max = Math.max(...data.trend.map((t) => t.c), 1)
                    return <Progress percent={Math.round((r.c / max) * 100)} showInfo={false} size="small" />
                  },
                },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="提出次数 Top 榜" size="small">
            <Table
              rowKey="req_no"
              size="small"
              pagination={false}
              dataSource={data.top_freq}
              columns={[
                { title: '需求编号', dataIndex: 'req_no', width: 150 },
                { title: '标题', dataIndex: 'title' },
                { title: '提出次数', dataIndex: 'freq', width: 90 },
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}><DistCard title="模块分布" data={data.module_dist} /></Col>
        <Col span={6}><DistCard title="状态分布" data={data.status_dist} nameMap={STATUS_LABELS} /></Col>
        <Col span={6}><DistCard title="类型分布" data={data.type_dist} /></Col>
        <Col span={6}><DistCard title="来源分布 Top10" data={data.source_dist} /></Col>
      </Row>
    </div>
  )
}
