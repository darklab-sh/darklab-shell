export default [
  {
    files: ['../tests/js/**/*.js', '../playwright*.js', './playwright*.js'],
    rules: {
      indent: ['error', 2],
      quotes: ['error', 'single', { avoidEscape: true }],
      semi: ['error', 'never'],
    },
  },
]
