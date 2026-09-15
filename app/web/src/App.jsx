import React, { useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ConfigProvider, Dropdown, Layout, Menu, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import {
  DashboardOutlined, InboxOutlined, DatabaseOutlined, SoundOutlined, BarChartOutlined,
  SettingOutlined, RobotOutlined, LogoutOutlined, UserOutlined,
} from '@ant-design/icons'
import { getUser, clearAuth } from './store'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Inbox from './pages/Inbox'
import RequirementPool from './pages/RequirementPool'
import Broadcasts from './pages/Broadcasts'
import Stats from './pages/Stats'
import BotSimulator from './pages/BotSimulator'
import { Members, Contacts, BotConfig, ModelConfig, BroadcastConfig, Modules, MaskingWords, AiLogs } from './pages/admin'

const { Sider, Header, Content } = Layout

function AdminLayout() {
  const user = getUser()
  const navigate = useNavigate()
  const location = useLocation()
  const [meta, setMeta] = useState({ bot_mode: 'mock' })
  const { token } = theme.useToken()

  if (!user) return <Navigate to="/login" replace />

  const items = useMemo(() => {
    const list = [
      { key: '/', icon: <DashboardOutlined />, label: '首页概览' },
      { key: '/inbox', icon: <InboxOutlined />, label: '待确认需求' },
      { key: '/requirements', icon: <DatabaseOutlined />, label: '需求池' },
      { key: '/broadcasts', icon: <SoundOutlined />, label: '汇总播报' },
      { key: '/stats', icon: <BarChartOutlined />, label: '统计分析' },
      { key: '/simulator', icon: <RobotOutlined />, label: '机器人模拟器' },
    ]
    if (user.role === 'admin') {
      list.push({
        key: '/admin', icon: <SettingOutlined />, label: '系统管理',
        children: [
          { key: '/admin/members', label: '成员管理' },
          { key: '/admin/contacts', label: '提出人名单' },
          { key: '/admin/bot', label: '机器人配置' },
          { key: '/admin/model', label: '模型配置' },
          { key: '/admin/broadcast', label: '播报配置' },
          { key: '/admin/modules', label: '模块配置' },
          { key: '/admin/masking', label: '脱敏配置' },
          { key: '/admin/logs', label: 'AI 调用日志' },
        ],
      })
    }
    return list
  }, [user.role])

  const selected = location.pathname === '/' ? '/' : '/' + location.pathname.split('/').slice(1, 3).join('/').replace(/\/$/, '')

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={220}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 16 }}>
          <img src="/logo.png" alt="logo" style={{ width: 32, height: 32, borderRadius: 8 }} />
          <span style={{ color: '#fff', fontSize: 16, fontWeight: 600 }}>需求搜集智能工作台</span>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected === '/admin' ? location.pathname : selected]}
          defaultOpenKeys={location.pathname.startsWith('/admin') ? ['/admin'] : []}
          items={items} onClick={({ key }) => navigate(key)} />
      </Sider>
      <Layout>
        <Header style={{ background: token.colorBgContainer, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', padding: '0 24px' }}>
          <Dropdown menu={{
            items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录' }],
            onClick: () => { clearAuth(); navigate('/login') },
          }}>
            <span style={{ cursor: 'pointer' }}>
              <UserOutlined style={{ marginRight: 8 }} />
              {user.name}（{user.role === 'admin' ? '系统管理员' : user.role === 'leader' ? '产品负责人' : '成员'}）
            </span>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AdminLayout />}>
            <Route path="/" element={<Overview />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/requirements" element={<RequirementPool />} />
            <Route path="/broadcasts" element={<Broadcasts />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/simulator" element={<BotSimulator />} />
            <Route path="/admin/members" element={<Members />} />
            <Route path="/admin/contacts" element={<Contacts />} />
            <Route path="/admin/bot" element={<BotConfig />} />
            <Route path="/admin/model" element={<ModelConfig />} />
            <Route path="/admin/broadcast" element={<BroadcastConfig />} />
            <Route path="/admin/modules" element={<Modules />} />
            <Route path="/admin/masking" element={<MaskingWords />} />
            <Route path="/admin/logs" element={<AiLogs />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
