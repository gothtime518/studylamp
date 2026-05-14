const app = getApp()

App({
  globalData: {
    deviceId: '',
    openid: '',
    baseUrl: 'http://localhost:8000',
  },

  onLaunch() {
    const deviceId = wx.getStorageSync('deviceId')
    if (deviceId) this.globalData.deviceId = deviceId

    const openid = wx.getStorageSync('openid')
    if (openid) {
      this.globalData.openid = openid
    } else {
      this._login()
    }
  },

  _login() {
    wx.login({
      success: res => {
        if (!res.code) return
        // 实际生产中应把 code 发给后端换取 openid
        // MVP 阶段用 code 的 hash 作为临时 openid
        const tmpOpenid = 'user_' + res.code.slice(0, 8)
        wx.setStorageSync('openid', tmpOpenid)
        this.globalData.openid = tmpOpenid
      }
    })
  },

  request(options) {
    return new Promise((resolve, reject) => {
      wx.request({
        url: this.globalData.baseUrl + options.url,
        method: options.method || 'GET',
        data: options.data || {},
        header: { 'Content-Type': 'application/json' },
        success: res => {
          if (res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode}`))
          } else {
            resolve(res.data)
          }
        },
        fail: err => reject(err),
      })
    })
  }
})
