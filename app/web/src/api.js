import axios from 'axios'

export const AI_TIMEOUT = 250000

const api = axios.create({ baseURL: '/api', timeout: 30000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = 'Bearer ' + token
  return config
})

api.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    const detail = (err.response && err.response.data && err.response.data.detail) || err.message
    return Promise.reject(new Error(typeof detail === 'string' ? detail : '请求失败'))
  },
)

export default api
