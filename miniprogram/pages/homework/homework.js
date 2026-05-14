const app = getApp()

Page({
  data: {
    loading: true,
    homeworks: [],
    error: '',
  },

  onShow() {
    this.loadRecent()
  },

  async loadRecent() {
    const deviceId = wx.getStorageSync('deviceId')
    if (!deviceId) {
      this.setData({ loading: false, error: '请先绑定设备' })
      return
    }
    this.setData({ loading: true, error: '' })
    try {
      const data = await app.request({
        url: `/api/v1/homework/recent?device_id=${deviceId}&limit=10`,
      })
      this.setData({ homeworks: data, loading: false })
    } catch (err) {
      this.setData({ loading: false, error: '加载失败' })
    }
  },

  goToDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/homework/detail?id=${id}` })
  },

  onPullDownRefresh() {
    this.loadRecent().then(() => wx.stopPullDownRefresh())
  }
})
