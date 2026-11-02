/**
 * 闲鱼小程序 - 强制跳转外部浏览器页面
 * 
 * 核心 API：my.openUrl
 * 官方文档：https://miniprogram.alipay.com/docs/miniprogram_claro/mpdev/open-url
 * 功能：在设备默认浏览器中打开指定 URL
 */

// 目标链接（可从页面参数获取或写死）
const TARGET_URL = 'https://xianyu.jinan.me/Xian_goods/App.php?ClickID=455&te=62';

Page({
  data: {
    targetUrl: TARGET_URL,
    status: 'loading',  // loading | success | fail | manual
    errorMsg: ''
  },

  onLoad(query) {
    // 支持从页面参数传入目标 URL
    if (query && query.url) {
      this.setData({ targetUrl: decodeURIComponent(query.url) });
    }
    // 页面加载后自动尝试跳转
    this.tryOpenBrowser();
  },

  /**
   * 核心方法：调用 my.openUrl 在系统默认浏览器中打开 URL
   * 这是阿里小程序官方 API，闲鱼/淘宝/支付宝小程序通用
   */
  tryOpenBrowser() {
    const url = this.data.targetUrl;
    const that = this;

    // 方式1：my.openUrl（推荐，标准调用方式）
    if (typeof my !== 'undefined' && my.openUrl) {
      my.openUrl({
        url: url,
        complete(res) {
          console.log('my.openUrl complete:', res);
          if (res && res.code === 0) {
            // 成功唤起系统浏览器
            that.setData({ status: 'success' });
          } else {
            // 失败，降级到其他方案
            that.fallbackToWebView(url);
          }
        }
      });
      return;
    }

    // 方式2：my.call('openUrl', ...)（兼容旧版本）
    if (typeof my !== 'undefined' && my.call) {
      my.call('openUrl', {
        url: url,
        complete(res) {
          if (res && res.code === 0) {
            that.setData({ status: 'success' });
          } else {
            that.fallbackToWebView(url);
          }
        }
      });
      return;
    }

    // 都不支持，显示手动引导
    this.setData({ status: 'manual', errorMsg: '当前环境不支持自动跳转，请手动操作' });
  },

  /**
   * 降级方案1：通过 web-view 组件打开
   * 如果 openUrl 失败，可以先在小程序内 web-view 打开，再引导用户
   */
  fallbackToWebView(url) {
    this.setData({ status: 'manual', errorMsg: '自动跳转失败，请点击下方按钮在浏览器中打开' });
  },

  /**
   * 降级方案2：复制链接到剪贴板
   */
  copyUrl() {
    const url = this.data.targetUrl;
    my.setClipboard({
      text: url,
      success() {
        my.showToast({ content: '链接已复制，请在浏览器中粘贴打开' });
      },
      fail() {
        my.showToast({ content: '复制失败，请手动复制' });
      }
    });
  },

  /**
   * 用户点击按钮重新尝试打开浏览器
   */
  onRetry() {
    this.setData({ status: 'loading', errorMsg: '' });
    this.tryOpenBrowser();
  }
});
