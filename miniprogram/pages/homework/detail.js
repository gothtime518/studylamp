const app = getApp()

Page({
  data: {
    loading: true,
    hw: null,
    error: '',
  },

  onLoad(options) {
    this.loadDetail(options.id)
  },

  async loadDetail(id) {
    try {
      const hw = await app.request({ url: `/api/v1/homework/${id}/analysis` })
      this.setData({ hw, loading: false })
    } catch (err) {
      this.setData({ loading: false, error: '加载失败' })
    }
  }
})
