const app = getApp()

Page({
  data: {
    children: [],
    activeDeviceId: '',
    bound: false,
  },

  onShow() {
    const openid = wx.getStorageSync('openid') || 'local-user'
    const activeDeviceId = wx.getStorageSync('deviceId') || ''
    this.setData({ activeDeviceId, bound: !!activeDeviceId })
    this.loadChildren(openid)
  },

  async loadChildren(openid) {
    try {
      const list = await app.request({
        url: `/api/v1/children?parent_openid=${openid}`,
      })
      this.setData({ children: list })
    } catch (e) {
      // 服务器未启动时静默失败，不影响本地使用
    }
  },

  switchChild(e) {
    const deviceId = e.currentTarget.dataset.id
    wx.setStorageSync('deviceId', deviceId)
    app.globalData.deviceId = deviceId
    this.setData({ activeDeviceId: deviceId, bound: true })
    wx.showToast({ title: '已切换', icon: 'success' })
  },

  goToBind() {
    wx.navigateTo({ url: '/pages/bind/bind' })
  },

  goToReport() {
    wx.navigateTo({ url: '/pages/report/report' })
  },

  removeChild(e) {
    const id = e.currentTarget.dataset.childid
    const name = e.currentTarget.dataset.name
    wx.showModal({
      title: `移除 ${name}`,
      content: '确认移除该孩子的设备绑定？',
      success: async res => {
        if (!res.confirm) return
        try {
          await app.request({ url: `/api/v1/children/${id}`, method: 'DELETE' })
          const openid = wx.getStorageSync('openid') || 'local-user'
          this.loadChildren(openid)
        } catch (e) {
          wx.showToast({ title: '操作失败', icon: 'error' })
        }
      }
    })
  }
})
