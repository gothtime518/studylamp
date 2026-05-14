const app = getApp()

const STATE_LABELS = {
  studying:   '学习中 🟢',
  warning:    '坐姿注意 🟡',
  distracted: '分心了 🔴',
  absent:     '未检测到人 ⚫',
}

Page({
  data: {
    loading: true,
    report: null,
    error: '',
    date: '',
    realtimeState: '',
    wsConnected: false,
  },

  _ws: null,

  onLoad() {
    const today = new Date().toISOString().slice(0, 10)
    this.setData({ date: today })
    this.loadReport(today)
  },

  onShow() {
    this._connectWS()
  },

  onHide() {
    this._disconnectWS()
  },

  onUnload() {
    this._disconnectWS()
  },

  _connectWS() {
    const deviceId = wx.getStorageSync('deviceId')
    if (!deviceId) return
    const baseUrl = app.globalData.baseUrl.replace('http://', 'ws://').replace('https://', 'wss://')
    const wsUrl = `${baseUrl}/api/v1/realtime/${deviceId}`

    this._ws = wx.connectSocket({ url: wsUrl, fail: () => {} })

    this._ws.onOpen(() => {
      this.setData({ wsConnected: true })
      // 每 30 秒 ping 保活
      this._pingTimer = setInterval(() => {
        this._ws && this._ws.send({ data: 'ping' })
      }, 30000)
    })

    this._ws.onMessage(res => {
      try {
        const data = JSON.parse(res.data)
        if (data.state) {
          this.setData({ realtimeState: STATE_LABELS[data.state] || data.state })
        }
      } catch (e) {}
    })

    this._ws.onClose(() => {
      this.setData({ wsConnected: false, realtimeState: '' })
      clearInterval(this._pingTimer)
    })
  },

  _disconnectWS() {
    clearInterval(this._pingTimer)
    if (this._ws) {
      this._ws.close({})
      this._ws = null
    }
  },

  async loadReport(date) {
    const deviceId = wx.getStorageSync('deviceId')
    if (!deviceId) {
      this.setData({ loading: false, error: '请先绑定设备' })
      return
    }
    this.setData({ loading: true, error: '' })
    try {
      const report = await app.request({
        url: `/api/v1/report/daily/${date}?device_id=${deviceId}`,
      })
      this.setData({ report, loading: false })
    } catch (err) {
      this.setData({ loading: false, error: '加载失败，请检查网络' })
    }
  },

  onPullDownRefresh() {
    this.loadReport(this.data.date).then(() => wx.stopPullDownRefresh())
  }
})
