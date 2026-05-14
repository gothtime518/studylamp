const app = getApp()

Page({
  data: {
    inputId: '',
    inputName: '',
    error: '',
    loading: false,
  },

  onInputId(e) {
    this.setData({ inputId: e.detail.value.trim(), error: '' })
  },

  onInputName(e) {
    this.setData({ inputName: e.detail.value.trim(), error: '' })
  },

  async bind() {
    const deviceId = this.data.inputId
    const name = this.data.inputName || '我的孩子'
    if (!deviceId) return

    this.setData({ loading: true, error: '' })
    wx.showLoading({ title: '验证中…' })

    try {
      const today = new Date().toISOString().slice(0, 10)
      // 验证设备可达
      await app.request({
        url: `/api/v1/report/daily/${today}?device_id=${deviceId}`,
      })

      // 注册孩子绑定关系
      const openid = wx.getStorageSync('openid') || app.globalData.openid || 'local-user'
      try {
        await app.request({
          url: '/api/v1/children',
          method: 'POST',
          data: { parent_openid: openid, name, device_id: deviceId },
        })
      } catch (e) {
        // 409 = 已绑定，忽略
      }

      wx.setStorageSync('deviceId', deviceId)
      app.globalData.deviceId = deviceId
      wx.hideLoading()
      this.setData({ loading: false })
      wx.showToast({ title: '绑定成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1200)
    } catch (err) {
      wx.hideLoading()
      this.setData({ loading: false, error: '无法连接设备，请检查设备 ID 或网络' })
    }
  }
})
