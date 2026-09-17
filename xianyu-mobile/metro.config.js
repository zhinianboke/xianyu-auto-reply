// gradle release 打包强制 production，确保 __DEV__=false，
// 避免 react-navigation/expo-router 的 dev 路由浮窗混入 release 遮挡 tab bar。
// 注意：本地 dev 开发（expo start）需临时注释此行，否则 __DEV__=false 影响 HMR。
process.env.NODE_ENV = 'production';

const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// 支持 @ 路径别名
config.resolver.alias = {
  '@': '.',
};

module.exports = config;
