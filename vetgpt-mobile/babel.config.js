module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    // react-native-reanimated/plugin needs react-native-worklets
    // which only exists after `npx expo prebuild`.
    // Commented out for Expo Go. Uncomment before production build.
    // plugins: ['react-native-reanimated/plugin'],
  };
};
