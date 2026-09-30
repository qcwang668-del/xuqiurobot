import React, { useState } from 'react'
import { Button, Image, Popconfirm, Space, message } from 'antd'
import { DeleteOutlined, EyeOutlined, PaperClipOutlined } from '@ant-design/icons'
import api from '../api'

const IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']

export const isImageAttachment = (att) => {
  if (att.msg_type === 'image') return true
  const name = (att.filename || '').toLowerCase()
  return IMAGE_EXTS.some((ext) => name.endsWith(ext))
}

export const formatSize = (size) => {
  if (!size) return ''
  if (size >= 1024 * 1024) return (size / 1024 / 1024).toFixed(1) + 'MB'
  return Math.max(1, Math.round(size / 1024)) + 'KB'
}

export default function AttachmentList({ attachments, canManage, onRemove }) {
  const [preview, setPreview] = useState(null)
  const [loadingId, setLoadingId] = useState(0)

  const downloadAttachment = async (att) => {
    try {
      const blob = await api.get(`/attachments/${att.id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = att.filename || 'attachment'
      link.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error(e.message)
    }
  }

  const previewAttachment = async (att) => {
    setLoadingId(att.id)
    try {
      const blob = await api.get(`/attachments/${att.id}/download`, { responseType: 'blob' })
      setPreview({ url: URL.createObjectURL(blob), filename: att.filename || '图片预览' })
    } catch (e) {
      message.error(e.message)
    } finally {
      setLoadingId(0)
    }
  }

  const closePreview = () => {
    if (preview) URL.revokeObjectURL(preview.url)
    setPreview(null)
  }

  return (
    <Space direction="vertical" style={{ marginBottom: 16 }}>
      {attachments.map((att) => (
        <Space key={att.id}>
          {isImageAttachment(att) ? (
            <Button size="small" icon={<EyeOutlined />} loading={loadingId === att.id} onClick={() => previewAttachment(att)}>
              {att.filename}（{formatSize(att.size)}）
            </Button>
          ) : (
            <Button size="small" icon={<PaperClipOutlined />} onClick={() => downloadAttachment(att)}>
              {att.filename}（{formatSize(att.size)}）
            </Button>
          )}
          {canManage && (
            <Popconfirm title="确认删除该附件？" onConfirm={() => onRemove(att)} okText="删除" cancelText="取消">
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ))}
      {preview && (
        <Image
          style={{ display: 'none' }}
          src={preview.url}
          preview={{
            visible: true,
            src: preview.url,
            onVisibleChange: (visible) => { if (!visible) closePreview() },
          }}
        />
      )}
    </Space>
  )
}
