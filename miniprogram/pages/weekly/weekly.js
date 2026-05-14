const app = getApp()

Page({
  data: {
    loading: true,
    days: [],
    error: '',
    maxMinutes: 1,
  },

  onShow() {
    this.loadWeekly()
  },

  async loadWeekly() {
    const deviceId = wx.getStorageSync('deviceId')
    if (!deviceId) {
      this.setData({ loading: false, error: '请先绑定设备' })
      return
    }
    this.setData({ loading: true })
    try {
      const data = await app.request({ url: `/api/v1/report/weekly?device_id=${deviceId}` })
      const days = data.days || []
      const maxMinutes = Math.max(...days.map(d => d.study_minutes), 1)
      this.setData({ days, maxMinutes, loading: false })
    } catch (err) {
      this.setData({ loading: false, error: '加载失败' })
    }
  },

  barWidth(minutes) {
    return Math.round((minutes / this.data.maxMinutes) * 100)
  },

  onPullDownRefresh() {
    this.loadWeekly().then(() => wx.stopPullDownRefresh())
  }
})
