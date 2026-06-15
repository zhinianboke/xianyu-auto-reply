module.exports = {
  root: true,
  env: {
    browser: true,
    es2020: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs', 'node_modules'],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
  },
  plugins: ['react-refresh', '@typescript-eslint'],
  rules: {
    // ==================== React 相关 ====================
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',

    // ==================== TypeScript 相关 ====================
    '@typescript-eslint/no-unused-vars': [
      'warn',
      {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
      },
    ],
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/explicit-function-return-type': 'off',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    '@typescript-eslint/no-non-null-assertion': 'warn',
    '@typescript-eslint/ban-ts-comment': 'warn',

    // ==================== 代码风格 ====================
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'no-debugger': 'warn',
    'no-alert': 'warn',
    'prefer-const': 'error',
    'no-var': 'error',
    'eqeqeq': ['error', 'always', { null: 'ignore' }],
    'curly': ['error', 'multi-line'],
    'no-multiple-empty-lines': ['error', { max: 2, maxEOF: 1 }],
    'no-trailing-spaces': 'error',
    'comma-dangle': ['error', 'always-multiline'],
    'semi': ['error', 'never'],
    'quotes': ['error', 'single', { avoidEscape: true }],

    // ==================== 导入相关 ====================
    'no-duplicate-imports': 'error',
    'sort-imports': [
      'warn',
      {
        ignoreCase: true,
        ignoreDeclarationSort: true,
      },
    ],

    // ==================== 最佳实践 ====================
    'no-nested-ternary': 'warn',
    'no-unneeded-ternary': 'error',
    'no-else-return': 'error',
    'no-useless-return': 'error',
    'no-param-reassign': ['error', { props: false }],
    'array-callback-return': 'error',
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
}
