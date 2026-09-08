const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// 支持 @ 路径别名
config.resolver.alias = {
  '@': '.',
};

module.exports = config;
