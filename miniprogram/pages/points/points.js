const app = getApp()

Page({
  data: {
    loading: true,
    summary: null,
    error: '',
  },

  onShow() {
    this.loadSummary()
  },

  async loadSummary() {
    const deviceId = wx.getStorageSync('deviceId')
    if (!deviceId) {
      this.setData({ loading: false, error: '请先绑定设备' })
      return
    }
    this.setData({ loading: true })
    try {
      const summary = await app.request({
        url: `/api/v1/points/summary?device_id=${deviceId}`,
      })
      this.setData({ summary, loading: false })
    } catch (err) {
      this.setData({ loading: false, error: '加载失败' })
    }
  },

  onPullDownRefresh() {
    this.loadSummary().then(() => wx.stopPullDownRefresh())
  }
})
